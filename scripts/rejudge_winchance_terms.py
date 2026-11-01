"""Rejuge deux termes de la win chance au premier étage d'ADR-004 : `form_impact` et l'a priori de draft.

Chaque terme est ajouté au modèle en place (avec son produit par le temps), en validation croisée
poolée à blocs contigus de parties, comme `measure_form_term`. Adoption si l'IC 90 % du gain de Brier
sur les images ≤ `FORM_EARLY_MIN` minutes exclut 0, calibration par décile à l'appui, sans seuil fixe.
Deux IC : bootstrap par partie, et par bloc de temps (les parties d'un même joueur ne sont pas
indépendantes) ; on retient le plus large. Un placebo (signe du terme tiré au hasard par partie) vérifie
que le protocole ne fabrique pas de gain. La puissance sort de l'erreur-type mesurée.

Biais de `form_impact` : les impacts viennent du modèle passé en `--model-path`. Si ses parties
d'entraînement ne sont pas dans la base, le biais n'existe pas. Le script le vérifie, et mesure le même
terme avec un modèle réentraîné sur la base elle-même, pour chiffrer le biais de l'ancienne mesure.

Lecture seule : `crawl.db` en `mode=ro`, ligne par ligne, et `db.db` sur copie. Ce n'est pas un test.

USAGE:
    python scripts/rejudge_winchance_terms.py --crawl-path C --db-path D --model-path M --cache F
"""

import argparse
import math
import pickle
import random
import shutil
import sqlite3
import sys
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist, mean
from typing import Dict, List, Optional, Sequence, Tuple

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.backtest_draft_model import _interval90, select
from scripts.measure_form_term import Game, _pooled, _prior, metrics, team_value
from scripts.measure_moneyball import _open_ro
from src.analysis.game_eval import GameEvaluator
from src.coaching.metrics import participant_roles
from src.config import config
from src.config_constants import analysis_config
from src.config_winprob import winprob_config as cfg
from src.db import Database
from src.winprob.crawl import unpack
from src.winprob.impact import impacts
from src.winprob.model import INPUTS, WinModel, fit
from src.winprob.state import blue_win, frame_states
from src.winprob.train import crawl_path, model_path

PROGRESS_EVERY = 5000
STATES_PER_GAME = 28  # ~28 images par partie, comme train.games
QUINTILES = 5
Z_90 = NormalDist().inv_cdf(0.95)
Z_POWER_80 = NormalDist().inv_cdf(0.80)

Row = Tuple[int, str, int, bytes]  # (game_id, création, file, raw)


@dataclass
class Meta:
    """Ce qu'il faut garder d'une partie retenue pour calculer sa forme, sans relire son JSON."""

    index: int  # rang dans la liste des lignes lues
    game_id: int
    creation: str
    patch: str
    puuid_of: Dict[int, Optional[str]]
    teams: Dict[int, int]
    has_draft: bool


def read_rows(db: sqlite3.Connection, limit: Optional[int]) -> List[Row]:
    """Lignes lues, de la plus ancienne à la plus récente, une requête par ligne : la collecte peut
    écrire entre deux. `limit` : les plus récentes, au plus. `length(raw)` plutôt que `read_utc`, rangé
    après le blob : 5 min de scan (et de verrou) sur 1,7 Go contre quelques secondes."""
    query = (
        "SELECT game_id, game_creation_utc, queue_id FROM crawl_games "
        "WHERE length(raw) > 0 ORDER BY game_creation_utc, game_id"
    )
    keys = db.execute(query).fetchall()
    out: List[Row] = []
    for game_id, creation, queue in keys[-limit:] if limit else keys:
        row = db.execute("SELECT raw FROM crawl_games WHERE game_id = ?", (game_id,)).fetchone()
        if row:  # purgée entre les deux requêtes sinon
            out.append((game_id, creation, queue, row[0]))
    return out


