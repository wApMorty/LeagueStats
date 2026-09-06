"""SPEC-11 (étage a) — pondération par lane restante.

Constat : ``ChampionScorer.score_against_team()`` (src/analysis/scoring.py)
pondère les ennemis DÉJÀ PICKÉS par proximité de lane (``_lane_weight()``,
SAME_LANE_WEIGHT/OTHER_LANE_WEIGHT), mais dilue chaque slot ennemi encore
inconnu ("blind pick") avec une moyenne neutre — sans jamais tenir compte du
fait qu'un de ces slots deviendra, en fin de draft, l'adversaire de notre
lane. Ce module comble ce trou en isolant, parmi les slots encore ouverts,
celui qui représente statistiquement le futur adversaire direct, et en
l'estimant avec une moyenne pondérée par la plausibilité de chaque candidat
sur cette lane (``champion_lanes.share``, déjà collectée et déjà utilisée
côté role_inference.py pour les champions pickés).

Garde-fou (@pj35, 2026-09-06) : is_enabled() n'active ce comportement
qu'une fois assez de résultats de partie réels en base (même seuil que
scripts/calibrate_model.py, analysis_config.MIN_ROWS_FOR_CALIBRATION) — sous
ce seuil, blind_pick_contribution() reproduit exactement le calcul
pré-SPEC-11 (moyenne neutre, poids 1.0 par slot), donc la fonctionnalité est
un no-op tant que le seuil n'est pas franchi. ChampionScorer.
effective_model_version() suffixe MODEL_VERSION en conséquence, pour qu'une
future calibration ne mélange jamais les deux régimes de scoring.

Hors périmètre ici (voir docs/specs/SPEC-11-lane-restante-et-recherche.md
§3-4) : toute recherche/anticipation multi-plis — ce module ne fait
qu'affiner l'évaluation statique d'un seul pick, jamais une recherche
dessus.
"""

from typing import Dict, List, Optional, Set, Tuple

from ..config_constants import analysis_config, role_inference_config
from ..models import Matchup
from .probability import confidence


def is_enabled(db) -> bool:
    """True une fois analysis_config.MIN_ROWS_FOR_CALIBRATION prédictions
    labellisées en base -- même bar que scripts/calibrate_model.py, pour
    qu'un changement d'éval non éprouvé ne s'active pas sur un coup de tête
    ni sur un jeu de données trop mince pour dire s'il aide ou nuit."""
    return db.count_labelled_predictions() >= analysis_config.MIN_ROWS_FOR_CALIBRATION


def blind_pick_contribution(
    scorer,
    available_matchups: List[Matchup],
    blind_picks: int,
    player_lane: Optional[str],
    enemy_lanes_filled: Set[str],
    lane_distributions_by_name: Dict[str, Dict[str, float]],
) -> Tuple[float, float]:
    """(delta2 total, poids total) pour les `blind_picks` slots ennemis
    encore inconnus.

    Si `player_lane` est inconnue, déjà occupée par un ennemi pické (déjà
    géré par la boucle des ennemis connus dans score_against_team), ou s'il
    n'y a aucun slot à combler : comportement inchangé, un slot = un poids
    de 1.0 et la moyenne neutre (pré-SPEC-11, jamais de repli silencieux sur
    une lane devinée).

    Sinon, un des slots est traité comme "l'ennemi qui finira dans notre
    lane" (en fin de draft les 5 lanes adverses sont toujours remplies) :
    pondéré SAME_LANE_WEIGHT au lieu de OTHER_LANE_WEIGHT, et estimé par une
    moyenne conditionnée sur la plausibilité de chaque candidat pour cette
    lane plutôt que la moyenne neutre.
    """
    if not player_lane or player_lane in enemy_lanes_filled or blind_picks <= 0:
        avg = scorer.avg_delta2(available_matchups)
        return blind_picks * avg, float(blind_picks)

    same_lane_avg = _lane_conditioned_avg_delta2(
        scorer, available_matchups, player_lane, lane_distributions_by_name
    )
    other_avg = scorer.avg_delta2(available_matchups)
    other_blind = blind_picks - 1

    total_delta2 = (
        role_inference_config.SAME_LANE_WEIGHT * same_lane_avg
        + other_blind * role_inference_config.OTHER_LANE_WEIGHT * other_avg
    )
    total_weight = (
        role_inference_config.SAME_LANE_WEIGHT
        + other_blind * role_inference_config.OTHER_LANE_WEIGHT
    )
    return total_delta2, total_weight


def _lane_conditioned_avg_delta2(
    scorer,
    matchups: List[Matchup],
    player_lane: str,
    lane_distributions_by_name: Dict[str, Dict[str, float]],
) -> float:
    """Moyenne de delta2 pondérée par pickrate*confidence (comme
    ChampionScorer.avg_delta2), avec un facteur supplémentaire : la
    plausibilité que cet adversaire potentiel joue `player_lane`
    (champion_lanes.share, plancher EPSILON -- même convention que
    role_inference.py, une lane jamais jouée doit rester improbable, jamais
    impossible)."""
    valid = scorer.filter_valid_matchups(matchups)
    if not valid:
        return 0.0

    def plausibility(m: Matchup) -> float:
        share = lane_distributions_by_name.get(m.enemy_name.lower(), {}).get(player_lane, 0.0)
        return max(share, role_inference_config.EPSILON)

    weights = [m.pickrate * confidence(m.games) * plausibility(m) for m in valid]
    total_weight = sum(weights)
    if total_weight == 0:
        return 0.0
    return sum(m.delta2 * w for m, w in zip(valid, weights)) / total_weight
