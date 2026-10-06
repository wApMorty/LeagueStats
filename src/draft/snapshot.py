"""L'état de la draft, structuré (SPEC-21 §4.5, tâche 72).

`DraftRecommender.provide` construit ce snapshot puis imprime la même sortie console qu'avant ; le
moniteur le publie sur le bus du client, qui le dessine. Données seulement : aucune mise en forme,
aucun appel au LCU. Chaque classe se sérialise par `dataclasses.asdict` (charge utile du bus, du SSE
et des fragments).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..config_constants import draft_config
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
    skin_id: int = 0
    role: Optional[str] = None
    role_source: Optional[str] = None  # "lcu" | "inferred" | "user"
    role_confidence: Optional[float] = None
    is_local: bool = False
    is_acting: bool = False
    pick_order: Optional[int] = None  # rang de pick (1 à 10), None sans actions du LCU


@dataclass
class SnapshotSwap:
    """Un échange que la session liste avec ``cell_id`` ; l'``id`` reste côté serveur."""

    kind: str  # "pick_order" | "position"
    cell_id: int
    state: str  # AVAILABLE | SENT | RECEIVED | INVALID


@dataclass
class SnapshotSwapAdvice:
    """Un échange que le modèle conseille : ce que gagne la victoire prédite, en points."""

    kind: str  # "position" (échange de rôle) | "pick_order"
    cell_id: int  # l'autre joueur
    champion: str  # son champion
    gain_pts: float
    reason: str


@dataclass
class SnapshotBan:
    champion_id: int
    champion: str
    team: str


@dataclass
class SnapshotRecommendation:
    """Un candidat du classement de pick, tel que la recherche l'a noté."""

    champion: str
    champion_id: Optional[int]
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
    champion_id: Optional[int] = None


@dataclass
class SnapshotBanAdvice:
    """Un ban conseillé : la menace de `BanRecommender`, en points de victoire pour 100 parties."""

    champion: str
    champion_id: Optional[int]
    gain: float  # points gagnés si le champion est banni
    best_response: str  # la meilleure réponse de la pool face à lui
    best_response_value: float  # sa valeur contre lui, en points
    matchups: int  # matchups mesurés derrière le chiffre


@dataclass
class SnapshotChampion:
    """Un champion du grimoire : ses rôles, sa victoire prédite si je le prends, son gain si banni."""

    champion_id: int
    champion: str
    roles: List[str] = field(default_factory=list)
    win_probability: Optional[float] = None  # ma lane, ce champion verrouillé (0 à 1)
    ban_gain: Optional[float] = None  # points si banni (phase de bans)


@dataclass
class DraftSnapshot:
    phase: str = ""
    kind: Optional[str] = None  # "ban" | "pick" : ce qui se joue maintenant
    my_turn: bool = False
    acting_cell: Optional[int] = None
    local_cell: Optional[int] = None
    local_role: Optional[str] = None
    versus: Optional[str] = None  # l'adversaire de ma lane, s'il est connu
    time_left_ms: Optional[int] = None
    time_total_ms: Optional[int] = None
    my_ban: Optional[SnapshotBan] = None  # posé
    my_ban_hover: Optional[SnapshotBan] = None  # survolé
    allies: List[SnapshotPlayer] = field(default_factory=list)
    enemies: List[SnapshotPlayer] = field(default_factory=list)
    ally_bans: List[SnapshotBan] = field(default_factory=list)
    enemy_bans: List[SnapshotBan] = field(default_factory=list)
    recommendations: List[SnapshotRecommendation] = field(default_factory=list)
    skipped: List[SnapshotSkipped] = field(default_factory=list)
    depth: int = 0
    base_probability: Optional[float] = None  # position actuelle, côté allié (0 à 1)
    # Fin de draft attendue si l'on joue le premier du classement (la position actuelle sans lui).
    projected_probability: Optional[float] = None
    ban_advice: List[SnapshotBanAdvice] = field(default_factory=list)
    swaps: List[SnapshotSwap] = field(default_factory=list)
    swap_advice: List[SnapshotSwapAdvice] = field(default_factory=list)
    champions: List[SnapshotChampion] = field(default_factory=list)
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
    candidates: Dict[int, float] = field(
        default_factory=dict
    )  # championId -> victoire si je le prends


