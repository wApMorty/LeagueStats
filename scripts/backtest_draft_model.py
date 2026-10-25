"""Backtest du modèle de draft sur `crawl.db` (SPEC-43 §4.2, tâche 210).

Lit `crawl.db` (parties de tiers, lues) et `db.db` (tables de paires, sur copie) en lecture seule.
Pour chaque partie retenue, les deux compositions sont évaluées par `GameEvaluator` ; en validation
croisée à 5 plis, le logit en vigueur (un seul coefficient, qui vaut 1 s'il est calibré) est comparé à
un modèle à coefficients libres : duel de lane, matchups hors lane, synergies, force intrinsèque. Les
features sont à K = 1, donc chaque coefficient ajusté est directement la valeur de son K. IC 90 % des
coefficients par Wald, IC 90 % des gains d'AUC et de Brier par bootstrap sur les prédictions hors pli.
Verdict : adopter les K ajustés si l'IC 90 % du gain de Brier exclut 0 (SPEC-43 §2). Aucune écriture.

USAGE:
    python scripts/backtest_draft_model.py                  # mesure complète (~10 min)
    python scripts/backtest_draft_model.py --limit 20000    # 20 000 parties lues les plus récentes
"""

import argparse
import itertools
import json
import random
import shutil
import sqlite3
import sys
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.measure_moneyball import _open_ro
from src.analysis.calibration import brier_score
from src.analysis.game_eval import GameEvaluator, Placed
from src.analysis.mastery import _gradient_hessian, fit_logistic, predict_logistic
from src.config import config
from src.config_constants import analysis_config as cfg
from src.config_constants import role_inference_config
from src.coaching.metrics import participant_roles
from src.db import Database
from src.winprob.crawl import unpack
from src.winprob.model import _solve
from src.winprob.state import BLUE, blue_win
from src.winprob.train import crawl_path

# Compteurs de lecture, dans l'ordre d'affichage.
COUNT_KEYS = ("lues", "illisibles", "courtes", "sans_issue", "postes", "retenues")
# Queue de chaque côté de l'IC 90 % (5 % de chaque côté).
_TAIL = 0.05


@dataclass(frozen=True)
class Game:
    """Une partie retenue : composition bleue et rouge, (champion, lane), et issue bleue."""

    blue: List[Placed]
    red: List[Placed]
    win: bool


@dataclass(frozen=True)
class Terms:
    """Termes de la draft d'une partie, du point de vue bleu, en logit à K = 1 (sauf `current`)."""

    lane: float  # duels de lane, pondérés par SAME_LANE_WEIGHT
    other: float  # duels hors lane, pondérés par OTHER_LANE_WEIGHT
    synergy: float  # synergies alliées moins synergies ennemies
    strength: float  # force intrinsèque alliée moins ennemie
    current: float  # logit en vigueur (`GameEvaluator.team_logit`, avec K actuels)

    @property
    def matchup(self) -> float:
        """Duels de lane et hors lane ensemble."""
        return self.lane + self.other


def _parse_args() -> argparse.Namespace:
    """Arguments de la ligne de commande : bases et nombre de parties lues."""
    parser = argparse.ArgumentParser(description="SPEC-43 : backtest du modèle de draft")
    parser.add_argument("--crawl-path", default=str(crawl_path()))
    parser.add_argument("--db-path", default=str(config.DATABASE_PATH))
    parser.add_argument(
        "--limit", type=int, default=None, help="parties de crawl.db les plus récentes, au plus"
    )
    return parser.parse_args()


def select(game: dict, names: Dict[int, str]) -> Tuple[str, Optional[Game]]:
    """Motif de l'écart (clé de COUNT_KEYS) et la partie retenue, None si écartée.

    Une partie est écartée si elle est trop courte, sans issue bleue, ou si un de ses dix postes
    reste inconnu (`participant_roles` rend None).
    """
    if game.get("gameDuration", 0) < cfg.BACKTEST_MIN_DURATION_S:
        return "courtes", None
    win = blue_win(game)
    if win is None:
        return "sans_issue", None
    roles = participant_roles(game)
    if len(roles) != 10 or None in roles.values():
        return "postes", None
    blue: List[Placed] = []
    red: List[Placed] = []
    for participant in game["participants"]:
        placed = (
            names.get(participant["championId"], str(participant["championId"])),
            roles[participant["participantId"]],
        )
        (blue if participant["teamId"] == BLUE else red).append(placed)
    return "retenues", Game(blue, red, bool(win))


