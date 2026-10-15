"""Mesure du terme de forme de la win chance (SPEC-33 §2, §4.6, tâche 159).

Pour chaque partie lue de `crawl.db`, la forme de chacun des dix joueurs AVANT la partie : taux de
victoire et KDA sur ses parties antérieures (`crawl_histories`), puis impact ΔP moyen sur ses parties
antérieures lues dans cette exécution. Variable d'équipe = moyenne bleu − moyenne rouge, centrée sur
les joueurs connus (inconnu = 0). Validation croisée poolée à `FORM_CV_FOLDS` blocs contigus, modèle
en place (`INPUTS`) contre modèle + variable, sur les mêmes blocs. Décision au seuil du §2, figé avant
la mesure.

Lecture seule : `crawl.db` est ouverte en `mode=ro`, le Live Coach peut rester ouvert. Ce n'est pas un
test : les chiffres dépendent de la base et du modèle. L'impact vient du modèle en place, entraîné sur
ces mêmes parties (biais imprimé).

USAGE:
    python scripts/measure_form_term.py                        # attente, ou mesure si la base est prête
    python scripts/measure_form_term.py --force --limit 3000   # mesure sur les 3 000 parties les plus récentes
"""

import argparse
import random
import sqlite3
import sys
import time
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Dict, List, Optional, Sequence, Tuple

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.analysis.calibration import brier_score
from src.coaching.metrics import participant_roles
from src.config_winprob import winprob_config as cfg
from src.winprob.crawl import unpack
from src.winprob.impact import impacts
from src.winprob.model import INPUTS, WinModel, fit
from src.winprob.state import BLUE, RED, blue_win, frame_states
from src.winprob.train import crawl_path, load_model

PROGRESS_EVERY = 5000
TEAM_SIZE = 5
STATES_PER_GAME = 28  # ~28 images par partie, comme train.games

Point = Tuple[float, int, float]  # (probabilité, victoire bleue, minute)


@dataclass
class Game:
    """Une partie retenue : images échantillonnées (avec les variables d'équipe), issue bleue."""

    states: List[dict]
    win: int
    covered: bool  # assez de joueurs avec assez d'impacts antérieurs (sous-ensemble §4.6)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SPEC-33 : mesure du terme de forme")
    parser.add_argument("--db-path", default=str(crawl_path()))
    parser.add_argument(
        "--limit", type=int, default=None, help="parties les plus récentes, au plus"
    )
    parser.add_argument(
        "--force", action="store_true", help="mesurer même sous FORM_MIN_COVERED_GAMES"
    )
    return parser.parse_args()


