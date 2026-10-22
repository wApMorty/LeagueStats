"""Mesure du terme de maîtrise personnelle (SPEC-41 §4.3, tâche 199).

Lit `crawl.db` (parties de tiers, lues) et `db.db` (tables LoLalytics, parties de @pj35) en lecture
seule. Pour chaque joueur focal (au moins `MASTERY_STUDY_MIN_GAMES` parties lues), sa maîtrise du
champion joué est tirée de son impact ΔP (SPEC-20) sur ses AUTRES parties, puis on teste si elle prédit
la victoire au-delà du logit de draft (`GameEvaluator`). Validation croisée à 5 blocs de joueurs,
IC95 par bootstrap sur les joueurs, seuil de SPEC-41 §2 figé avant la mesure. Références : (a)
écart à la moyenne du joueur, (b) le même moins la norme ΔP du champion, (c) l'impact relatif aux
coéquipiers de la partie (le sien moins leur moyenne), (d) l'impact relatif à l'adversaire de lane.
SPEC-42 : (e) interaction avec le matchup de lane (M × lane), (f) écart D de la case (champion,
vis-à-vis de lane) avec son K₂ propre, (g) e et f ensemble. Aucune écriture.

USAGE:
    python scripts/measure_mastery_term.py                 # mesure complète (~35 min)
    python scripts/measure_mastery_term.py --limit 5000    # 5 000 parties lues les plus récentes
"""

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
import time
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from statistics import median
from typing import Dict, List, Optional, Sequence, Set, Tuple

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.measure_moneyball import _has_player, _open_ro, _player_puuids
from src.analysis.calibration import brier_score
from src.analysis.game_eval import GameEvaluator
from src.analysis.mastery import (
    ci95,
    decide,
    fit_logistic,
    leave_one_out_points,
    leave_one_out_matchup_deviation,
    masteries,
    matchup_deviations,
    matchup_shrink_k,
    player_bootstrap,
    player_mean_bootstrap,
    pooled_shrink_k,
    predict_logistic,
    shrink_k,
)
from src.coaching.metrics import participant_roles
from src.config import config
from src.config_constants import analysis_config as cfg
from src.db import Database
from src.repositories.coaching import CoachingRepository
from src.winprob.crawl import unpack
from src.winprob.impact import impacts
from src.winprob.model import WinModel
from src.winprob.state import BLUE, blue_win
from src.winprob.train import crawl_path, load_model

PROGRESS_EVERY = 5000
VARIANTS = ("a", "b", "c", "d", "e", "f", "g")
# La valeur de partie lue par chaque variante (b retranche en plus la norme du champion).
VALUE_OF = {
    "a": "points",
    "b": "points",
    "c": "team_rel",
    "d": "lane_rel",
    "e": "points",
    "f": "points",
    "g": "points",
}
# Variante dont le K sert à la maîtrise de chaque variante (e, f, g reprennent celui de a).
K_SOURCE = {"a": "a", "b": "b", "c": "c", "d": "d", "e": "a", "f": "a", "g": "a"}
# Variantes qui ajoutent le terme de matchup D, au K₂ de la population.
MATCHUP_VARIANTS = ("f", "g")
# Indices des coefficients que `decide` contrôle (SPEC-42 §2) : tout ce qui suit le biais, le draft
# et la maîtrise M.
NEW_COEFFICIENTS = {
    "a": (2,),
    "b": (2,),
    "c": (2,),
    "d": (2,),
    "e": (3,),
    "f": (3,),
    "g": (3, 4),
}
# Libellés des termes ajoutés (indices 3 et suivants), dans l'ordre des colonnes (`_columns`).
TERM_LABELS = {"e": ("M × lane",), "f": ("D",), "g": ("M × lane", "D")}
# Constantes du moteur (§4.4) : nom et indice du coefficient mesuré.
TERM_CONSTANTS = {
    "e": (("MASTERY_LANE_INTERACTION", 3),),
    "f": (("MASTERY_OPPONENT_LOGIT_PER_POINT", 3),),
    "g": (("MASTERY_LANE_INTERACTION", 3), ("MASTERY_OPPONENT_LOGIT_PER_POINT", 4)),
}


