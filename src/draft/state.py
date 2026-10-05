"""Draft state dataclasses.

Extracted from src/draft_monitor.py (SPEC-07 E10, lot 6) : déplacement
verbatim, aucun changement de comportement. Ré-exportées par
src/draft_monitor.py pour préserver ``from src.draft_monitor import DraftState``.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .search import PickTurn


@dataclass
class ChampionAction:
    """Represents a champion pick/ban action."""

    champion_id: int
    champion_name: str
    actor_cell_id: int
    action_type: str  # "pick" or "ban"
    is_ally: bool
    completed: bool


@dataclass
class Cell:
    """Un emplacement d'équipe du champ select (SPEC-21 tâche 72)."""

    cell_id: int
    champion_id: int = 0  # champion verrouillé (0 : aucun)
    hover_id: int = 0  # champion survolé, pas encore verrouillé (0 : aucun)
    position: Optional[str] = None  # poste assigné par la file (alliés seulement)


@dataclass
class DraftState:
    """Current state of the draft."""

    phase: str = ""
    ally_picks: List[str] = field(default_factory=list)
    enemy_picks: List[str] = field(default_factory=list)
    ally_bans: List[str] = field(default_factory=list)
    enemy_bans: List[str] = field(default_factory=list)
    current_actor: Optional[int] = None
    local_player_cell_id: Optional[int] = None
    # SPEC-04 B3: lane info, filled from the LCU (ally_positions) and later
    # inferred by role_inference.py (B4) for all 10 players.
    ally_positions: Dict[int, str] = field(default_factory=dict)  # cellId -> lane
    inferred_roles: Dict[int, str] = field(default_factory=dict)  # championId -> lane
    role_confidence: Dict[int, float] = field(default_factory=dict)  # championId -> [0,1]
    # SPEC-04 B5: championId -> "lcu" | "inferred" | "user" (manual correction).
    role_source: Dict[int, str] = field(default_factory=dict)
    # SPEC-12: les picks encore à venir, dans l'ordre de la draft, pour la
    # recherche minimax. Vide hors phase de pick (ou si le payload LCU ne
    # contient aucune action non complétée), ce qui ramène le coach au
    # classement à profondeur 1.
    remaining_picks: List[PickTurn] = field(default_factory=list)
    # SPEC-21 tâche 72 : les emplacements des deux équipes (le client les dessine), et le
    # temps restant de la phase en millisecondes si le LCU l'annonce.
    ally_cells: List[Cell] = field(default_factory=list)
    enemy_cells: List[Cell] = field(default_factory=list)
    time_left_ms: Optional[int] = None
    time_total_ms: Optional[int] = None
    # Le ban du joueur local : posé (my_ban_id) ou seulement survolé (my_ban_hover_id).
    my_ban_id: int = 0
    my_ban_hover_id: int = 0

    def get_all_picks(self) -> List[str]:
        """Get all picked champions."""
        return self.ally_picks + self.enemy_picks

    def get_all_actions(self) -> List[str]:
        """Get all picks and bans."""
        return self.ally_picks + self.enemy_picks + self.ally_bans + self.enemy_bans
