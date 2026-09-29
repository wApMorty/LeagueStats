"""Moteur de constats déterministe (SPEC-19 §6, tâche 34).

Pour chaque partie capturée : métriques des 10 participants, puis, sur les
lignes du joueur, les deux références (norme, objectif) et leurs Z, figés au
moment de la partie. Les constats classés vont dans `game_findings`.

Classement : `z_norm` quand la norme compte MIN_NORM_SAMPLE valeurs, sinon
`z_objective` ; pondéré par le rang de la métrique dans la grille du rôle.
"""

import json
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from ..config_constants import coaching_config
from ..repositories.coaching import CoachingRepository
from .grid import GRID, Reference, norm_reference, onetricks_objective, z_score
from .metrics import METRICS, compute_metrics

# (champion_id, rôle) -> références objectif par métrique.
ObjectiveFn = Callable[[int, str], Dict[str, Reference]]


@dataclass(frozen=True)
class Finding:
    metric: str
    value: float
    z: float
    reference: str  # "norm" ou "objective"
    weight: int
    norm: Optional[Reference]
    objective: Optional[Reference]

    @property
    def weighted(self) -> float:
        return self.z * self.weight


@dataclass
class GameAnalysis:
    """Ce que le rapport de fin de partie affiche."""

    game_id: int
    queue_id: int
    duration_s: int
    win: bool
    role: Optional[str]
    champion_id: int
    opponent_champion_id: Optional[int]
    values: Dict[str, float] = field(default_factory=dict)
    negatives: List[Finding] = field(default_factory=list)
    positives: List[Finding] = field(default_factory=list)
    norm_n: int = 0  # taille de la norme du rôle (la plus grande par métrique)


def usable_z(norm: Optional[Reference], z_norm, objective: Optional[Reference], z_objective):
    """(z, référence) retenus pour le classement, ou (None, None)."""
    if norm and norm.n >= coaching_config.MIN_NORM_SAMPLE and z_norm is not None:
        return z_norm, "norm"
    if objective and z_objective is not None:
        return z_objective, "objective"
    return None, None


def analyze_game(
    repo: CoachingRepository, record: dict, objective_fn: ObjectiveFn
) -> Optional[GameAnalysis]:
    """Analyse et stocke une partie capturée. None si rien n'est calculable (remake)."""
    game = json.loads(record["game"])
    timeline = json.loads(record["timeline"]) if record["timeline"] else None
    eog = json.loads(record["eog"]) if record["eog"] else None
    rows = compute_metrics(game, timeline, eog)
    pid = record["player_pid"]
    player = next((p for p in game["participants"] if p["participantId"] == pid), None)
    if not rows or player is None:
        return None

    mine = [row for row in rows if row.participant_id == pid]
    role = mine[0].role if mine else None
    team = player["teamId"]
    opponent = next(
        (r.champion_id for r in rows if role and r.role == role and r.team_id != team), None
    )
    analysis = GameAnalysis(
        game_id=record["game_id"],
        queue_id=record["queue_id"],
        duration_s=record["duration_s"] or game.get("gameDuration", 0),
        win=bool(player["stats"]["win"]),
        role=role,
        champion_id=player["championId"],
        opponent_champion_id=opponent,
    )
    objectives = objective_fn(player["championId"], role) if role else {}
    grid = GRID.get(role, {})

    stored, findings = [], []
    for row in rows:
        base = (record["game_id"], row.participant_id, row.metric)
        if row.participant_id != pid:
            stored.append(base + (0, row.role, row.champion_id, row.value) + (None,) * 9)
            continue
        norm = objective = None
        if role:
            norm = norm_reference(
                row.metric,
                repo.norm_values(
                    role, row.metric, record["created"], coaching_config.NORM_WINDOW_GAMES
                ),
            )
            objective = objectives.get(row.metric)
        sense = METRICS[row.metric].sense
        z_norm, z_obj = z_score(row.value, norm, sense), z_score(row.value, objective, sense)
        stored.append(
            base
            + (1, row.role, row.champion_id, row.value)
            + (norm.mean if norm else None, norm.sd if norm else None, norm.n if norm else 0)
            + (z_norm,)
            + (objective.mean if objective else None, objective.sd if objective else None)
            + (objective.source if objective else None, z_obj, coaching_config.GRID_VERSION)
        )
        analysis.values[row.metric] = row.value
        analysis.norm_n = max(analysis.norm_n, norm.n if norm else 0)
        z, reference = usable_z(norm, z_norm, objective, z_obj)
        if row.metric in grid and z is not None:
            findings.append(
                Finding(row.metric, row.value, z, reference, grid[row.metric], norm, objective)
            )
    repo.insert_metrics(stored)

    negatives = sorted(
        (f for f in findings if f.z <= -coaching_config.MIN_ABS_Z), key=lambda f: f.weighted
    )[: coaching_config.TOP_NEGATIVE]
    positives = sorted(
        (f for f in findings if f.z >= coaching_config.MIN_ABS_Z), key=lambda f: -f.weighted
    )[: coaching_config.TOP_POSITIVE]
    analysis.negatives, analysis.positives = negatives, positives
    repo.insert_findings(
        [
            (record["game_id"], f.metric, polarity, f.z, f.reference, rank)
            for polarity, group in (("negative", negatives), ("positive", positives))
            for rank, f in enumerate(group, 1)
        ]
    )
    return analysis


def default_objective(db) -> ObjectiveFn:
    """Objectif OneTricks, le nom du champion lu en base."""

    def objective(champion_id: int, role: str) -> Dict[str, Reference]:
        name = db.get_champion_by_id(champion_id)
        return onetricks_objective(name, role) if name else {}

    return objective


def analyze_pending(db, objective_fn: Optional[ObjectiveFn] = None) -> List[GameAnalysis]:
    """Analyse les parties capturées pas encore analysées, dans l'ordre chronologique.

    Une grille changée (`GRID_VERSION`) déclenche d'abord le recalcul complet.
    """
    repo = CoachingRepository(db)
    if repo.has_stale_analysis(coaching_config.GRID_VERSION):
        repo.clear_analysis()
    objective_fn = objective_fn or default_objective(db)
    analyses = []
    for record in repo.unanalyzed_games():
        try:
            analysis = analyze_game(repo, record, objective_fn)
        except (KeyError, TypeError, ValueError, IndexError):
            continue  # brut inattendu : les parties suivantes passent quand même
        if analysis:
            analyses.append(analysis)
    return analyses
