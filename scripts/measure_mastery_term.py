"""Mesure du terme de maîtrise personnelle (SPEC-41 §4.3, tâche 199).

Lit `crawl.db` (parties de tiers, lues) et `db.db` (tables LoLalytics, parties de @pj35) en lecture
seule. Pour chaque joueur focal (au moins `MASTERY_STUDY_MIN_GAMES` parties lues), sa maîtrise du
champion joué est tirée de son impact ΔP (SPEC-20) sur ses AUTRES parties, puis on teste si elle prédit
la victoire au-delà du logit de draft (`GameEvaluator`). Validation croisée à 5 blocs de joueurs,
IC95 par bootstrap sur les joueurs, seuil de SPEC-41 §2 figé avant la mesure. Deux références : (a)
écart à la moyenne du joueur, (b) le même moins la norme ΔP du champion. Aucune écriture.

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
    masteries,
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
from src.winprob.crawl import unpack
from src.winprob.impact import impacts
from src.winprob.model import WinModel
from src.winprob.state import BLUE, blue_win
from src.winprob.train import crawl_path, load_model

PROGRESS_EVERY = 5000
VARIANTS = ("a", "b")


@dataclass(frozen=True)
class Row:
    """Un participant d'une partie retenue."""

    puuid: str
    game: int  # rang de la partie dans la lecture, du plus récent au plus ancien
    champion: str
    win: int
    points: float  # 100 × Σ ΔP de ses lignes d'impact
    draft: float  # logit de draft de son équipe


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
    return [
        Row(
            puuid=puuid_of[pid],
            game=index,
            champion=champion_of[pid],
            win=int(win) if team_of[pid] == BLUE else 1 - int(win),
            points=points[pid],
            draft=blue_logit if team_of[pid] == BLUE else -blue_logit,
        )
        for pid in roles
    ]


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
    by_player: Dict[str, List[Row]], norms: Optional[Dict[str, float]]
) -> Optional[float]:
    """K de la population : variance entre champions à l'intérieur de chaque joueur, regroupée."""
    offsets = norms or {}
    players = []
    for games in by_player.values():
        groups: Dict[str, List[float]] = defaultdict(list)
        for row in games:
            groups[row.champion].append(row.points - offsets.get(row.champion, 0.0))
        players.append(groups)
    return pooled_shrink_k(players)


def offsets_of(
    by_player: Dict[str, List[Row]], k: float, norms: Optional[Dict[str, float]]
) -> Dict[Tuple[str, int], float]:
    """(joueur, partie) -> maîtrise du champion joué, calculée sans cette partie."""
    out: Dict[Tuple[str, int], float] = {}
    for puuid, games in by_player.items():
        points = leave_one_out_points([(r.champion, r.points) for r in games], k, norms)
        for row, value in zip(games, points):
            out[(puuid, row.game)] = value
    return out


@dataclass
class Pooled:
    """Prédictions hors bloc, une par ligne focale."""

    players: List[str]
    wins: List[int]
    base: List[float]
    variants: Dict[str, List[float]]
    ks: Dict[str, List[float]]


def cross_validate(rows: Sequence[Row], focal: Set[str]) -> Optional[Pooled]:
    """Validation croisée à blocs de joueurs : draft seule contre draft + maîtrise (a et b)."""
    pooled = Pooled([], [], [], {v: [] for v in VARIANTS}, {v: [] for v in VARIANTS})
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
        for variant in VARIANTS:
            variant_norms = norms if variant == "b" else None
            k = estimate_k(train, variant_norms)
            if k is None:
                print(f"[INFO] Variante {variant}, bloc {fold} : τ² ≤ 0, terme nul.")
                pooled.variants[variant].extend(pooled.base[-len(test_rows) :])
                continue
            pooled.ks[variant].append(k)
            train_off = offsets_of(train, k, variant_norms)
            test_off = offsets_of(test, k, variant_norms)
            coef = fit_logistic(
                [[1.0, r.draft, train_off[(r.puuid, r.game)]] for r in train_rows],
                [r.win for r in train_rows],
            )
            pooled.variants[variant].extend(
                predict_logistic(coef, [1.0, r.draft, test_off[(r.puuid, r.game)]])
                for r in test_rows
            )
    return pooled


def _squared_errors(probs: Sequence[float], wins: Sequence[int]) -> List[float]:
    return [(p - y) ** 2 for p, y in zip(probs, wins)]