@dataclass(frozen=True)
class Row:
    """Un participant d'une partie retenue."""

    puuid: str
    game: int  # rang de la partie dans la lecture, du plus récent au plus ancien
    champion: str
    win: int
    points: float  # 100 × Σ ΔP de ses lignes d'impact
    draft: float  # logit de draft de son équipe
    team_rel: float = 0.0  # points moins la moyenne de ses 4 coéquipiers (variante c)
    lane_rel: float = 0.0  # points moins ceux de son adversaire de lane (variante d)
    opponent: Optional[str] = None  # champion de son vis-à-vis de lane, None sans vis-à-vis unique
    lane: float = 0.0  # matchup_logit de sa paire de lane contre ce vis-à-vis (0 sans vis-à-vis)


def lane_opponents(
    team_of: Dict[int, int], roles: Dict[int, Optional[str]]
) -> Dict[int, Optional[int]]:
    """participantId -> l'unique participant de l'autre équipe au même poste, None s'il n'y en a pas
    exactement un (poste inconnu compris)."""
    out: Dict[int, Optional[int]] = {}
    for pid, team in team_of.items():
        rivals = [
            q
            for q, t in team_of.items()
            if t != team and roles.get(q) is not None and roles.get(q) == roles.get(pid)
        ]
        out[pid] = rivals[0] if len(rivals) == 1 else None
    return out


def relative_values(
    points: Dict[int, float], team_of: Dict[int, int], roles: Dict[int, Optional[str]]
) -> Dict[int, Tuple[float, float]]:
    """participantId -> (impact moins la moyenne des coéquipiers, impact moins l'adversaire de lane).

    Ramène l'impact à la partie : un +5 quand ses coéquipiers font +20 vaut −15 relatif. Sans
    adversaire de même poste, l'écart de lane vaut 0.
    """
    opponents = lane_opponents(team_of, roles)
    out: Dict[int, Tuple[float, float]] = {}
    for pid, team in team_of.items():
        mates = [points.get(q, 0.0) for q, t in team_of.items() if t == team and q != pid]
        opponent = opponents[pid]
        own = points.get(pid, 0.0)
        team_rel = own - sum(mates) / len(mates) if mates else 0.0
        lane_rel = own - points.get(opponent, 0.0) if opponent is not None else 0.0
        out[pid] = (team_rel, lane_rel)
    return out


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SPEC-41 : mesure du terme de maîtrise")
    parser.add_argument("--crawl-path", default=str(crawl_path()))
    parser.add_argument("--db-path", default=config.DATABASE_PATH)
    parser.add_argument(
        "--limit", type=int, default=None, help="parties les plus récentes, au plus"
    )
    parser.add_argument("--seed", type=int, default=cfg.MASTERY_STUDY_SEED)
    return parser.parse_args()


def _game_rows(
    index: int, game: dict, timeline: dict, model: WinModel, names: Dict[int, str], evaluator
) -> Optional[List[Row]]:
    """Les dix participants d'une partie, ou None si elle sort du filtre (issue, postes, puuid)."""
    win = blue_win(game)
    roles = participant_roles(game)
    if win is None or not (timeline or {}).get("frames") or None in roles.values():
        return None
    puuid_of = {
        i["participantId"]: (i.get("player") or {}).get("puuid")
        for i in game.get("participantIdentities") or []
    }
    if len(roles) != 10 or not all(puuid_of.get(pid) for pid in roles):
        return None
    points: Dict[int, float] = defaultdict(float)
    for row in impacts(model, game, timeline, roles)["rows"]:
        points[row["participant_id"]] += 100 * row["delta_p"]
    team_of = {p["participantId"]: p["teamId"] for p in game["participants"]}
    champion_of = {
        p["participantId"]: names.get(p["championId"], str(p["championId"]))
        for p in game["participants"]
    }
    blue = [(champion_of[pid], roles[pid]) for pid in roles if team_of[pid] == BLUE]
    red = [(champion_of[pid], roles[pid]) for pid in roles if team_of[pid] != BLUE]
    blue_logit = evaluator.team_logit(blue, red)  # antisymétrique : le rouge vaut l'opposé
    relative = relative_values(points, team_of, roles)
    opponents = lane_opponents(team_of, roles)
    rows = []
    for pid in roles:
        opponent = opponents[pid]
        rows.append(
            Row(
                puuid=puuid_of[pid],
                game=index,
                champion=champion_of[pid],
                win=int(win) if team_of[pid] == BLUE else 1 - int(win),
                points=points[pid],
                draft=blue_logit if team_of[pid] == BLUE else -blue_logit,
                team_rel=relative[pid][0],
                lane_rel=relative[pid][1],
                opponent=champion_of[opponent] if opponent is not None else None,
                lane=(
                    evaluator.matchup_logit(
                        (champion_of[pid], roles[pid]), (champion_of[opponent], roles[opponent])
                    )
                    if opponent is not None
                    else 0.0
                ),
            )
        )
    return rows


