"""Relevé des formes LCU de la draft (SPEC-21 tâche 86), en lecture seule.

À lancer client LoL ouvert, idéalement EN champ select (actions, bans, sorts, skins du champion
sélectionné). Chaque endpoint est lu (GET) et sa réponse écrite dans `outputs/lcu_forms/<nom>.json`
(ignoré par git), les identités remplacées par `anon`. Les formes qui servent aux fixtures de
`tests/fixtures/lcu_forms/` en sont tirées ; un endpoint absent est signalé, jamais une erreur.

USAGE:
    python scripts/dump_lcu_draft_forms.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.lcu_client import LCUClient  # noqa: E402

OUTPUT_DIR = Path(__file__).parent.parent / "outputs" / "lcu_forms"
IDENTITY_KEYS = {"puuid", "summonerId", "accountId", "gameName", "tagLine", "summonerName", "name"}
KEPT_NAMES = {"pages", "styles", "skins"}  # `name` y désigne une page, un arbre, un skin : à garder


def anonymize(value, keep_names: bool):
    if isinstance(value, dict):
        return {
            key: (
                "anon"
                if key in IDENTITY_KEYS and not (key == "name" and keep_names)
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


def main() -> int:
    lcu = LCUClient()
    if not lcu.connect():
        print("[ALERTE] Client LoL introuvable : ouvre-le (idéalement en champ select) et relance")
        return 1
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