def build_games(rows: Sequence[Row], names: Dict[int, str], evaluator) -> Tuple[List[Game], list]:
    """Parties retenues (mêmes filtres que `measure_form_term`), images tirées comme `train.games`,
    `draft` (logit bleu de `GameEvaluator`, en classées à dix postes connus) posé sur chaque image.
    """
    keep = min(1.0, cfg.WINPROB_MAX_ROWS / max(1, len(rows) * STATES_PER_GAME))
    rng = random.Random(0)
    games: List[Game] = []
    metas: List[Meta] = []
    unreadable = 0
    for index, (game_id, creation, queue, raw) in enumerate(rows):
        try:
            packed = unpack(raw)
            game, timeline = packed["game"], packed["timeline"]
            win = blue_win(game)
            if (
                not (timeline or {}).get("frames")
                or win is None
                or game.get("gameDuration", 0) < 300
            ):
                continue
            states = [s for s in frame_states(game, timeline) if rng.random() < keep]
            _, picked = select(game, names)
            has_draft = picked is not None and queue in analysis_config.BACKTEST_QUEUE_IDS
            draft = evaluator.team_logit(picked.blue, picked.red) if has_draft else 0.0
            for s in states:
                s["draft"] = draft
            puuid_of = {
                i["participantId"]: (i.get("player") or {}).get("puuid")
                for i in game.get("participantIdentities") or []
            }
            teams = {p["participantId"]: p["teamId"] for p in game["participants"]}
            patch = ".".join(str(game.get("gameVersion", "?")).split(".")[:2])
            games.append(Game(states=states, win=int(win), covered=False))
            metas.append(Meta(index, game_id, creation, patch, puuid_of, teams, has_draft))
        except Exception:  # pylint: disable=broad-exception-caught
            unreadable += 1  # partie illisible : ignorée, comme dans l'éclaireur
    print(f"[DATA] {len(rows)} parties lues, {unreadable} illisibles, {len(games)} retenues")
    return games, metas


def add_form(
    games: Sequence[Game], metas: Sequence[Meta], rows: Sequence[Row], model: WinModel, key: str
) -> None:
    """Pose `key` sur les images : `form_impact` de `measure_form_term`, impacts tirés de `model`.
    Marque `covered` (parties à assez de joueurs ayant assez d'impacts antérieurs)."""
    window, min_games = cfg.SCOUT_BADGE_WINDOW, cfg.SCOUT_MIN_IMPACT_GAMES
    points: Dict[str, List[tuple]] = defaultdict(list)  # puuid -> (création, id, points)
    began = time.monotonic()
    for done, (g, m) in enumerate(zip(games, metas), 1):
        if done % PROGRESS_EVERY == 0:
            print(f"[INFO] {key} : {done} parties en {time.monotonic() - began:.0f} s", flush=True)
        known: Dict[int, Optional[float]] = dict.fromkeys(m.teams)
        covered_players = 0
        for pid in m.teams:
            picked = _prior(points.get(m.puuid_of.get(pid), []), m.creation, m.game_id, window)
            covered_players += len(picked) >= cfg.FORM_IMPACT_MIN_GAMES
            if len(picked) >= min_games:
                known[pid] = mean(r[2] for r in picked)
        value = team_value(known, m.teams)
        for s in g.states:
            s[key] = value
        g.covered = covered_players >= cfg.FORM_IMPACT_MIN_PLAYERS

        packed = unpack(rows[m.index][3])
        game, timeline = packed["game"], packed["timeline"]
        totals: Dict[int, float] = defaultdict(float)
        for row in impacts(model, game, timeline, participant_roles(game))["rows"]:
            totals[row["participant_id"]] += row["delta_p"]
        for pid, puuid in m.puuid_of.items():
            if puuid:
                points[puuid].append((m.creation, m.game_id, 100 * totals[pid]))