def read_rows(
    crawl_db: sqlite3.Connection,
    limit: Optional[int],
    puuids: Set[str],
    model: WinModel,
    names: Dict[int, str],
    evaluator,
    counts: Dict[str, int],
) -> List[Row]:
    """Participants des parties lues de `crawl.db` en SoloQ, sans les parties de @pj35."""
    placeholders = ",".join("?" * len(cfg.MASTERY_QUEUE_IDS))
    query = (
        f"SELECT raw FROM crawl_games WHERE read_utc IS NOT NULL AND queue_id IN ({placeholders}) "
        "ORDER BY game_creation_utc DESC, game_id DESC LIMIT ?"
    )
    rows: List[Row] = []
    began = time.monotonic()
    for (raw,) in crawl_db.execute(query, (*cfg.MASTERY_QUEUE_IDS, limit if limit else -1)):
        counts["lues"] += 1
        if counts["lues"] % PROGRESS_EVERY == 0:
            print(f"[INFO] {counts['lues']} parties en {time.monotonic() - began:.0f} s")
        try:
            packed = unpack(raw)
            game, timeline = packed["game"], packed["timeline"]
            if _has_player(game, puuids):
                counts["exclues"] += 1
                continue
            game_rows = _game_rows(counts["lues"], game, timeline, model, names, evaluator)
        except Exception:  # pylint: disable=broad-exception-caught
            counts["illisibles"] += 1  # partie illisible : ignorée, comme measure_moneyball
            continue
        if game_rows is None:
            counts["hors_filtre"] += 1
            continue
        counts["retenues"] += 1
        rows.extend(game_rows)
    print(
        f"[DATA] {counts['lues']} parties lues ({counts['illisibles']} illisibles, "
        f"{counts['exclues']} exclues (@pj35 y joue), {counts['hors_filtre']} hors filtre), "
        f"{counts['retenues']} retenues en {time.monotonic() - began:.0f} s"
    )
    return rows


def _fold(puuid: str) -> int:
    """Bloc stable d'un joueur : un joueur n'est jamais à la fois en entraînement et en test."""
    return zlib.crc32(puuid.encode("utf-8")) % cfg.MASTERY_STUDY_FOLDS


def champion_norms(rows: Sequence[Row]) -> Dict[str, float]:
    """ΔP moyen par champion, tous participants confondus (variante b)."""
    sums: Dict[str, float] = defaultdict(float)
    counts: Dict[str, int] = defaultdict(int)
    for row in rows:
        sums[row.champion] += row.points
        counts[row.champion] += 1
    return {champion: sums[champion] / counts[champion] for champion in sums}


def _by_player(rows: Sequence[Row]) -> Dict[str, List[Row]]:
    grouped: Dict[str, List[Row]] = defaultdict(list)
    for row in rows:
        grouped[row.puuid].append(row)
    return grouped


def estimate_k(
    by_player: Dict[str, List[Row]], norms: Optional[Dict[str, float]], field: str = "points"
) -> Optional[float]:
    """K de la population : variance entre champions à l'intérieur de chaque joueur, regroupée.

    `field` : la valeur de partie de la variante (`VALUE_OF`)."""
    offsets = norms or {}
    players = []
    for games in by_player.values():
        groups: Dict[str, List[float]] = defaultdict(list)
        for row in games:
            groups[row.champion].append(getattr(row, field) - offsets.get(row.champion, 0.0))
        players.append(groups)
    return pooled_shrink_k(players)


def offsets_of(
    by_player: Dict[str, List[Row]],
    k: float,
    norms: Optional[Dict[str, float]],
    field: str = "points",
) -> Dict[Tuple[str, int], float]:
    """(joueur, partie) -> maîtrise du champion joué, calculée sans cette partie."""
    out: Dict[Tuple[str, int], float] = {}
    for puuid, games in by_player.items():
        points = leave_one_out_points([(r.champion, getattr(r, field)) for r in games], k, norms)
        for row, value in zip(games, points):
            out[(puuid, row.game)] = value
    return out


