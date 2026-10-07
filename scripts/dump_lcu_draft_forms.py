"""Relevé des formes LCU de la draft (SPEC-21 tâche 86), en lecture seule.

À lancer client LoL ouvert, idéalement EN champ select (actions, bans, sorts, skins du champion
sélectionné). Chaque endpoint est lu (GET) et sa réponse écrite dans `outputs/lcu_forms/<nom>.json`
(ignoré par git), les identités remplacées par `anon`. Les formes qui servent aux fixtures de
`tests/fixtures/lcu_forms/` en sont tirées ; un endpoint absent est signalé, jamais une erreur.

SPEC-24 tâche 96 : `--watch` relit toutes les 2 s la session de champ select, les champions
bannissables et sélectionnables et les listes de swaps, et écrit chaque NOUVELLE forme dans
`outputs/lcu_forms/watch/<HHMMSS>_<nom>.json`. À lancer pendant une draft (survoler un ban, le
valider, demander et recevoir un swap), puis arrêter par Ctrl+C. Lectures GET seulement.

USAGE:
    python scripts/dump_lcu_draft_forms.py
    python scripts/dump_lcu_draft_forms.py --watch
"""

import json
import sys
import time
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.lcu_client import LCUClient  # noqa: E402

OUTPUT_DIR = Path(__file__).parent.parent / "outputs" / "lcu_forms"
WATCH_INTERVAL_S = 2.0
# Lu en champ select ; les chemins des swaps sont ceux de `/help`, à confirmer par ce relevé.
WATCHED = [
    ("session", "/lol-champ-select/v1/session"),
    ("bannable_champion_ids", "/lol-champ-select/v1/bannable-champion-ids"),
    ("pickable_champion_ids", "/lol-champ-select/v1/pickable-champion-ids"),
    ("pick_order_swaps", "/lol-champ-select/v1/session/pick-order-swaps"),
    ("position_swaps", "/lol-champ-select/v1/session/position-swaps"),
]
IDENTITY_KEYS = {
    "puuid",
    "summonerId",
    "accountId",
    "gameName",
    "tagLine",
    "summonerName",
    "name",
    "riotIdGameName",
    "riotIdTagLine",
    "jwt",  # écran de fin : jetons du salon de discussion (SPEC-25 tâche 112)
    "multiUserChatPassword",
}
KEPT_NAMES = {"pages", "styles", "skins"}  # `name` y désigne une page, un arbre, un skin : à garder


def anonymize(value, keep_names: bool):
    if isinstance(value, dict):
        return {
            key: (
                "anon"
                if (key in IDENTITY_KEYS or key.startswith("obfuscated"))
                and not (key == "name" and keep_names)
                else anonymize(item, keep_names)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [anonymize(item, keep_names) for item in value]
    return value


def endpoints(lcu: LCUClient, champion_id: int, summoner_id: int):
    """(nom du fichier, endpoint) ; ceux qui dépendent du champ select sont ignorés hors draft."""
    return [
        ("gameflow_phase", "/lol-gameflow/v1/gameflow-phase"),
        ("session", "/lol-champ-select/v1/session"),
        ("pickable_champion_ids", "/lol-champ-select/v1/pickable-champion-ids"),
        ("bannable_champion_ids", "/lol-champ-select/v1/bannable-champion-ids"),
        ("current_champion", "/lol-champ-select/v1/current-champion"),
        ("pages", "/lol-perks/v1/pages"),
        ("current_page", "/lol-perks/v1/currentpage"),
        ("styles", "/lol-perks/v1/styles"),
        ("perks_inventory", "/lol-perks/v1/inventory"),
        ("champions_minimal", f"/lol-champions/v1/inventories/{summoner_id}/champions-minimal"),
        (
            "skins",
            f"/lol-champions/v1/inventories/{summoner_id}/champions/{champion_id}/skins",
        ),
        ("skins_minimal", f"/lol-champions/v1/inventories/{summoner_id}/skins-minimal"),
    ]


VOLATILE_TIMER_KEYS = {
    "adjustedTimeLeftInPhase",
    "internalNowInEpochMs",
}  # changent à chaque lecture


def form_key(data) -> str:
    """Texte de comparaison : la session sans les compteurs qui avancent seuls (pas une « forme »)."""
    if isinstance(data, dict) and isinstance(data.get("timer"), dict):
        timer = {k: v for k, v in data["timer"].items() if k not in VOLATILE_TIMER_KEYS}
        data = {**data, "timer": timer}
    return json.dumps(anonymize(data, False), sort_keys=True)


def watch_once(lcu: LCUClient, seen: dict, target_dir: Path, now: str) -> int:
    """Lit les endpoints suivis, écrit les formes jamais vues ; renvoie leur nombre."""
    written = 0
    for name, endpoint in WATCHED:
        data = lcu._make_request(endpoint)
        if data is None:
            continue
        text = json.dumps(anonymize(data, False), indent=2, ensure_ascii=False, sort_keys=True)
        if seen.get(name) == form_key(data):
            continue
        seen[name] = form_key(data)
        target = target_dir / f"{now}_{name}.json"
        target.write_text(text, encoding="utf-8")
        print(f"[DATA] {now} {endpoint} -> {target.name}")
        written += 1
    return written


def watch(
    lcu: LCUClient,
    target_dir: Path = OUTPUT_DIR / "watch",
    interval: float = WATCH_INTERVAL_S,
    ticks: Optional[int] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Boucle de relevé jusqu'à Ctrl+C (ou `ticks` lectures, pour les tests)."""
    target_dir.mkdir(parents=True, exist_ok=True)
    seen: dict = {}
    count = 0
    print(f"[INFO] Relevé toutes les {interval:g} s dans {target_dir} : Ctrl+C pour arrêter")
    try:
        while ticks is None or count < ticks:
            watch_once(lcu, seen, target_dir, time.strftime("%H%M%S"))
            count += 1
            sleep(interval)
    except KeyboardInterrupt:
        print("[INFO] Relevé arrêté")


def main() -> int:
    lcu = LCUClient()
    if not lcu.connect():
        print("[ALERTE] Client LoL introuvable : ouvre-le (idéalement en champ select) et relance")
        return 1
    if "--watch" in sys.argv[1:]:
        watch(lcu)
        return 0
    me = lcu._make_request("/lol-summoner/v1/current-summoner") or {}
    session = lcu.get_champion_select_session() or {}
    local = next(
        (
            p
            for p in session.get("myTeam", [])
            if p.get("cellId") == session.get("localPlayerCellId")
        ),
        {},
    )
    champion_id = local.get("championId") or 1
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, endpoint in endpoints(lcu, champion_id, me.get("summonerId", 0)):
        data = lcu._make_request(endpoint)
        if data is None:
            print(f"[ALERTE] {endpoint} : pas de réponse")
            continue
        target = OUTPUT_DIR / f"{name}.json"
        target.write_text(
            json.dumps(anonymize(data, name in KEPT_NAMES), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"[OK] {endpoint} -> {target.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