def add_placebo(games: Sequence[Game], key: str, seed: int) -> str:
    """Pose `<key>_placebo` : le terme, de signe tiré au hasard par partie. Même loi, plus de lien."""
    rng = random.Random(seed)
    name = f"{key}_placebo"
    for g in games:
        sign = rng.choice((-1.0, 1.0))
        for s in g.states:
            s[name] = sign * s[key]
    return name


def cluster_interval(
    pairs: Sequence[Tuple[float, int]], draws: int, seed: int
) -> Tuple[float, float, float]:
    """(erreur-type, borne basse, borne haute à 90 %) d'un gain moyen, bootstrap sur des grappes
    (somme des écarts d'erreur, nombre d'images)."""
    rng = random.Random(seed)
    out = []
    for _ in range(draws):
        sample = rng.choices(pairs, k=len(pairs))
        out.append(sum(d for d, _ in sample) / (sum(n for _, n in sample) or 1))
    center = mean(out)
    se = math.sqrt(sum((v - center) ** 2 for v in out) / (len(out) - 1))
    low, high = _interval90(out)
    return se, low, high


def grouped(deltas: Sequence[Tuple[int, float]], groups: int, n_games: int) -> list:
    """Regroupe (rang de partie, écart d'erreur) en `groups` blocs de parties consécutives."""
    sums, counts = [0.0] * groups, [0] * groups
    for game, delta in deltas:
        block = game * groups // n_games
        sums[block] += delta
        counts[block] += 1
    return [(s, n) for s, n in zip(sums, counts) if n]


def quantile(ranked: Sequence[float], q: float) -> float:
    """Quantile d'une liste triée, au rang le plus proche."""
    return ranked[min(len(ranked) - 1, int(q * len(ranked)))]