def estimate_k2(by_player: Dict[str, List[Row]]) -> Optional[float]:
    """K₂ de la maîtrise par matchup : variance entre adversaires de lane à l'intérieur de chaque
    (joueur, champion), regroupée. Valeurs en points, vis-à-vis None écartés."""
    cells: List[Dict[str, List[float]]] = []
    for games in by_player.values():
        per_champion: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        for row in games:
            if row.opponent is not None:
                per_champion[row.champion][row.opponent].append(row.points)
        cells.extend(per_champion.values())
    return matchup_shrink_k(cells)


def matchup_offsets_of(by_player: Dict[str, List[Row]], k2: float) -> Dict[Tuple[str, int], float]:
    """(joueur, partie) -> écart D de la case (champion, vis-à-vis) calculé sans cette partie."""
    out: Dict[Tuple[str, int], float] = {}
    for puuid, games in by_player.items():
        devs = leave_one_out_matchup_deviation(
            [(r.champion, r.opponent, r.points) for r in games], k2
        )
        for row, value in zip(games, devs):
            out[(puuid, row.game)] = value
    return out


def _offsets(
    by_player: Dict[str, List[Row]],
    variant: str,
    k: float,
    k2: Optional[float],
    norms: Optional[Dict[str, float]],
) -> Dict[Tuple[str, int], Tuple[float, float]]:
    """(joueur, partie) -> (maîtrise M, écart D), chacun calculé sans la partie elle-même."""
    value = offsets_of(by_player, k, norms, VALUE_OF[variant])
    dev = matchup_offsets_of(by_player, k2) if variant in MATCHUP_VARIANTS else {}
    return {key: (m, dev.get(key, 0.0)) for key, m in value.items()}


def _columns(variant: str, row: Row, m: float, d: float) -> List[float]:
    """Colonnes de régression d'une ligne focale (SPEC-42 §4.2.2) : biais, draft, puis les termes de
    la variante. `m` : maîtrise (celle de a pour e, f, g), `d` : écart de matchup (f, g)."""
    columns = [1.0, row.draft, m]
    if variant == "e":
        return columns + [m * row.lane]
    if variant == "f":
        return columns + [d]
    if variant == "g":
        return columns + [m * row.lane, d]
    return columns


@dataclass
class Pooled:
    """Prédictions hors bloc, une par ligne focale."""

    players: List[str]
    wins: List[int]
    base: List[float]
    variants: Dict[str, List[float]]
    ks: Dict[str, List[float]]
    k2s: List[float]


def cross_validate(rows: Sequence[Row], focal: Set[str]) -> Optional[Pooled]:
    """Validation croisée à blocs de joueurs : draft seule contre draft + maîtrise (a à g).

    K est estimé une fois par bloc pour a à d ; e, f, g reprennent celui de a, K₂ est estimé une fois.
    """
    pooled = Pooled([], [], [], {v: [] for v in VARIANTS}, {v: [] for v in VARIANTS}, [])
    for fold in range(cfg.MASTERY_STUDY_FOLDS):
        train_all = [r for r in rows if _fold(r.puuid) != fold]
        focal_rows = [r for r in rows if r.puuid in focal]
        train = _by_player([r for r in focal_rows if _fold(r.puuid) != fold])
        test = _by_player([r for r in focal_rows if _fold(r.puuid) == fold])
        if not train or not test:
            print(f"[ALERTE] Bloc {fold} vide : validation croisée impossible.")
            return None
        norms = champion_norms(train_all)
        train_rows = [r for games in train.values() for r in games]
        test_rows = [r for games in test.values() for r in games]
        base = fit_logistic([[1.0, r.draft] for r in train_rows], [r.win for r in train_rows])
        pooled.base.extend(predict_logistic(base, [1.0, r.draft]) for r in test_rows)
        pooled.players.extend(r.puuid for r in test_rows)
        pooled.wins.extend(r.win for r in test_rows)
        ks = {v: estimate_k(train, norms if v == "b" else None, VALUE_OF[v]) for v in "abcd"}
        k2 = estimate_k2(train)
        if k2 is not None:
            pooled.k2s.append(k2)
        for variant in VARIANTS:
            k = ks[K_SOURCE[variant]]
            if k is None or (variant in MATCHUP_VARIANTS and k2 is None):
                print(f"[INFO] Variante {variant}, bloc {fold} : tau2 <= 0, terme nul.")
                pooled.variants[variant].extend(pooled.base[-len(test_rows) :])
                continue
            pooled.ks[variant].append(k)
            variant_norms = norms if variant == "b" else None
            train_off = _offsets(train, variant, k, k2, variant_norms)
            test_off = _offsets(test, variant, k, k2, variant_norms)
            coef = fit_logistic(
                [_columns(variant, r, *train_off[(r.puuid, r.game)]) for r in train_rows],
                [r.win for r in train_rows],
            )
            pooled.variants[variant].extend(
                predict_logistic(coef, _columns(variant, r, *test_off[(r.puuid, r.game)]))
                for r in test_rows
            )
    return pooled