def covered_games(db: sqlite3.Connection, players: int, min_games: int) -> int:
    """Parties lues où au moins `players` joueurs ont la partie dans `crawl_histories` et au moins
    `min_games` parties antérieures. Sans décompression : approximation, qui compte aussi les parties
    lues sans timeline ou trop courtes, écartées ensuite par la mesure."""
    (count,) = db.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT h.game_id
            FROM crawl_histories h
            JOIN crawl_games g ON g.game_id = h.game_id AND g.read_utc IS NOT NULL
            WHERE (SELECT COUNT(*) FROM crawl_histories p
                   WHERE p.puuid = h.puuid AND p.creation_utc < h.creation_utc) >= ?
            GROUP BY h.game_id
            HAVING COUNT(*) >= ?
        )
        """,
        (min_games, players),
    ).fetchone()
    return count


def load_histories(db: sqlite3.Connection) -> Dict[str, List[tuple]]:
    """puuid -> parties de `crawl_histories` (création, id, victoire, kills, deaths, assists), de la
    plus ancienne à la plus récente."""
    out: Dict[str, List[tuple]] = defaultdict(list)
    query = (
        "SELECT puuid, creation_utc, game_id, win, kills, deaths, assists "
        "FROM crawl_histories ORDER BY creation_utc, game_id"
    )
    for puuid, creation, game_id, win, kills, deaths, assists in db.execute(query):
        out[puuid].append((creation, game_id, win, kills, deaths, assists))
    return out


def _prior(rows: Sequence[tuple], creation_utc: str, game_id: int, window: int) -> List[tuple]:
    """Les `window` dernières lignes strictement antérieures à `creation_utc`, hors `game_id`, de la
    plus ancienne à la plus récente. `rows` est trié par création croissante (début du tuple)."""
    i = bisect_left(rows, (creation_utc,))
    picked: List[tuple] = []
    while i > 0 and len(picked) < window:
        i -= 1
        if rows[i][1] != game_id:
            picked.append(rows[i])
    return picked[::-1]


def prior_form(
    rows: Sequence[tuple], creation_utc: str, game_id: int, window: int, min_games: int
) -> Optional[Tuple[float, float]]:
    """(taux de victoire, KDA) sur les `window` parties antérieures, None sous `min_games`.

    KDA = (Σkills + Σassists) / max(Σdeaths, 1), comme `form.form`. `rows` : voir `load_histories`.
    """
    picked = _prior(rows, creation_utc, game_id, window)
    if not picked or len(picked) < min_games:
        return None
    kills_assists = sum(r[3] + r[5] for r in picked)
    deaths = sum(r[4] for r in picked)
    return mean(r[2] for r in picked), kills_assists / max(deaths, 1)


def team_value(values: Dict[int, Optional[float]], teams: Dict[int, int]) -> float:
    """Moyenne bleu − moyenne rouge sur 5 joueurs, chacun centré sur la moyenne des joueurs connus ;
    inconnu = 0. 0 si personne n'est connu."""
    known = [v for v in values.values() if v is not None]
    if not known:
        return 0.0
    centre = mean(known)

    def side(team: int) -> float:
        return (
            sum(
                (v - centre) if v is not None else 0.0
                for p, v in values.items()
                if teams[p] == team
            )
            / TEAM_SIZE
        )

    return side(BLUE) - side(RED)


def load_game_points(
    db: sqlite3.Connection,
    model: WinModel,
    histories: Dict[str, List[tuple]],
    limit: Optional[int],
) -> Tuple[List[Game], Dict[str, int]]:
    """Parcourt les parties lues, de la plus ancienne à la plus récente, et rend les parties retenues
    et les compteurs (lues, illisibles, hors filtre). `limit` : les plus récentes, au plus."""
    total = db.execute("SELECT COUNT(*) FROM crawl_games WHERE read_utc IS NOT NULL").fetchone()[0]
    selected = min(total, limit) if limit else total
    keep = min(1.0, cfg.WINPROB_MAX_ROWS / max(1, selected * STATES_PER_GAME))
    rng = random.Random(0)  # même graine que train.games
    window, min_games = cfg.SCOUT_BADGE_WINDOW, cfg.SCOUT_MIN_IMPACT_GAMES
    rows = db.execute(
        "SELECT raw, game_id, game_creation_utc FROM ("
        "SELECT raw, game_id, game_creation_utc FROM crawl_games WHERE read_utc IS NOT NULL "
        "ORDER BY game_creation_utc DESC, game_id DESC LIMIT ?) "
        "ORDER BY game_creation_utc, game_id",
        (limit if limit else -1,),
    )
    points: Dict[str, List[tuple]] = defaultdict(list)  # puuid -> (création, id, points)
    games: List[Game] = []
    counts = {"lues": 0, "illisibles": 0, "hors_filtre": 0}
    began = time.monotonic()
    for raw, game_id, creation in rows:
        counts["lues"] += 1
        if counts["lues"] % PROGRESS_EVERY == 0:
            print(f"[INFO] {counts['lues']} parties en {time.monotonic() - began:.0f} s")
        try:
            packed = unpack(raw)
            game, timeline = packed["game"], packed["timeline"]
            win = blue_win(game)
            if (
                not (timeline or {}).get("frames")
                or win is None
                or game.get("gameDuration", 0) < 300
            ):
                counts["hors_filtre"] += 1
                continue
            puuid_of = {
                i["participantId"]: (i.get("player") or {}).get("puuid")
                for i in game.get("participantIdentities") or []
            }
            teams = {p["participantId"]: p["teamId"] for p in game["participants"]}

            wr, kda, imp, covered_players = {}, {}, {}, 0
            for pid in teams:
                puuid = puuid_of.get(pid)
                if not puuid:
                    continue
                form = prior_form(histories.get(puuid, []), creation, game_id, window, min_games)
                if form:
                    wr[pid], kda[pid] = form
                picked = _prior(points.get(puuid, []), creation, game_id, window)
                covered_players += len(picked) >= cfg.FORM_IMPACT_MIN_GAMES
                if len(picked) >= min_games:
                    imp[pid] = mean(r[2] for r in picked)
            candidates = {
                "form_wr": team_value({p: wr.get(p) for p in teams}, teams),
                "form_kda": team_value({p: kda.get(p) for p in teams}, teams),
                "form_impact": team_value({p: imp.get(p) for p in teams}, teams),
            }
            states = [s for s in frame_states(game, timeline) if rng.random() < keep]
            for s in states:
                s.update(candidates)

            # Impacts de cette partie, rangés après sa forme (elle n'entre pas dans la sienne).
            totals: Dict[int, float] = defaultdict(float)
            for row in impacts(model, game, timeline, participant_roles(game))["rows"]:
                totals[row["participant_id"]] += row["delta_p"]
            for pid, puuid in puuid_of.items():
                if puuid:
                    points[puuid].append((creation, game_id, 100 * totals[pid]))

            games.append(
                Game(
                    states=states,
                    win=int(win),
                    covered=covered_players >= cfg.FORM_IMPACT_MIN_PLAYERS,
                )
            )
        except Exception:  # pylint: disable=broad-exception-caught
            counts["illisibles"] += 1  # partie illisible : ignorée, comme dans l'éclaireur
    print(
        f"[DATA] {counts['lues']} parties lues ({counts['illisibles']} illisibles, "
        f"{counts['hors_filtre']} hors filtre) en {time.monotonic() - began:.0f} s, "
        f"{len(games)} retenues"
    )
    return games, counts