def read_games(
    crawl_db: sqlite3.Connection,
    limit: Optional[int],
    names: Dict[int, str],
    counts: Dict[str, int],
) -> List[Game]:
    """Parties retenues de `crawl.db`, de la plus récente à la plus ancienne.

    Les identifiants sont lus d'abord, puis une ligne à la fois : une ligne illisible (erreur SQLite,
    blob qui ne se décompresse pas) est comptée dans `illisibles` et sautée.
    """
    ids = [
        game_id
        for (game_id,) in crawl_db.execute(
            "SELECT game_id FROM crawl_games WHERE read_utc IS NOT NULL "
            "AND queue_id IN (SELECT value FROM json_each(?)) "
            "ORDER BY game_creation_utc DESC, game_id DESC LIMIT ?",
            (json.dumps(cfg.BACKTEST_QUEUE_IDS), limit if limit else -1),
        )
    ]
    games: List[Game] = []
    for game_id in ids:
        counts["lues"] += 1
        try:
            (raw,) = crawl_db.execute(
                "SELECT raw FROM crawl_games WHERE game_id = ?", (game_id,)
            ).fetchone()
            motif, picked = select(unpack(raw)["game"], names)
        except (sqlite3.DatabaseError, zlib.error, ValueError, KeyError, TypeError):
            counts["illisibles"] += 1
            continue
        counts[motif] += 1
        if picked is not None:
            games.append(picked)
    return games


def _pair_sum(points: Callable[[Placed, Placed], float], team: Sequence[Placed]) -> float:
    """Somme de `points` sur les paires non ordonnées d'une équipe, en logit à K = 1."""
    return sum(
        points(a, b) * cfg.LOGIT_PER_WINRATE_POINT for a, b in itertools.combinations(team, 2)
    )


def game_terms(evaluator: GameEvaluator, blue: Sequence[Placed], red: Sequence[Placed]) -> Terms:
    """Termes de la draft, du point de vue bleu. Changer de camp change le signe de chaque terme."""
    lane = other = 0.0
    for ally in blue:
        for enemy in red:
            logit = evaluator.duel_points(ally, enemy) * cfg.LOGIT_PER_WINRATE_POINT
            if ally[1] and ally[1] == enemy[1]:
                lane += role_inference_config.SAME_LANE_WEIGHT * logit
            else:
                other += role_inference_config.OTHER_LANE_WEIGHT * logit
    synergy = _pair_sum(evaluator.synergy_points, blue) - _pair_sum(evaluator.synergy_points, red)
    strength = sum(evaluator.strength_points(c) for c in blue) - sum(
        evaluator.strength_points(c) for c in red
    )
    return Terms(
        lane=lane,
        other=other,
        synergy=synergy,
        strength=strength * cfg.LOGIT_PER_WINRATE_POINT,
        current=evaluator.team_logit(list(blue), list(red)),
    )


def rank_auc(scores: Sequence[float], outcomes: Sequence[int]) -> float:
    """AUC par les rangs (O(n log n)), ex aequo au rang moyen : égale `calibration.auc`.

    0,5 sans victoire ni défaite, comme `calibration.auc`.
    """
    n = len(scores)
    order = sorted(range(n), key=lambda i: scores[i])
    ranks = [0.0] * n
    start = 0
    while start < n:
        end = start
        while end + 1 < n and scores[order[end + 1]] == scores[order[start]]:
            end += 1
        for position in range(start, end + 1):
            ranks[order[position]] = (start + end) / 2 + 1
        start = end + 1
    positives = sum(outcomes)
    negatives = n - positives
    if not positives or not negatives:
        return 0.5
    rank_sum = sum(rank for rank, outcome in zip(ranks, outcomes) if outcome == 1)
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def cross_validate(
    xs: Sequence[Sequence[float]], ys: Sequence[int], folds: int, seed: int
) -> List[float]:
    """Prédictions hors pli : chaque ligne est prédite par un modèle entraîné sans elle."""
    n = len(xs)
    order = list(range(n))
    random.Random(seed).shuffle(order)
    fold_of = [0] * n
    for position, index in enumerate(order):
        fold_of[index] = position % folds
    predictions = [0.0] * n
    for fold in range(folds):
        train = [i for i in range(n) if fold_of[i] != fold]
        coef = fit_logistic([xs[i] for i in train], [ys[i] for i in train])
        for i in range(n):
            if fold_of[i] == fold:
                predictions[i] = predict_logistic(coef, xs[i])
    return predictions