def choose(
    adopted: Dict[str, Tuple[float, List[float]]],
    gains: Dict[str, List[float]],
    players: Sequence[str],
    seed: int,
) -> Optional[str]:
    """La variante retenue parmi celles qui passent le seuil : a, la référence de SPEC-41 §8, sauf si
    une autre la bat significativement (IC95 de son gain moins celui de a entièrement positif) ;
    entre plusieurs qui la battent, le plus grand gain moyen. Sans a adoptée, le plus grand gain."""
    others = [v for v in adopted if v != "a"]
    if "a" not in adopted:
        return max(others, key=lambda v: sum(gains[v]), default=None)
    better = []
    for variant in others:
        diff = [gv - ga for ga, gv in zip(gains["a"], gains[variant])]
        low, high = ci95(player_mean_bootstrap(players, diff, cfg.MASTERY_STUDY_BOOTSTRAP, seed))
        print(f"[DATA] Gain {variant} - a : IC95 [{low:+.5f} ; {high:+.5f}]")
        if low > 0:
            better.append(variant)
    return max(better, key=lambda v: sum(gains[v])) if better else "a"


def _squared_errors(probs: Sequence[float], wins: Sequence[int]) -> List[float]:
    return [(p - y) ** 2 for p, y in zip(probs, wins)]


def full_fit(
    rows: Sequence[Row], focal: Set[str], variant: str, seed: int
) -> Optional[Tuple[float, Optional[float], List[float], List[Tuple[float, float]], int]]:
    """Sur tout l'échantillon : K, K₂ (f et g seulement), coefficients, IC95 bootstrap de chaque
    coefficient d'indice ≥ 2, et nombre de lignes focales à D ≠ 0."""
    by_player = _by_player([r for r in rows if r.puuid in focal])
    norms = champion_norms(rows) if variant == "b" else None
    k = estimate_k(by_player, norms, VALUE_OF[variant])
    k2 = estimate_k2(by_player) if variant in MATCHUP_VARIANTS else None
    if k is None or (variant in MATCHUP_VARIANTS and k2 is None):
        return None
    off = _offsets(by_player, variant, k, k2, norms)
    focal_rows = [r for games in by_player.values() for r in games]
    keys = [(r.puuid, r.game) for r in focal_rows]
    xs = [_columns(variant, r, *off[key]) for r, key in zip(focal_rows, keys)]
    ys = [r.win for r in focal_rows]
    coef = fit_logistic(xs, ys)
    draws = player_bootstrap(
        [r.puuid for r in focal_rows], xs, ys, coef, cfg.MASTERY_STUDY_BOOTSTRAP, seed
    )
    cis = [ci95([c[i] for c in draws]) for i in range(2, len(coef))]
    n_dev = sum(1 for key in keys if off[key][1] != 0.0)
    return k, k2, coef, cis, n_dev


def _own_games(game_db: sqlite3.Connection, names: Dict[int, str]) -> List[Tuple[str, float]]:
    """Parties SoloQ de @pj35 : (champion, 100 × Σ ΔP de ses lignes d'impact)."""
    repository = CoachingRepository(SimpleNamespace(connection=game_db))
    return [
        (names.get(cid, str(cid)), points)
        for cid, points in repository.player_champion_impacts(cfg.MASTERY_QUEUE_IDS)
    ]