def full_fit(
    rows: Sequence[Row], focal: Set[str], variant: str, seed: int
) -> Optional[Tuple[float, List[float], Tuple[float, float]]]:
    """Sur tout l'échantillon : K, coefficients [biais, draft, maîtrise] et IC95 du coefficient."""
    by_player = _by_player([r for r in rows if r.puuid in focal])
    norms = champion_norms(rows) if variant == "b" else None
    k = estimate_k(by_player, norms)
    if k is None:
        return None
    off = offsets_of(by_player, k, norms)
    focal_rows = [r for games in by_player.values() for r in games]
    xs = [[1.0, r.draft, off[(r.puuid, r.game)]] for r in focal_rows]
    ys = [r.win for r in focal_rows]
    coef = fit_logistic(xs, ys)
    draws = player_bootstrap(
        [r.puuid for r in focal_rows], xs, ys, coef, cfg.MASTERY_STUDY_BOOTSTRAP, seed
    )
    return k, coef, ci95([c[2] for c in draws])


def _own_games(game_db: sqlite3.Connection, names: Dict[int, str]) -> List[Tuple[str, float]]:
    """Parties SoloQ de @pj35 : (champion, 100 × Σ ΔP de ses lignes d'impact)."""
    placeholders = ",".join("?" * len(cfg.MASTERY_QUEUE_IDS))
    query = f"""
        SELECT m.champion_id, 100 * SUM(i.delta_p)
        FROM game_records g
        JOIN game_impact i ON i.game_id = g.game_id AND i.participant_id = g.player_participant_id
        JOIN (SELECT DISTINCT game_id, champion_id FROM game_metrics WHERE is_player = 1) m
          ON m.game_id = g.game_id
        WHERE g.queue_id IN ({placeholders})
        GROUP BY g.game_id, m.champion_id
        ORDER BY g.game_creation_utc
    """
    return [
        (names.get(cid, str(cid)), points)
        for cid, points in game_db.execute(query, cfg.MASTERY_QUEUE_IDS)
    ]


def _print_own(own: List[Tuple[str, float]], k_population: Optional[float]) -> None:
    """Le K de @pj35 et sa table, rétrécie avec le K de la population (celui du moteur)."""
    groups: Dict[str, List[float]] = defaultdict(list)
    for champion, points in own:
        groups[champion].append(points)
    k_own = shrink_k(groups)
    own_text = "τ² ≤ 0" if k_own is None else f"{k_own:.1f}"
    print(f"[DATA] @pj35 : {len(own)} parties SoloQ avec impact, K propre {own_text}")
    if not own or k_population is None:
        return
    table = masteries(own, k_population)
    for mastery in sorted(table.values(), key=lambda m: -m.games):
        print(
            f"[DATA]   {mastery.champion:<14} {mastery.games:>3} parties  "
            f"brut {mastery.raw_points:+6.1f}  rétréci {mastery.points:+5.1f} pts"
        )


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
        finally:
            db.close()
            crawl_db.close()
            game_db.close()

    games_per_player = Counter(r.puuid for r in rows)
    focal = {p for p, n in games_per_player.items() if n >= cfg.MASTERY_STUDY_MIN_GAMES}
    focal_rows = sum(games_per_player[p] for p in focal)
    print(
        f"[DATA] {len(games_per_player)} joueurs, {len(focal)} focaux "
        f"(≥ {cfg.MASTERY_STUDY_MIN_GAMES} parties lues), {focal_rows} lignes de prédiction"
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
            print(f"[DATA] Variante {variant} : τ² ≤ 0 sur l'échantillon complet, terme nul.")
            continue
        k, coef, coef_ci = fitted
        k_by_variant[variant] = k
        k_folds = median(pooled.ks[variant]) if pooled.ks[variant] else float("nan")
        print(
            f"[DATA] Variante {variant} : K {k:.1f} (médiane des blocs {k_folds:.1f}), "
            f"b {coef[2]:.4f} logit/pt [{coef_ci[0]:.4f} ; {coef_ci[1]:.4f}], "
            f"Brier {base_brier:.5f} -> {brier:.5f}, gain {base_brier - brier:+.5f} "
            f"[{gain_ci[0]:+.5f} ; {gain_ci[1]:+.5f}]"
        )
        if decide(coef_ci, gain_ci):
            adopted[variant] = (k, coef)

    choice = None
    if "b" in adopted:
        diff = [gb - ga for ga, gb in zip(gains["a"], gains["b"])]
        diff_ci = ci95(
            player_mean_bootstrap(pooled.players, diff, cfg.MASTERY_STUDY_BOOTSTRAP, args.seed)
        )
        print(f"[DATA] Gain b − a : IC95 [{diff_ci[0]:+.5f} ; {diff_ci[1]:+.5f}]")
        if diff_ci[0] > 0 or "a" not in adopted:
            choice = "b"
    if choice is None and "a" in adopted:
        choice = "a"
    if choice is None:
        print("[INFO] Non adopté : seuil de SPEC-41 §2 non atteint.")
        _print_own(own, k_by_variant.get("a"))
        return
    k, coef = adopted[choice]
    print(
        f"[OK] Adopté (variante {choice}) : MASTERY_LOGIT_PER_POINT = {coef[2]:.4f}, "
        f"MASTERY_K = {k:.1f}"
    )
    _print_own(own, k)


if __name__ == "__main__":
    main()