def _pooled(parts: Sequence[Game], folds: int, inputs: Sequence[str]) -> List[Point]:
    """Prédictions poolées de la validation croisée à blocs contigus de parties (SPEC-20 §4.3)."""
    n, pooled = len(parts), []
    for k in range(folds):
        lo, hi = k * n // folds, (k + 1) * n // folds
        rest = parts[:lo] + parts[hi:]
        model = fit(
            [s for g in rest for s in g.states], [g.win for g in rest for _ in g.states], inputs
        )
        pooled += [(model.predict(s), g.win, s["time_min"]) for g in parts[lo:hi] for s in g.states]
    return pooled


def _auc(rows: Sequence[Tuple[float, int]]) -> Optional[float]:
    """Aire sous la courbe ROC par les rangs (ex æquo moyennés) ; None sans les deux issues."""
    n_pos = sum(y for _, y in rows)
    n_neg = len(rows) - n_pos
    if not n_pos or not n_neg:
        return None
    rank_sum, i = 0.0, 0
    while i < len(rows):
        j = i
        while j + 1 < len(rows) and rows[j + 1][0] == rows[i][0]:
            j += 1
        rank_sum += ((i + j) / 2 + 1) * sum(y for _, y in rows[i : j + 1])
        i = j + 1
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def metrics(pooled: Sequence[Point]) -> dict:
    """Brier (toutes les images, et jusqu'à FORM_EARLY_MIN minutes), écart max par décile, AUC."""
    rows = sorted((p, y) for p, y, _ in pooled)
    early = [(p, y) for p, y, minute in pooled if minute <= cfg.FORM_EARLY_MIN]
    n, gaps = len(rows), []
    for k in range(10):
        decile = rows[k * n // 10 : (k + 1) * n // 10]
        if decile:
            gaps.append(abs(sum(p for p, _ in decile) - sum(y for _, y in decile)) / len(decile))
    return {
        "images": n,
        "brier": brier_score(rows),
        "brier_early": brier_score(early) if early else float("nan"),
        "max_gap": max(gaps),
        "auc": _auc(rows),
    }


def decide(base: dict, cand: dict) -> bool:
    """Adopté si le Brier ≤ FORM_EARLY_MIN minutes gagne au moins FORM_BRIER_GAIN_MIN et si l'écart
    par décile reste sous WINPROB_GAP_MAX sur toutes les images."""
    gain = base["brier_early"] - cand["brier_early"]
    return gain >= cfg.FORM_BRIER_GAIN_MIN and cand["max_gap"] <= cfg.WINPROB_GAP_MAX


def _line(label: str, m: dict, games: int) -> str:
    auc = "n/a" if m["auc"] is None else f"{m['auc']:.3f}"
    return (
        f"[DATA] {label} : Brier {m['brier']:.4f}, Brier <= {cfg.FORM_EARLY_MIN:g} min "
        f"{m['brier_early']:.4f}, écart max {m['max_gap'] * 100:.1f} pts, AUC {auc}, "
        f"{games} parties, {m['images']} images"
    )


def _decision(name: str, base: dict, cand: dict) -> None:
    adopted = decide(base, cand)
    gain = base["brier_early"] - cand["brier_early"]
    print(
        f"[DATA] Décision {name} : {'ADOPTÉ' if adopted else 'REFUSÉ'} "
        f"(gain <= {cfg.FORM_EARLY_MIN:g} min {gain:+.4f}, seuil {cfg.FORM_BRIER_GAIN_MIN}, "
        f"écart max {cand['max_gap'] * 100:.1f} pts, seuil {cfg.WINPROB_GAP_MAX * 100:.0f})"
    )


def main() -> None:
    """Attente si la base est peu couverte (sans --force), sinon validation croisée et décisions."""
    args = _parse_args()
    path = Path(args.db_path)
    if not path.exists():
        print(f"[ERREUR] Pas de base de collecte : {path}")
        raise SystemExit(1)
    db = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=cfg.FORM_DB_TIMEOUT_S)
    covered = {
        p: covered_games(db, p, cfg.SCOUT_MIN_IMPACT_GAMES)
        for p in sorted({10, cfg.FORM_COVERED_PLAYERS, 5}, reverse=True)
    }
    print(
        "[DATA] Couverture (parties lues, joueurs ayant la partie et des parties antérieures) : "
        + ", ".join(f"{p} joueurs {n}" for p, n in covered.items())
    )
    done = covered[cfg.FORM_COVERED_PLAYERS]
    if done < cfg.FORM_MIN_COVERED_GAMES and not args.force:
        db.close()
        print(f"[INFO] Mesure en attente : couverture {done} / {cfg.FORM_MIN_COVERED_GAMES}")
        return

    model = load_model()
    if model is None:
        db.close()
        print("[ERREUR] Pas de modèle de win chance : python -m src.winprob.retrain --force")
        raise SystemExit(1)
    began = time.monotonic()
    histories = load_histories(db)
    print(
        f"[INFO] {sum(map(len, histories.values()))} parties d'historique, {len(histories)} joueurs"
    )
    games, _ = load_game_points(db, model, histories, args.limit)
    db.close()
    folds = cfg.FORM_CV_FOLDS
    if len(games) < folds:
        print(f"[ALERTE] {len(games)} parties retenues, moins de {folds} blocs : pas de mesure.")
        return

    base = metrics(_pooled(games, folds, INPUTS))
    print(_line("Modèle en place", base, len(games)))
    for name in ("form_wr", "form_kda"):
        cand = metrics(_pooled(games, folds, INPUTS + (name,)))
        print(_line(f"Modèle + {name}", cand, len(games)))
        _decision(name, base, cand)

    subset = [g for g in games if g.covered]
    if len(subset) < folds:
        print(
            f"[ALERTE] Sous-ensemble couvert : {len(subset)} parties, pas de mesure de form_impact."
        )
    else:
        print(
            "[INFO] form_impact : sous-ensemble couvert, biais connu : les impacts viennent du "
            "modèle en place, entraîné sur ces parties."
        )
        base_sub = metrics(_pooled(subset, folds, INPUTS))
        cand_sub = metrics(_pooled(subset, folds, INPUTS + ("form_impact",)))
        print(_line("Sous-ensemble, modèle en place", base_sub, len(subset)))
        print(_line("Sous-ensemble, modèle + form_impact", cand_sub, len(subset)))
        _decision("form_impact", base_sub, cand_sub)
    print(f"[INFO] Mesure en {time.monotonic() - began:.0f} s")


if __name__ == "__main__":
    main()