def _own_relative(game_db: sqlite3.Connection, names: Dict[int, str]) -> Dict[str, list]:
    """Parties SoloQ de @pj35 en impact relatif : `team_rel` et `lane_rel` -> (champion, valeur), et
    `matchups` -> (champion, vis-à-vis de lane ou None, points)."""
    points: Dict[Tuple[int, int], float] = defaultdict(float)
    for game_id, pid, delta in game_db.execute(
        "SELECT game_id, participant_id, delta_p FROM game_impact"
    ):
        points[(game_id, pid)] += 100 * delta
    out: Dict[str, list] = {"team_rel": [], "lane_rel": [], "matchups": []}
    query = (
        "SELECT game_id, queue_id, player_participant_id, raw_game, raw_eog FROM game_records "
        "ORDER BY game_creation_utc"
    )
    for game_id, queue_id, player, raw_game, raw_eog in game_db.execute(query):
        if queue_id not in cfg.MASTERY_QUEUE_IDS or (game_id, player) not in points:
            continue
        game = json.loads(raw_game)
        team_of = {p["participantId"]: p["teamId"] for p in game["participants"]}
        roles = participant_roles(game, json.loads(raw_eog) if raw_eog else None)
        game_points = {pid: points.get((game_id, pid), 0.0) for pid in team_of}
        team_rel, lane_rel = relative_values(game_points, team_of, roles)[player]
        champion_of = {
            p["participantId"]: names.get(p["championId"], str(p["championId"]))
            for p in game["participants"]
        }
        opponent = lane_opponents(team_of, roles)[player]
        champion = champion_of[player]
        out["team_rel"].append((champion, team_rel))
        out["lane_rel"].append((champion, lane_rel))
        out["matchups"].append(
            (
                champion,
                champion_of[opponent] if opponent is not None else None,
                game_points[player],
            )
        )
    return out


def _print_own(own: List[Tuple[str, float]], k_population: Optional[float]) -> None:
    """Le K de @pj35 et sa table, rétrécie avec le K de la population (celui du moteur)."""
    groups: Dict[str, List[float]] = defaultdict(list)
    for champion, points in own:
        groups[champion].append(points)
    k_own = shrink_k(groups)
    own_text = "tau2 <= 0" if k_own is None else f"{k_own:.1f}"
    print(f"[DATA] @pj35 : {len(own)} parties SoloQ avec impact, K propre {own_text}")
    if not own or k_population is None:
        return
    table = masteries(own, k_population)
    for mastery in sorted(table.values(), key=lambda m: -m.games):
        print(
            f"[DATA]   {mastery.champion:<14} {mastery.games:>3} parties  "
            f"brut {mastery.raw_points:+6.1f}  rétréci {mastery.points:+5.1f} pts"
        )


def _print_own_matchups(matchups: List[Tuple[str, Optional[str], float]], k2: float) -> None:
    """La table de @pj35 par matchup : les cases à 2 parties ou plus, triées par |D|."""
    table = matchup_deviations(matchups, k2)
    cells = sorted(
        ((cell, n, d) for cell, (n, d) in table.items() if n >= 2), key=lambda c: -abs(c[2])
    )
    for (champion, opponent), n, d in cells:
        print(f"[DATA]   {champion} contre {opponent:<14} {n:>3} parties  D {d:+6.1f} pts")