def wald_interval(
    xs: Sequence[Sequence[float]], ys: Sequence[int], coef: Sequence[float], z: float
) -> List[Tuple[float, float]]:
    """IC de Wald de chaque coefficient : coef ± z × écart-type (diagonale de l'inverse de la hessienne)."""
    _, hess = _gradient_hessian(xs, ys, coef)
    size = len(coef)
    intervals = []
    for k in range(size):
        column = _solve(hess, [1.0 if i == k else 0.0 for i in range(size)])
        half = z * column[k] ** 0.5
        intervals.append((coef[k] - half, coef[k] + half))
    return intervals


def effective_lane_weight(coef_lane: float, coef_other: float) -> Optional[float]:
    """Poids du duel de lane que préfèrent les données, à comparer à SAME_LANE_WEIGHT.

    Les deux variables portent déjà leur poids (SAME_LANE_WEIGHT, OTHER_LANE_WEIGHT) : des
    coefficients égaux veulent dire que le rapport en vigueur est juste. None si le coefficient hors
    lane est nul.
    """
    if not coef_other:
        return None
    return (
        coef_lane
        / coef_other
        * role_inference_config.SAME_LANE_WEIGHT
        / role_inference_config.OTHER_LANE_WEIGHT
    )


def _interval90(samples: Sequence[float]) -> Tuple[float, float]:
    """IC 90 % percentile d'un échantillon bootstrap."""
    ranked = sorted(samples)
    n = len(ranked)
    return ranked[int(_TAIL * n)], ranked[min(n - 1, int((1 - _TAIL) * n))]


def bootstrap_gains(
    p_ref: Sequence[float], p_new: Sequence[float], ys: Sequence[int], draws: int, seed: int
) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """IC 90 % des gains (AUC : new − ref ; Brier : ref − new, positif = mieux) par bootstrap.

    Rééchantillonne les parties sur les prédictions hors pli, sans réajuster le modèle.
    """
    rng = random.Random(seed)
    n = len(ys)
    auc_gains: List[float] = []
    brier_gains: List[float] = []
    for _ in range(draws):
        index = [rng.randrange(n) for _ in range(n)]
        ref = [p_ref[i] for i in index]
        new = [p_new[i] for i in index]
        outcomes = [ys[i] for i in index]
        auc_gains.append(rank_auc(new, outcomes) - rank_auc(ref, outcomes))
        brier_gains.append(
            brier_score(list(zip(ref, outcomes))) - brier_score(list(zip(new, outcomes)))
        )
    return _interval90(auc_gains), _interval90(brier_gains)


