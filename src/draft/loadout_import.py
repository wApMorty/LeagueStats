"""Déclenchement de l'import de build dans la boucle de draft (SPEC-15 §3.2).

À chaque tick, on calcule la build CIBLE — la build générale OneTricks de
(champion, lane), adaptée au duel dès que l'adversaire direct est locké — et
on ne l'écrit dans le client que si elle diffère de la dernière écrite. Ce seul
principe couvre le lock-in, l'affinage, le trade de champion, la correction de
lane et la réinférence de l'adversaire.

Back-reference to the monitor, like the other draft components: it reads
``lcu``, ``hover`` and ``_get_display_name`` through the monitor.
"""

from typing import Dict, List, Optional, Tuple

from ..config_constants import draft_config
from .loadout import (
    Build,
    Substitution,
    adapt_to_matchup,
    get_page,
    option_name,
    pick_build,
)
from .loadout_lcu import apply_build
from .state import DraftState

# Catégories de substitution dont les options sont des objets (les autres : runes, sorts).
ITEM_CATEGORIES = ("Départ", "Core", "Bottes", "Situationnels")

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


def _skills(page: dict) -> Optional[Dict]:
    """L'ordre des compétences que la page OneTricks publie (SPEC-24 tâche 110) : la maximisation
    (« Q > E > W », part des parties) et la montée des premiers niveaux ; None si elle ne le publie pas.
    """
    try:
        stats = page["firstItemStats"]["all"]["all"]
        letters = "QWER"
        top = stats["maxSkillOrders"][0]
        path = stats["skillPaths"][0][0]
        return {
            "max_order": [letters[index] for index in top["order"]],
            "playrate": top["playrate"],
            "levels": [letters[int(step[0]["skillSlot"]) - 1] for step in path],
        }
    except (KeyError, IndexError, TypeError, ValueError):
        return None


class LoadoutImporter:
    """Pousse la build OneTricks dans le client, une fois par clé et par draft."""

    def __init__(self, monitor) -> None:
        self.m = monitor
        self.reset()

    def reset(self) -> None:
        """Nouvelle draft : rien n'a encore été écrit."""
        self.manual = False  # SPEC-21 : page choisie à la main, elle prime sur l'import
        self._last_key: Optional[ImportKey] = None
        # Ce qui est écrit dans le client : (championId, libellé, build). Le
        # champion en fait partie : la page et le set portent son nom et son id.
        self._applied: Optional[Tuple[int, str, Build]] = None
        # SPEC-24 tâche 106 : substitutions du duel et noms d'objets de cette build (pour l'écran).
        self._duel_info: Dict = {"substitutions": [], "skills": None, "item_names": {}}

    def set_manual(self, manual: bool) -> None:
        """La page est choisie à la main (l'import du lock-in s'efface) ou rendue à l'import."""
        if self.manual and not manual:
            self._last_key = None  # le prochain tick réimporte la build OneTricks
            self._applied = None
            self._duel_info = {"substitutions": [], "skills": None, "item_names": {}}
        self.manual = manual

    def state(self, with_duel: bool = False) -> Optional[Dict]:
        """Ce qui est écrit dans le client (SPEC-21 : le snapshot de draft), None avant le lock-in.

        ``with_duel`` ajoute les substitutions du duel et les noms d'objets (SPEC-24 tâche 106).
        """
        if self._applied is None:
            return None
        champion_id, label, build = self._applied
        return {
            "champion_id": champion_id,
            "label": label,
            "primary_style": build.primary_style,
            "sub_style": build.sub_style,
            "perks": list(build.perks),
            "shards": list(build.shards),
            "spells": list(build.spells),
            "item_blocks": [
                {"title": title, "items": list(items)} for title, items in build.item_blocks
            ],
            "games": build.games,
            **(self._duel_info if with_duel else {}),
        }

    def direct_opponent(self, state: DraftState, lane: Optional[str]) -> Optional[str]:
        """Adversaire direct locké, s'il est le seul ennemi inféré sur notre lane.

        Partagé avec la fenêtre OneTricks de fin de draft, qui ouvre la page du duel.
        """
        if not lane:
            return None
        rivals = [c for c in state.enemy_picks if state.inferred_roles.get(c) == lane]
        return self.m._get_display_name(rivals[0]) if len(rivals) == 1 else None

    def on_tick(self, champ_select_data: Dict, state: DraftState) -> None:
        """Appelé à chaque tick de champ select ; ne lève jamais."""
        if not draft_config.AUTO_IMPORT_LOADOUT or self.manual:
            return
        try:
            champion_id = locked_champion(champ_select_data)
            if champion_id is None:
                return
            lane = state.inferred_roles.get(champion_id) or self.m.hover._resolve_player_lane()
            opponent = self.direct_opponent(state, lane)
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

        substitutions, duel_games, duel = [], None, None
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
        self._duel_info = self._describe(build, substitutions, general, duel)
        self._report(label, build, opponent, duel_games, substitutions, general, outcome)

    @staticmethod
    def _describe(
        build: Build, substitutions: List[Substitution], page: dict, duel: Optional[dict]
    ) -> Dict:
        """Substitutions du duel (catégorie, ancien, nouveau, parts, raison) et noms d'objets."""
        names = {**((duel or {}).get("itemData") or {}), **page.get("itemData", {})}
        named = {**page, "itemData": names}  # un objet du duel absent de la page générale
        ids = {str(item) for _, items in build.item_blocks for item in items}
        rows = []
        for sub in substitutions:
            bound = "" if sub.general_listed else "<"
            ids.update(
                str(item) for item in (*sub.old, *sub.new) if sub.category in ITEM_CATEGORIES
            )
            rows.append(
                {
                    "category": sub.category,
                    "old": option_name(named, sub.category, sub.old),
                    "new": option_name(named, sub.category, sub.new),
                    "duel_share": sub.duel_share,
                    "general_share": sub.general_share,
                    "general_listed": sub.general_listed,
                    "duel_games": sub.duel_games,
                    "reason": f"{sub.duel_share:.0%} vs {bound}{sub.general_share:.0%} en général "
                    f"({sub.duel_games} parties)",
                }
            )
        return {
            "substitutions": rows,
            "skills": _skills(page),
            "item_names": {item: names[item] for item in sorted(ids) if item in names},
        }

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
                    f"  {sub.category:<10} {option_name(page, sub.category, sub.old)} -> "
                    f"{option_name(page, sub.category, sub.new)}  "
                    f"({sub.duel_share:.0%} vs {bound}{sub.general_share:.0%} en général)"
                )
        else:
            print(
                f"[OK] Build importée : {label} ({build.games} parties one-tricks) "
                f"({', '.join(written)})"
            )
        if outcome.get("sorts") is None:
            print(f"  {'Sorts':<10} {option_name(page, 'Sorts', build.spells)}")
        for part, reason in outcome.items():
            if reason:
                print(f"[INFO] {part} : {reason}")
