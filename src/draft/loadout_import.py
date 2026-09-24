"""Déclenchement de l'import de build dans la boucle de draft (SPEC-15 §3.2).

À chaque tick, on calcule la build CIBLE — la build générale OneTricks de
(champion, lane), adaptée au duel dès que l'adversaire direct est locké — et
on ne l'écrit dans le client que si elle diffère de la dernière écrite. Ce seul
principe couvre le lock-in, l'affinage, le trade de champion, la correction de
lane et la réinférence de l'adversaire.

Back-reference to the monitor, like the other draft components: it reads
``lcu``, ``hover`` and ``_get_display_name`` through the monitor.
"""

from typing import Dict, Optional, Tuple

from ..config_constants import draft_config
from .loadout import Build, adapt_to_matchup, apply_build, get_page, option_name, pick_build
from .state import DraftState

# (championId, lane, adversaire) : ce qui détermine la build cible.
ImportKey = Tuple[int, Optional[str], Optional[str]]


def locked_champion(champ_select_data: Dict) -> Optional[int]:
    """Champion verrouillé par le joueur local, None tant qu'il ne fait que survoler.

    Le lock se lit sur l'action ``pick`` complétée (``completed: True``), jamais
    sur ``player_champion``, renseigné dès le survol. Le champion se lit sur
    ``myTeam`` : après un trade, c'est lui qui change, pas l'action.
    """
    cell_id = champ_select_data.get("localPlayerCellId")
    has_locked = any(
        action.get("type") == "pick"
        and action.get("actorCellId") == cell_id
        and action.get("completed", False)
        for action_set in champ_select_data.get("actions", [])
        for action in action_set
    )
    if not has_locked:
        return None
    me = next(
        (p for p in champ_select_data.get("myTeam", []) if p.get("cellId") == cell_id),
        {},
    )
    return me.get("championId") or None


class LoadoutImporter:
    """Pousse la build OneTricks dans le client, une fois par clé et par draft."""

    def __init__(self, monitor) -> None:
        self.m = monitor
        self.reset()

    def reset(self) -> None:
        """Nouvelle draft : rien n'a encore été écrit."""
        self._last_key: Optional[ImportKey] = None
        # Ce qui est écrit dans le client : (championId, libellé, build). Le
        # champion en fait partie : la page et le set portent son nom et son id.
        self._applied: Optional[Tuple[int, str, Build]] = None

    def _opponent(self, state: DraftState, lane: Optional[str]) -> Optional[str]:
        """Adversaire direct locké, s'il est le seul ennemi inféré sur notre lane."""
        if not lane:
            return None
        rivals = [c for c in state.enemy_picks if state.inferred_roles.get(c) == lane]
        return self.m._get_display_name(rivals[0]) if len(rivals) == 1 else None

    def on_tick(self, champ_select_data: Dict, state: DraftState) -> None:
        """Appelé à chaque tick de champ select ; ne lève jamais."""
        if not draft_config.AUTO_IMPORT_LOADOUT:
            return
        try:
            champion_id = locked_champion(champ_select_data)
            if champion_id is None:
                return
            lane = state.inferred_roles.get(champion_id) or self.m.hover._resolve_player_lane()
            opponent = self._opponent(state, lane)
            key = (champion_id, lane, opponent)
            if key == self._last_key:
                return
            # Une seule tentative par clé : un échec ne relance pas une
            # requête à chaque tick (SPEC-15 §3.1).
            self._last_key = key
            self._import(champion_id, lane, opponent)
        except Exception as error:
            print(f"[INFO] Build non importée : erreur inattendue ({type(error).__name__})")

    def _import(self, champion_id: int, lane: Optional[str], opponent: Optional[str]) -> None:
        name = self.m._get_display_name(champion_id)
        label = f"{name} {lane}" if lane else name
        general = get_page(name, lane)
        build = pick_build(general) if general else None
        if build is None:
            print(f"[INFO] Build non importée : page OneTricks indisponible pour {label}")
            return

        substitutions, duel_games = [], None
        if opponent:
            duel = get_page(name, lane, opponent)
            adapted = adapt_to_matchup(general, duel) if duel else None
            if adapted is None:
                print(f"[INFO] Duel vs {opponent} : page OneTricks indisponible")
            else:
                build, substitutions = adapted
                duel_games = duel["patchStats"]["all"]
                if not substitutions:
                    print(
                        f"[INFO] Duel vs {opponent} ({duel_games} parties) : aucun écart "
                        "significatif, build générale conservée"
                    )

        target = (champion_id, label, build)
        if target == self._applied:
            return
        outcome = apply_build(self.m.lcu, build, champion_id, label)
        self._applied = target
        self._report(label, build, opponent, duel_games, substitutions, general, outcome)

    @staticmethod
    def _report(label, build, opponent, duel_games, substitutions, page, outcome) -> None:
        written = [part for part, reason in outcome.items() if reason is None]
        if not written:
            reasons = "; ".join(reason for reason in outcome.values() if reason)
            print(f"[INFO] Build non importée : {reasons}")
            return
        if substitutions:
            print(f"[OK] Build affinée vs {opponent} ({duel_games} parties) :")
            for sub in substitutions:
                bound = "" if sub.general_listed else "<"
                print(
                    f"  {sub.category:<8} {option_name(page, sub.category, sub.old)} -> "
                    f"{option_name(page, sub.category, sub.new)}  "
                    f"({sub.duel_share:.0%} vs {bound}{sub.general_share:.0%} en général)"
                )
        else:
            print(
                f"[OK] Build importée : {label} ({build.games} parties one-tricks) "
                f"({', '.join(written)})"
            )
        for part, reason in outcome.items():
            if reason:
                print(f"[INFO] {part} : {reason}")