def _is_acting(state: DraftState, cell_id: int) -> bool:
    """Cette cellule a une action en cours (plusieurs à la fois en bans et par lots de picks)."""
    return cell_id in state.acting_cells if state.acting_cells else cell_id == state.current_actor


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
                skin_id=cell.skin_id,
                hover_id=0 if champion_id else cell.hover_id,
                hover=name(cell.hover_id) if cell.hover_id and not champion_id else None,
                role=state.inferred_roles.get(champion_id) or cell.position,
                role_source=state.role_source.get(champion_id) if champion_id else None,
                role_confidence=state.role_confidence.get(champion_id) if champion_id else None,
                is_local=cell.cell_id is not None and cell.cell_id == state.local_player_cell_id,
                is_acting=cell.cell_id is not None and _is_acting(state, cell.cell_id),
                pick_order=state.pick_order.get(cell.cell_id),
            )
        )
    return players


def _champion_table(
    monitor, analysis: "Analysis", ban_gains: Dict[int, float]
) -> List[SnapshotChampion]:
    """Tous les champions connus, annotés pour le grimoire (rôles de `lane_distributions`)."""
    distributions = getattr(monitor, "lane_distributions", None) or {}
    rows = []
    for champion_id, name in monitor.champion_id_to_name.items():
        shares = distributions.get(champion_id, {})
        roles = [
            lane
            for lane, share in sorted(shares.items(), key=lambda item: -item[1])
            if share >= draft_config.GRIMOIRE_ROLE_SHARE
        ]
        rows.append(
            SnapshotChampion(
                champion_id,
                name,
                roles,
                analysis.candidates.get(champion_id),
                ban_gains.get(champion_id),
            )
        )
    return sorted(rows, key=lambda row: row.champion.lower())


def build_snapshot(
    monitor,
    state: DraftState,
    analysis: Analysis,
    advice: Optional[str],
    swap_advice: Sequence[SnapshotSwapAdvice] = (),
) -> DraftSnapshot:
    """Le snapshot de ce tick ; `monitor` fournit les noms, la pool, les prédicats de phase et le loadout."""
    name = monitor._get_display_name  # pylint: disable=protected-access
    is_ban = monitor._is_ban_phase(state)  # pylint: disable=protected-access
    results = list(analysis.results)
    base = analysis.base_probability
    games = analysis.games_by_champion
    ids = {n.lower(): i for i, n in monitor.champion_id_to_name.items()}
    ban_rows, gains = (
        monitor.ban_advisor.advice(state, draft_config.SNAPSHOT_BAN_COUNT, ids)
        if is_ban
        else ([], {})
    )
    return DraftSnapshot(
        phase=state.phase,
        kind="ban" if is_ban else ("pick" if state.phase else None),
        my_turn=monitor._is_player_turn(state),  # pylint: disable=protected-access
        acting_cell=state.current_actor,
        local_cell=state.local_player_cell_id,
        local_role=state.ally_positions.get(state.local_player_cell_id),
        versus=analysis.direct_counter,
        time_left_ms=state.time_left_ms,
        time_total_ms=state.time_total_ms,
        my_ban=(
            SnapshotBan(state.my_ban_id, name(state.my_ban_id), ALLY) if state.my_ban_id else None
        ),
        my_ban_hover=(
            SnapshotBan(state.my_ban_hover_id, name(state.my_ban_hover_id), ALLY)
            if state.my_ban_hover_id
            else None
        ),
        allies=_team(ALLY, state.ally_cells, state.ally_picks, state, name),
        enemies=_team(ENEMY, state.enemy_cells, state.enemy_picks, state, name),
        ally_bans=[SnapshotBan(c, name(c), ALLY) for c in state.ally_bans],
        enemy_bans=[SnapshotBan(c, name(c), ENEMY) for c in state.enemy_bans],
        recommendations=[
            SnapshotRecommendation(
                champion=r.champion,
                champion_id=ids.get(r.champion.lower()),
                lane=r.lane,
                win_probability=r.win_probability,
                delta=None if base is None else (r.win_probability - base) * 100.0,
                depth=r.depth,
                games=games.get(r.champion),
                variation=[{"champion": c, "lane": lane} for c, lane in r.principal_variation],
            )
            for r in results
        ],
        skipped=[
            SnapshotSkipped(champion, count, champion_id=ids.get(champion.lower()))
            for champion, count in analysis.skipped
        ],
        depth=results[0].depth if results else 0,
        base_probability=base,
        projected_probability=results[0].win_probability if results else base,
        ban_advice=ban_rows,
        swaps=[SnapshotSwap(s.kind, s.cell_id, s.state) for s in state.swaps],
        swap_advice=list(swap_advice),
        champions=_champion_table(monitor, analysis, gains),
        pool_name=getattr(monitor, "pool_name", None),
        pool=list(getattr(monitor, "current_pool", []) or []),
        advice=advice,
        loadout=monitor.loadout.state(),
    )