def decile_gap(points: Sequence[tuple], seed: int) -> float:
    """Écart max par décile, ex æquo mélangés. `metrics` trie (p, issue) : à la première image tout le
    monde a la même probabilité, les défaites passent devant et une coupe de décile invente 12 pts.
    """
    rows = list(points)
    random.Random(seed).shuffle(rows)
    rows.sort(key=lambda r: r[0])
    n, gaps = len(rows), []
    for k in range(10):
        decile = rows[k * n // 10 : (k + 1) * n // 10]
        if decile:
            gaps.append(abs(sum(r[0] - r[1] for r in decile)) / len(decile))
    return max(gaps)


def power(gain: float, se: float) -> float:
    """Probabilité que la borne basse de l'IC 90 % passe au-dessus de 0 si le vrai gain vaut `gain`."""
    return NormalDist().cdf(gain / se - Z_90)


def report(
    label: str,
    parts: Sequence[Game],
    base: Sequence[tuple],
    cand: Sequence[tuple],
    term: str,
    reference: Optional[float],
) -> None:
    """Brier et calibration, IC 90 % du gain, puissance, ampleur en points sur les images précoces."""
    limit = cfg.FORM_EARLY_MIN
    ids = [i for i, g in enumerate(parts) for _ in g.states]
    values = [s[term] for g in parts for s in g.states]
    early = [
        (i, b[0], c[0], b[1], v) for i, b, c, v in zip(ids, base, cand, values) if b[2] <= limit
    ]
    m_base, m_cand = metrics(base), metrics(cand)
    early_base = [p for p in base if p[2] <= limit]
    early_cand = [p for p in cand if p[2] <= limit]
    m_early_base, m_early_cand = metrics(early_base), metrics(early_cand)
    gain = m_base["brier_early"] - m_cand["brier_early"]
    seed = analysis_config.MASTERY_STUDY_SEED
    gaps = [decile_gap(points, seed) * 100 for points in (base, cand, early_base, early_cand)]
    print(f"\n[DATA] === {label} : {len(parts)} parties, {m_base['images']} images ===")
    print(
        f"[DATA] Brier <= {limit:g} min {m_base['brier_early']:.5f} -> {m_cand['brier_early']:.5f}, "
        f"gain {gain:+.5f} ; toutes images {m_base['brier']:.5f} -> {m_cand['brier']:.5f}, "
        f"gain {m_base['brier'] - m_cand['brier']:+.5f}"
    )
    print(
        f"[DATA] Écart max par décile : toutes images {gaps[0]:.2f} -> {gaps[1]:.2f} pts ; "
        f"<= {limit:g} min {gaps[2]:.2f} -> {gaps[3]:.2f} pts ; AUC <= {limit:g} min "
        f"{m_early_base['auc']:.4f} -> {m_early_cand['auc']:.4f}"
    )

    deltas = [(i, (b - y) ** 2 - (c - y) ** 2) for i, b, c, y, _ in early]
    moved = [d for (_, d), row in zip(deltas, early) if row[4] != 0.0]
    print(
        f"[DATA] Terme non nul : {sum(g.states[0][term] != 0.0 for g in parts if g.states)} parties"
        f" sur {len(parts)}, gain sur leurs images <= {limit:g} min "
        f"{mean(moved) if moved else 0.0:+.5f}"
    )
    draws = analysis_config.MASTERY_STUDY_BOOTSTRAP
    by_game = grouped(deltas, len(parts), len(parts))
    by_time = grouped(deltas, cfg.FORM_TIME_BLOCKS, len(parts))
    se_game, low_game, high_game = cluster_interval(by_game, draws, seed)
    se_time, low_time, high_time = cluster_interval(by_time, draws, seed)
    print(
        f"[DATA] IC 90 % du gain : par partie [{low_game:+.5f} ; {high_game:+.5f}] (se "
        f"{se_game:.5f}), par bloc de temps [{low_time:+.5f} ; {high_time:+.5f}] (se {se_time:.5f})"
    )
    se = max(se_game, se_time)
    wide_low, wide_high = (
        (low_game, high_game)
        if high_game - low_game >= high_time - low_time
        else (low_time, high_time)
    )
    print(f"[DATA] IC retenu (le plus large) : [{wide_low:+.5f} ; {wide_high:+.5f}]")
    detect = (Z_90 + Z_POWER_80) * se
    line = f"[DATA] Puissance : gain détectable à 80 % = {detect:.5f}"
    if reference is not None:
        line += f", puissance pour {reference:.4f} = {power(reference, se) * 100:.0f} %"
    print(line)

    moves = sorted(abs(c - b) * 100 for _, b, c, _, _ in early)
    print(
        f"[DATA] Ampleur <= {limit:g} min, |P avec - P sans| en points : moyenne {mean(moves):.2f}, "
        f"RMS {math.sqrt(mean(v * v for v in moves)):.2f}, p50 {quantile(moves, 0.5):.2f}, "
        f"p90 {quantile(moves, 0.9):.2f}, max {moves[-1]:.2f}"
    )
    ranked = sorted(early, key=lambda r: r[4])
    n = len(ranked)
    for k in range(QUINTILES):
        chunk = ranked[k * n // QUINTILES : (k + 1) * n // QUINTILES]
        print(
            f"[DATA]   quintile {k + 1} du terme ({chunk[0][4]:+.2f} à {chunk[-1][4]:+.2f}) : "
            f"observé {mean(r[3] for r in chunk) * 100:.1f} %, sans {mean(r[1] for r in chunk) * 100:.1f}"
            f", avec {mean(r[2] for r in chunk) * 100:.1f}"
        )


def judge(
    label: str,
    parts: Sequence[Game],
    terms: Sequence[Tuple[str, str, Optional[float]]],
) -> None:
    """Le modèle en place sur `parts`, puis chaque (libellé, terme, gain de référence), mêmes blocs."""
    folds = cfg.FORM_CV_FOLDS
    began = time.monotonic()
    base = _pooled(parts, folds, INPUTS)
    for name, term, reference in terms:
        cand = _pooled(parts, folds, INPUTS + (term,))
        report(f"{label}, {name}", parts, base, cand, term, reference)
    print(f"[INFO] {label} : {time.monotonic() - began:.0f} s", flush=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ADR-004 : rejuge form_impact et la draft")
    parser.add_argument("--crawl-path", default=str(crawl_path()))
    parser.add_argument("--db-path", default=str(config.DATABASE_PATH))
    parser.add_argument("--model-path", default=str(model_path()))
    parser.add_argument("--cache", default=None, help="variables calculées, relues si présentes")
    parser.add_argument("--limit", type=int, default=None, help="parties les plus récentes")
    return parser.parse_args()


def compute(args: argparse.Namespace, model: WinModel) -> Tuple[List[Game], List[Meta]]:
    """Lit les bases, pose `draft`, `form_impact` et `form_in_sample` sur les images."""
    began = time.monotonic()
    crawl = _open_ro(Path(args.crawl_path))
    rows = read_rows(crawl, args.limit)
    crawl.close()
    print(f"[INFO] {len(rows)} lignes lues en {time.monotonic() - began:.0f} s", flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "db.db"
        shutil.copy2(
            args.db_path, copy
        )  # l'évaluateur passe par Database : jamais sur la vraie base
        db = Database(str(copy))
        db.connect()
        try:
            games, metas = build_games(rows, db.get_all_champion_names(), GameEvaluator(db))
        finally:
            db.close()
    print(f"[INFO] Parties prêtes en {time.monotonic() - began:.0f} s", flush=True)
    refit = fit([s for g in games for s in g.states], [g.win for g in games for _ in g.states])
    add_form(games, metas, rows, refit, "form_in_sample")
    add_form(games, metas, rows, model, "form_impact")
    return games, metas


def main() -> None:
    """Variables (cache ou calcul), vérification du biais, puis les deux jugements."""
    args = _parse_args()
    model = WinModel.from_json(Path(args.model_path).read_text(encoding="utf-8"))
    cache = Path(args.cache) if args.cache else None
    if cache and cache.exists():
        with cache.open("rb") as f:
            games, metas = pickle.load(f)
    else:
        games, metas = compute(args, model)
        if cache:
            with cache.open("wb") as f:
                pickle.dump((games, metas), f)

    trained = (model.meta or {}).get("trained", "")[:10]
    overlap = sum(m.creation[:10] <= trained for m in metas)
    print(f"[DATA] Modèle d'impact : {model.meta}")
    print(
        f"[DATA] Parties : {metas[0].creation} à {metas[-1].creation}, {Counter(m.patch for m in metas)}"
    )
    print(f"[DATA] Parties jouées au plus tard le jour de l'entraînement : {overlap}")

    seed = analysis_config.MASTERY_STUDY_SEED
    form_placebo = add_placebo(games, "form_impact", seed)
    draft_placebo = add_placebo(games, "draft", seed)
    covered = [g for g in games if g.covered]
    drafted = [g for g, m in zip(games, metas) if m.has_draft]
    print(f"[DATA] Sous-ensemble couvert : {len(covered)} parties ; avec draft : {len(drafted)}")
    judge(
        "Couvert",
        covered,
        (
            ("form_impact, impacts hors échantillon", "form_impact", 0.0013),
            (
                "form_impact, impacts sur la base (biais de l'ancienne mesure)",
                "form_in_sample",
                None,
            ),
            ("placebo", form_placebo, None),
        ),
    )
    judge(
        "Toutes parties (joueur sans forme = 0)",
        games,
        (
            ("form_impact, impacts hors échantillon", "form_impact", 0.0013),
            (
                "form_impact, impacts sur la base (biais de l'ancienne mesure)",
                "form_in_sample",
                None,
            ),
            ("placebo", form_placebo, None),
        ),
    )
    judge(
        "Draft",
        drafted,
        (("a priori de draft", "draft", 0.0005), ("placebo", draft_placebo, None)),
    )


if __name__ == "__main__":
    main()