def _report(games: List[Game], terms: List[Terms]) -> None:
    """Validation croisée, coefficients, IC et verdict, imprimés sur la console."""
    ys = [int(g.win) for g in games]
    current = [[1.0, t.current] for t in terms]
    adjusted = [[1.0, t.matchup, t.synergy, t.strength] for t in terms]
    diagnostic = [[1.0, t.lane, t.other, t.synergy, t.strength] for t in terms]
    folds, seed, z = cfg.BACKTEST_FOLDS, cfg.BACKTEST_SEED, cfg.BACKTEST_Z90

    pred_cur = cross_validate(current, ys, folds, seed)
    pred_adj = cross_validate(adjusted, ys, folds, seed)
    pred_diag = cross_validate(diagnostic, ys, folds, seed)
    print(
        f"[DATA] AUC hors pli : en vigueur {rank_auc(pred_cur, ys):.3f}, "
        f"ajusté {rank_auc(pred_adj, ys):.3f}, diagnostic {rank_auc(pred_diag, ys):.3f}"
    )
    print(
        f"[DATA] Brier hors pli : en vigueur {brier_score(list(zip(pred_cur, ys))):.4f}, "
        f"ajusté {brier_score(list(zip(pred_adj, ys))):.4f}, "
        f"diagnostic {brier_score(list(zip(pred_diag, ys))):.4f}"
    )

    coef_cur = fit_logistic(current, ys)
    ci_cur = wald_interval(current, ys, coef_cur, z)[1]
    verdict_one = "contient" if ci_cur[0] <= 1.0 <= ci_cur[1] else "ne contient pas"
    print(
        f"[DATA] Coefficient du logit en vigueur : {coef_cur[1]:.3f} "
        f"(IC 90 % [{ci_cur[0]:.3f} ; {ci_cur[1]:.3f}]), {verdict_one} 1"
    )

    coef_adj = fit_logistic(adjusted, ys)
    ci_adj = wald_interval(adjusted, ys, coef_adj, z)
    labels = (
        ("K_MATCHUP", cfg.K_MATCHUP),
        ("K_SYNERGY", cfg.K_SYNERGY),
        ("K_INTRINSIC", cfg.K_INTRINSIC),
    )
    for offset, (label, in_force) in enumerate(labels, start=1):
        print(
            f"[DATA] {label} ajusté : {coef_adj[offset]:.3f} "
            f"(IC 90 % [{ci_adj[offset][0]:.3f} ; {ci_adj[offset][1]:.3f}]), en vigueur {in_force}"
        )

    coef_diag = fit_logistic(diagnostic, ys)
    weight = effective_lane_weight(coef_diag[1], coef_diag[2])
    if weight is not None:
        print(
            f"[DATA] Diagnostic : poids effectif du duel de lane {weight:.2f} "
            f"(en vigueur : SAME_LANE_WEIGHT {role_inference_config.SAME_LANE_WEIGHT})"
        )

    auc_ci, brier_ci = bootstrap_gains(pred_cur, pred_adj, ys, cfg.BACKTEST_BOOTSTRAP, seed)
    gain_auc = rank_auc(pred_adj, ys) - rank_auc(pred_cur, ys)
    gain_brier = brier_score(list(zip(pred_cur, ys))) - brier_score(list(zip(pred_adj, ys)))
    print(
        f"[DATA] Gain d'AUC (ajusté - en vigueur) : {gain_auc:+.4f} "
        f"(IC 90 % [{auc_ci[0]:+.4f} ; {auc_ci[1]:+.4f}])"
    )
    print(
        f"[DATA] Gain de Brier (en vigueur - ajusté) : {gain_brier:+.5f} "
        f"(IC 90 % [{brier_ci[0]:+.5f} ; {brier_ci[1]:+.5f}])"
    )
    if brier_ci[0] > 0:
        print("[INFO] Verdict : adopter les K ajustés (IC 90 % du gain de Brier au-dessus de 0).")
    else:
        print("[INFO] Verdict : garder les K en vigueur (IC 90 % du gain de Brier n'exclut pas 0).")


def main() -> None:
    """Lecture de `crawl.db`, termes de draft, puis rapport de la validation croisée."""
    args = _parse_args()
    crawl_db = _open_ro(Path(args.crawl_path))
    _open_ro(Path(args.db_path)).close()  # présence de la base ; la lecture passe par la copie
    counts = {key: 0 for key in COUNT_KEYS}
    try:
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
                games = read_games(crawl_db, args.limit, names, counts)
                terms = [game_terms(evaluator, g.blue, g.red) for g in games]
            finally:
                db.close()
    finally:
        crawl_db.close()
    print(
        f"[DATA] {counts['lues']} parties lues : {counts['illisibles']} illisibles, "
        f"{counts['courtes']} courtes, {counts['sans_issue']} sans issue, "
        f"{counts['postes']} à poste inconnu ; {counts['retenues']} retenues"
    )
    if len(games) < cfg.BACKTEST_FOLDS:
        print("[ALERTE] Trop peu de parties retenues pour la validation croisée.")
        return
    _report(games, terms)


if __name__ == "__main__":
    main()