def main() -> None:
    """Lecture, validation croisée, ajustement complet, décision, puis la table de @pj35."""
    args = _parse_args()
    crawl_db = _open_ro(Path(args.crawl_path))
    game_db = _open_ro(Path(args.db_path))
    model = load_model()
    if model is None:
        print(
            "[ERREUR] Pas de modèle de win chance (data/winprob_model.json) : impacts impossibles."
        )
        return
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "db.db"
        shutil.copy2(
            args.db_path, copy
        )  # l'évaluateur passe par Database : jamais sur la vraie base
        db = Database(str(copy))
        db.connect()
        try:
            names = db.get_all_champion_names()
            evaluator = GameEvaluator(db)
            puuids = _player_puuids(game_db)
            counts = {"lues": 0, "illisibles": 0, "exclues": 0, "hors_filtre": 0, "retenues": 0}
            rows = read_rows(crawl_db, args.limit, puuids, model, names, evaluator, counts)
            own = _own_games(game_db, names)
            own_relative = _own_relative(game_db, names)
        finally:
            db.close()
            crawl_db.close()
            game_db.close()

    games_per_player = Counter(r.puuid for r in rows)
    focal = {p for p, n in games_per_player.items() if n >= cfg.MASTERY_STUDY_MIN_GAMES}
    focal_rows = sum(games_per_player[p] for p in focal)
    print(
        f"[DATA] {len(games_per_player)} joueurs, {len(focal)} focaux "
        f"(>= {cfg.MASTERY_STUDY_MIN_GAMES} parties lues), {focal_rows} lignes de prédiction"
    )
    print(
        "[INFO] Impacts tirés du modèle en place, entraîné sur ces parties (biais marginal : la "
        "maîtrise vient des autres parties du joueur). Deux focaux d'une même partie restent corrélés."
    )
    if len(focal) < cfg.MASTERY_STUDY_FOLDS:
        print("[INFO] Non adopté : trop peu de joueurs focaux pour la validation croisée.")
        _print_own(own, None)
        return

    pooled = cross_validate(rows, focal)
    if pooled is None:
        _print_own(own, None)
        return
    base_err = _squared_errors(pooled.base, pooled.wins)
    base_brier = brier_score(list(zip(pooled.base, pooled.wins)))
    gains: Dict[str, List[float]] = {}
    adopted: Dict[str, Tuple[float, List[float]]] = {}
    k_by_variant: Dict[str, float] = {}
    k2_by_variant: Dict[str, Optional[float]] = {}
    for variant in VARIANTS:
        err = _squared_errors(pooled.variants[variant], pooled.wins)
        gains[variant] = [b - e for b, e in zip(base_err, err)]
        gain_ci = ci95(
            player_mean_bootstrap(
                pooled.players, gains[variant], cfg.MASTERY_STUDY_BOOTSTRAP, args.seed
            )
        )
        brier = brier_score(list(zip(pooled.variants[variant], pooled.wins)))
        fitted = full_fit(rows, focal, variant, args.seed)
        if fitted is None:
            print(f"[DATA] Variante {variant} : tau2 <= 0 sur l'échantillon complet, terme nul.")
            continue
        k, k2, coef, cis, n_dev = fitted
        k_by_variant[variant] = k
        k2_by_variant[variant] = k2
        k_folds = median(pooled.ks[variant]) if pooled.ks[variant] else float("nan")
        print(
            f"[DATA] Variante {variant} : K {k:.1f} (médiane des blocs {k_folds:.1f}), "
            f"b {coef[2]:.4f} logit/pt [{cis[0][0]:.4f} ; {cis[0][1]:.4f}], "
            f"Brier {base_brier:.5f} -> {brier:.5f}, gain {base_brier - brier:+.5f} "
            f"[{gain_ci[0]:+.5f} ; {gain_ci[1]:+.5f}]"
        )
        if k2 is not None:
            k2_folds = median(pooled.k2s) if pooled.k2s else float("nan")
            print(
                f"[DATA]   K₂ {k2:.1f} (médiane des blocs {k2_folds:.1f}), "
                f"{n_dev} lignes focales à D ≠ 0"
            )
        for label, index in zip(TERM_LABELS.get(variant, ()), range(3, len(coef))):
            low, high = cis[index - 2]
            print(f"[DATA]   {label} {coef[index]:.4f} logit/unité [{low:.4f} ; {high:.4f}]")
        if decide([cis[i - 2] for i in NEW_COEFFICIENTS[variant]], gain_ci):
            adopted[variant] = (k, coef)

    choice = choose(adopted, gains, pooled.players, args.seed)
    if choice is None:
        print("[INFO] Non adopté : seuil de SPEC-41 §2 non atteint.")
        _print_own(own, k_by_variant.get("a"))
        return
    k, coef = adopted[choice]
    k2 = k2_by_variant.get(choice)
    line = (
        f"[OK] Adopté (variante {choice}) : MASTERY_LOGIT_PER_POINT = {coef[2]:.4f}, "
        f"MASTERY_K = {k:.1f}"
    )
    for name, index in TERM_CONSTANTS.get(choice, ()):
        line += f", {name} = {coef[index]:.4f}"
    if k2 is not None:
        line += f", MASTERY_OPPONENT_K = {k2:.1f}"
    print(line)
    field = VALUE_OF[choice]
    if choice == "b":
        print("[INFO] Table de @pj35 en variante a : la norme par champion n'est pas retranchée.")
    _print_own(own if field == "points" else own_relative[field], k)
    if k2 is not None:  # f ou g : D est dans le modèle, la table par matchup le montre
        _print_own_matchups(own_relative["matchups"], k2)


if __name__ == "__main__":
    main()
