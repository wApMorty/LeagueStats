"""Team role inference (SPEC-04 B4).

Assigns a distinct lane to each of up to 5 champions in a team, maximizing
the joint likelihood of the assignment given each champion's lane
distribution. Pure computation: no DB access, no I/O — see SPEC-04 §7
("le module ne fait qu'appeler et stocker" du côté de draft_monitor.py,
la logique reste ici pour rester trivialement testable).

Algorithm: exhaustive enumeration of the (at most 5! = 120) permutations of
lanes, exact and effectively instantaneous at this size — see SPEC-04 §4.2
for why a Hungarian algorithm / scipy would be overkill here.
"""

from dataclasses import dataclass
from itertools import permutations
from math import exp, log
from typing import Dict, List, Optional

from .config_constants import role_inference_config, scraping_config

LANES: tuple = scraping_config.LANES


@dataclass(frozen=True)
class RoleAssignment:
    """Result of infer_team_roles(): one entry per champion in the team."""

    roles: Dict[int, str]  # championId -> lane
    confidence: Dict[int, float]  # championId -> [0, 1]
    source: Dict[int, str]  # championId -> "lcu" | "inferred"


def _log_share(
    champion_id: int, lane: str, lane_distributions: Dict[int, Dict[str, float]]
) -> float:
    share = lane_distributions.get(champion_id, {}).get(lane, 0.0)
    return log(max(share, role_inference_config.EPSILON))


def _assignment_score(
    champion_ids: List[int], assignment: tuple, lane_distributions: Dict[int, Dict[str, float]]
) -> float:
    return sum(
        _log_share(champion_id, lane, lane_distributions)
        for champion_id, lane in zip(champion_ids, assignment)
    )


def _best_assignment(
    champion_ids: List[int], lanes: List[str], lane_distributions: Dict[int, Dict[str, float]]
) -> tuple:
    """(best assignment, its score) among all permutations of `lanes`."""
    best_assignment: Optional[tuple] = None
    best_score = float("-inf")
    for assignment in permutations(lanes, len(champion_ids)):
        score = _assignment_score(champion_ids, assignment, lane_distributions)
        if score > best_score:
            best_score = score
            best_assignment = assignment
    return best_assignment, best_score


def infer_team_roles(
    champion_ids: List[int],
    lane_distributions: Dict[int, Dict[str, float]],
    known_positions: Optional[Dict[int, str]] = None,
) -> RoleAssignment:
    """Assign a distinct lane to each champion of a team (partial or full).

    Args:
        champion_ids: Champions on the team, 1 to 5, no duplicates.
        lane_distributions: championId -> {lane -> share%}. A champion
            missing from this dict (new champion, no data) is treated as
            having a uniform (all-EPSILON) distribution.
        known_positions: championId -> lane, for champions whose role is
            certain (LCU `assignedPosition`). These lanes are removed from
            the pool before inferring the rest.

    Returns:
        RoleAssignment covering every champion in `champion_ids`.
    """
    known_positions = known_positions or {}
    roles: Dict[int, str] = {}
    confidence: Dict[int, float] = {}
    source: Dict[int, str] = {}

    free_champions: List[int] = []
    for champion_id in champion_ids:
        if champion_id in known_positions:
            roles[champion_id] = known_positions[champion_id]
            confidence[champion_id] = 1.0
            source[champion_id] = "lcu"
        else:
            free_champions.append(champion_id)

    if not free_champions:
        return RoleAssignment(roles=roles, confidence=confidence, source=source)

    used_lanes = set(known_positions.values())
    available_lanes = [lane for lane in LANES if lane not in used_lanes]

    best_assignment, best_score = _best_assignment(
        free_champions, available_lanes, lane_distributions
    )
    for champion_id, lane in zip(free_champions, best_assignment):
        roles[champion_id] = lane
        source[champion_id] = "inferred"

    # Confidence per champion: how much better the best assignment is versus
    # the best assignment that would give this champion a different lane.
    for i, champion_id in enumerate(free_champions):
        assigned_lane = best_assignment[i]
        best_alt_score = float("-inf")
        for alt_assignment in permutations(available_lanes, len(free_champions)):
            if alt_assignment[i] == assigned_lane:
                continue
            score = _assignment_score(free_champions, alt_assignment, lane_distributions)
            if score > best_alt_score:
                best_alt_score = score

        if best_alt_score == float("-inf"):
            # No alternative lane available for this champion (fully constrained).
            confidence[champion_id] = 1.0
        else:
            confidence[champion_id] = 1.0 - exp(best_alt_score - best_score)

    return RoleAssignment(roles=roles, confidence=confidence, source=source)
