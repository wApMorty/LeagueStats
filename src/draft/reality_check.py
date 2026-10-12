"""Comparaison des postes prédits et des postes réels en partie (SPEC-27 §4.3, tâche 124).

Fonctions pures : relevé `allPlayers` (voir `client/ingame.py:roster_of`) et
dictionnaire championId -> nom d'affichage de la draft -> comparaison. Aucune
base, aucun LCU, aucun bus.

Une vérification absente vaut mieux qu'une fausse : un champion dont le nom
n'est pas retrouvé de façon univoque, ou dont l'équipe n'a pas ses cinq postes
valides et distincts, n'entre dans aucun résultat.
"""

import re
from dataclasses import replace
from typing import Any, Dict, List, Optional, Set, Tuple

from ..coaching.metrics import EOG_POSITIONS
from ..config_constants import draft_config
from .final_analysis import TOPIC as GAME_TOPIC
from .final_analysis import build_final_analysis

INGAME_TOPIC = "ingame"  # sujet du bus publié par `client.ingame.LiveGame`
LANE_FR = {
    "top": "haut",
    "jungle": "jungle",
    "middle": "milieu",
    "bottom": "bas",
    "support": "support",
}


def _key(name: str) -> str:
    """Clé de comparaison d'un nom : minuscules, sans caractère non alphanumérique."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def resolve_champions(
    roster: List[Dict[str, Any]], names: Dict[int, str]
) -> Dict[int, Dict[str, Any]]:
    """championId -> entrée du relevé, pour les seuls noms retrouvés de façon univoque.

    `names` : championId -> nom d'affichage de la draft. La clé est essayée d'abord sur
    `raw` (Wukong / MonkeyKing), puis sur `champion` (Nunu & Willump / Nunu). Zéro ou
    plusieurs entrées : le champion est absent, jamais deviné.
    """
    resolved: Dict[int, Dict[str, Any]] = {}
    for champion_id, name in names.items():
        wanted = _key(name)
        if not wanted:
            continue
        matches = [entry for entry in roster if _key(entry.get("raw") or "") == wanted]
        if not matches:
            matches = [entry for entry in roster if _key(entry.get("champion") or "") == wanted]
        if len(matches) == 1:
            resolved[champion_id] = matches[0]
    return resolved


def real_lanes(resolved: Dict[int, Dict[str, Any]]) -> Dict[int, str]:
    """championId -> lane réelle, pour les seules équipes dont les cinq postes sont valides.

    Une équipe n'est retenue que si elle a cinq champions résolus, tous avec un poste de
    `EOG_POSITIONS`, et cinq postes distincts. Sinon aucun de ses champions n'apparaît.
    """
    by_team: Dict[str, List[tuple]] = {}
    for champion_id, entry in resolved.items():
        by_team.setdefault(entry.get("team") or "", []).append(
            (champion_id, entry.get("position") or "")
        )

    lanes: Dict[int, str] = {}
    for members in by_team.values():
        positions = [position for _, position in members]
        if (
            len(members) != 5
            or any(p not in EOG_POSITIONS for p in positions)
            or len(set(positions)) != 5
        ):
            continue
        for champion_id, position in members:
            lanes[champion_id] = EOG_POSITIONS[position]
    return lanes


def compare(predicted: Dict[int, str], real: Dict[int, str]) -> Dict[str, Any]:
    """Confronte les lanes prédites aux lanes réelles.

    Retourne `{"checked": n, "mismatches": [{"champion_id", "predicted", "real"}],
    "unverified": [champion_id, ...]}`. `checked` compte les ids présents des deux côtés ;
    `unverified` liste les ids prédits absents de `real` ; un id de `real` absent de
    `predicted` est ignoré.
    """
    checked = 0
    mismatches: List[Dict[str, Any]] = []
    unverified: List[int] = []
    for champion_id, lane in predicted.items():
        if champion_id not in real:
            unverified.append(champion_id)
            continue
        checked += 1
        if real[champion_id] != lane:
            mismatches.append(
                {"champion_id": champion_id, "predicted": lane, "real": real[champion_id]}
            )
    return {"checked": checked, "mismatches": mismatches, "unverified": unverified}


class RealityCheck:
    """Confronte les postes prédits en draft à ceux que la Live Client API donne en partie (SPEC-27).

    `step()` est appelé à chaque tour de `monitor_loop` pendant la partie ; il ne lève jamais. Le poste
    réel prime sur le poste inféré ou forcé : s'il diffère, le face-à-face, la probabilité et la build
    sont recalculés et le sujet `game` republié avec `reality`. `last_draft_state.inferred_roles` n'est
    jamais modifié : la partie suivante repart des postes de sa propre draft.
    """

    def __init__(self, monitor) -> None:
        self.m = monitor
        self._alerted: Set[str] = set()
        self.reset()

    def reset(self) -> None:
        """Nouvelle partie : rien n'a été relevé, ni corrigé."""
        self._seen: Optional[Tuple] = None  # dernier relevé de postes vu
        self._since = 0.0  # temps de jeu depuis lequel il est inchangé
        self._done: Optional[Tuple] = None  # correspondance championId -> lane déjà traitée
        self._corrections = 0

    def step(self) -> None:
        """Un tour : lit le relevé, attend qu'il soit stable, vérifie et corrige une fois par relevé."""
        try:
            self._step()
        except Exception as error:  # pylint: disable=broad-exception-caught
            message = f"{type(error).__name__}: {error}"
            if message not in self._alerted:
                self._alerted.add(message)
                print(f"[INFO] Vérification des postes en partie impossible ({message})")

    def _step(self) -> None:
        bus = getattr(self.m, "bus", None)
        draft = self.m.last_draft_state
        if bus is None or not self.m.has_analyzed_final_draft:
            return
        ingame = bus.latest(INGAME_TOPIC)
        if (
            not isinstance(ingame, dict)
            or ingame.get("state") != "live"
            or not ingame.get("roster")
        ):
            return
        roster, game_time = ingame["roster"], float(ingame.get("game_time") or 0.0)

        signature = tuple((e["raw"], e["team"], e["position"]) for e in roster)
        if signature != self._seen:
            self._seen, self._since = signature, game_time
            return
        if game_time - self._since < draft_config.REALITY_STABLE_S:
            return

        picks = [*draft.ally_picks, *draft.enemy_picks]
        resolved = resolve_champions(roster, {c: self.m._get_display_name(c) for c in picks})
        real = real_lanes(resolved)
        fingerprint = tuple(sorted(real.items()))
        if fingerprint == self._done:
            return
        self._done = fingerprint

        predicted = {c: draft.inferred_roles[c] for c in picks if c in draft.inferred_roles}
        result = compare(predicted, real)
        if result["mismatches"]:
            self._correct(draft, real, result, game_time)
        else:
            self._confirm(bus, result, game_time)

    def _confirm(self, bus, result: Dict[str, Any], game_time: float) -> None:
        """Aucun écart : l'analyse de la draft reste, avec le constat à côté."""
        complete = result["checked"] > 0 and not result["unverified"]
        state = "ok" if complete else "partial"
        if complete:
            print(
                f"[OK] Postes vérifiés en partie : {result['checked']}/{result['checked']} conformes"
            )
        else:
            print(
                f"[INFO] Postes vérifiés en partie : {result['checked']} conformes, "
                f"{len(result['unverified'])} non lus (relevé incomplet ou ambigu)"
            )
        published = bus.latest(GAME_TOPIC)
        if isinstance(published, dict):
            reality = {
                "state": state,
                "checked": result["checked"],
                "mismatches": [],
                "at": game_time,
            }
            bus.publish(GAME_TOPIC, {**published, "reality": reality})

    def _correct(
        self, draft, real: Dict[int, str], result: Dict[str, Any], game_time: float
    ) -> None:
        """Écarts : recalcule le face-à-face et la build avec les postes réels, puis republie."""
        shown = [
            {
                "champion": self.m._get_display_name(m["champion_id"]),
                "predicted": LANE_FR.get(m["predicted"], m["predicted"]),
                "real": LANE_FR.get(m["real"], m["real"]),
            }
            for m in result["mismatches"]
        ]
        print(
            "[ALERTE] Postes corrigés en partie : "
            + ", ".join(f"{m['champion']} {m['predicted']} -> {m['real']}" for m in shown)
        )
        if self._corrections >= draft_config.REALITY_MAX_CORRECTIONS:
            print("[INFO] Face-à-face conservé : limite de corrections par partie atteinte")
            return
        self._corrections += 1

        lanes = {**draft.inferred_roles, **real}
        self._retarget_build(draft, lanes)
        analysis = build_final_analysis(self.m, draft.ally_picks, draft.enemy_picks, lanes)
        analysis.reality = {
            "state": "corrected",
            "checked": result["checked"],
            "mismatches": shown,
            "at": game_time,
        }
        if self.m.last_draft_state is not draft or not self.m.has_analyzed_final_draft:
            return  # la partie a changé pendant le calcul : ne rien republier
        self.m.bus.publish(GAME_TOPIC, analysis.to_payload())
        print("[INFO] Face-à-face et build recalculés")

    def _retarget_build(self, draft, lanes: Dict[int, str]) -> None:
        """Build du vrai poste et du vrai vis-à-vis ; sans effet si la page est choisie à la main."""
        loadout = self.m.loadout
        mine = (loadout.state() or {}).get("champion_id")
        if loadout.manual or mine not in lanes:
            return
        merged = replace(draft, inferred_roles=lanes)
        opponent = loadout.direct_opponent(merged, lanes[mine])
        loadout.retarget(mine, lanes[mine], opponent)
