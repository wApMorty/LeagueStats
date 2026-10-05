"""L'état de la draft, structuré (SPEC-21 §4.5, tâche 72).

`DraftRecommender.provide` construit ce snapshot puis imprime la même sortie console qu'avant ; le
moniteur le publie sur le bus du client, qui le dessine. Données seulement : aucune mise en forme,
aucun appel au LCU. Chaque classe se sérialise par `dataclasses.asdict` (charge utile du bus, du SSE
et des fragments).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .search import SearchResult
from .state import Cell, DraftState

TOPIC = "draft"  # sujet du bus

ALLY, ENEMY = "ally", "enemy"


@dataclass
class SnapshotPlayer:
    """Un emplacement d'équipe."""

    team: str
    cell_id: Optional[int]
    champion_id: int = 0  # verrouillé (0 : aucun)
    champion: Optional[str] = None
    hover_id: int = 0  # survolé, pas encore verrouillé
    hover: Optional[str] = None
    role: Optional[str] = None
    role_source: Optional[str] = None  # "lcu" | "inferred" | "user"
    role_confidence: Optional[float] = None
    is_local: bool = False
    is_acting: bool = False


@dataclass
class SnapshotBan:
    champion_id: int
    champion: str
    team: str


@dataclass
class SnapshotRecommendation:
    """Un candidat du classement de pick, tel que la recherche l'a noté."""

    champion: str
    lane: Optional[str]
    win_probability: float  # 0 à 1
    delta: Optional[float]  # points de victoire face à la position actuelle
    depth: int
    games: Optional[int]
    variation: List[Dict[str, Optional[str]]] = field(default_factory=list)  # suite attendue


@dataclass
class SnapshotSkipped:
    """Un champion du pool écarté du classement (SPEC-09 : ignorance visible)."""

    champion: str
    games: int
    reason: str = "no_data"


@dataclass
class DraftSnapshot:
    phase: str = ""
    kind: Optional[str] = None  # "ban" | "pick" : ce qui se joue maintenant
    my_turn: bool = False
    acting_cell: Optional[int] = None
    local_cell: Optional[int] = None
    local_role: Optional[str] = None
    time_left_ms: Optional[int] = None
    allies: List[SnapshotPlayer] = field(default_factory=list)
    enemies: List[SnapshotPlayer] = field(default_factory=list)
    ally_bans: List[SnapshotBan] = field(default_factory=list)
    enemy_bans: List[SnapshotBan] = field(default_factory=list)
    recommendations: List[SnapshotRecommendation] = field(default_factory=list)
    skipped: List[SnapshotSkipped] = field(default_factory=list)
    depth: int = 0
    base_probability: Optional[float] = None  # position actuelle, côté allié (0 à 1)
    pool_name: Optional[str] = None
    pool: List[str] = field(default_factory=list)
    advice: Optional[str] = None
    loadout: Optional[Dict[str, Any]] = None


@dataclass
class Analysis:
    """Ce que `DraftRecommender` calcule avant d'imprimer, et que le snapshot reprend."""

    player_lane: Optional[str] = None
    direct_counter: Optional[str] = None
    base_probability: Optional[float] = None
    results: Sequence[SearchResult] = ()
    games_by_champion: Dict[str, int] = field(default_factory=dict)
    skipped: List[Tuple[str, int]] = field(default_factory=list)


def _team(
    team: str, cells: Sequence[Cell], picks: Sequence[int], state: DraftState, name
) -> List[SnapshotPlayer]:
    """Les emplacements d'une équipe ; sans cellules (LCU ancien, tests), les picks seuls."""
    if not cells:
        cells = [Cell(cell_id=None, champion_id=champion_id) for champion_id in picks]
    players = []
    for cell in cells:
        champion_id = cell.champion_id
        players.append(
            SnapshotPlayer(
                team=team,
                cell_id=cell.cell_id,
                champion_id=champion_id,
                champion=name(champion_id) if champion_id else None,
                hover_id=0 if champion_id else cell.hover_id,
                hover=name(cell.hover_id) if cell.hover_id and not champion_id else None,
                role=state.inferred_roles.get(champion_id) or cell.position,
                role_source=state.role_source.get(champion_id) if champion_id else None,
                role_confidence=state.role_confidence.get(champion_id) if champion_id else None,
                is_local=cell.cell_id is not None and cell.cell_id == state.local_player_cell_id,
                is_acting=cell.cell_id is not None and cell.cell_id == state.current_actor,
            )
        )
    return players


def build_snapshot(
    monitor, state: DraftState, analysis: Analysis, advice: Optional[str]
) -> DraftSnapshot:
    """Le snapshot de ce tick ; `monitor` fournit les noms, la pool, les prédicats de phase et le loadout."""
    name = monitor._get_display_name  # pylint: disable=protected-access
    is_ban = monitor._is_ban_phase(state)  # pylint: disable=protected-access
    results = list(analysis.results)
    base = analysis.base_probability
    games = analysis.games_by_champion
    return DraftSnapshot(
        phase=state.phase,
        kind="ban" if is_ban else ("pick" if state.phase else None),
        my_turn=monitor._is_player_turn(state),  # pylint: disable=protected-access
        acting_cell=state.current_actor,
        local_cell=state.local_player_cell_id,
        local_role=state.ally_positions.get(state.local_player_cell_id),
        time_left_ms=state.time_left_ms,
        allies=_team(ALLY, state.ally_cells, state.ally_picks, state, name),
        enemies=_team(ENEMY, state.enemy_cells, state.enemy_picks, state, name),
        ally_bans=[SnapshotBan(c, name(c), ALLY) for c in state.ally_bans],
        enemy_bans=[SnapshotBan(c, name(c), ENEMY) for c in state.enemy_bans],
        recommendations=[
            SnapshotRecommendation(
                champion=r.champion,
                lane=r.lane,
                win_probability=r.win_probability,
                delta=None if base is None else (r.win_probability - base) * 100.0,
                depth=r.depth,
                games=games.get(r.champion),
                variation=[{"champion": c, "lane": lane} for c, lane in r.principal_variation],
            )
            for r in results
        ],
        skipped=[SnapshotSkipped(champion, count) for champion, count in analysis.skipped],
        depth=results[0].depth if results else 0,
        base_probability=base,
        pool_name=getattr(monitor, "pool_name", None),
        pool=list(getattr(monitor, "current_pool", []) or []),
        advice=advice,
        loadout=monitor.loadout.state(),
    )
