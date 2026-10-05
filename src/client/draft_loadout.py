"""Loadout de la draft : page de runes, sorts et objets (SPEC-21 tâches 91 et 92, SPEC-15, ADR-003).

Trois choses côté serveur :

- `plan` : la page que le Live Coach importerait pour (champion, lane, adversaire), lue sur OneTricks
  (ou, une fois le champion verrouillé, la page déjà écrite dans le client) ;
- `runes_payload` : les arbres de Data Dragon, les fragments et les sorts, pour le gabarit de la page ;
- `send` : écrit la page et les sorts choisis à la main dans le client, après validation contre les arbres.

La modification manuelle prime sur l'import automatique du lock-in : le serveur le signale au Live
Coach par la commande `loadout manual` (voir `CommandListener`).
"""

from typing import Any, Dict, List, Optional, Sequence

from ..draft import loadout as onetricks
from ..draft.loadout_lcu import _apply_runes, _apply_spells
from .draft_actions import Refusal
from .lcu_proxy import LcuProxy

SESSION = "/lol-champ-select/v1/session"

# Couleur de chaque arbre (README du handoff), par identifiant de style Riot.
TREE_COLORS = {
    8000: "oklch(0.86 0.13 85)",  # Précision
    8100: "oklch(0.70 0.21 20)",  # Domination
    8200: "oklch(0.72 0.17 280)",  # Sorcellerie
    8400: "oklch(0.78 0.15 150)",  # Volonté
    8300: "oklch(0.80 0.12 210)",  # Inspiration
}

# Fragments (patch 14+, relevé du LCU `styles` du 2026-10-05 : emplacements 4 à 6 d'un arbre).
_SHARD_ICONS = "perk-images/StatMods/StatMods{}Icon.png"
SHARD_ROWS = (
    (
        "Offensif",
        (
            (5008, "Force adaptative", "AdaptiveForce"),
            (5005, "Vitesse d'attaque", "AttackSpeed"),
            (5007, "Accélération de compétence", "CDRScaling"),
        ),
    ),
    (
        "Flexible",
        (
            (5008, "Force adaptative", "AdaptiveForce"),
            (5010, "Vitesse de déplacement", "MovementSpeed"),
            (5001, "PV croissants", "HealthScaling"),
        ),
    ),
    (
        "Défensif",
        (
            (5011, "PV +65", "HealthPlus"),
            (5013, "Ténacité et ralentissement", "Tenacity"),
            (5001, "PV croissants", "HealthScaling"),
        ),
    ),
)

# Les neuf sorts du mode classique : (identifiant Riot, clé Data Dragon, nom).
SPELLS = (
    (4, "SummonerFlash", "Flash"),
    (12, "SummonerTeleport", "Téléport"),
    (14, "SummonerDot", "Embrasement"),
    (6, "SummonerHaste", "Fantôme"),
    (3, "SummonerExhaust", "Fatigue"),
    (7, "SummonerHeal", "Soins"),
    (21, "SummonerBarrier", "Barrière"),
    (1, "SummonerBoost", "Purge"),
    (11, "SummonerSmite", "Châtiment"),
)
SPELL_IDS = {spell[0] for spell in SPELLS}


def runes_payload(styles: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Ce que la page de runes dessine : arbres (couleur, icône, rangées), fragments, sorts."""
    return {
        "styles": [
            {
                "id": style["id"],
                "name": style["name"],
                "icon": style["icon"],
                "color": TREE_COLORS.get(style["id"], "oklch(0.8 0.1 165)"),
                "slots": [
                    [
                        {"id": rune["id"], "name": rune["name"], "icon": rune["icon"]}
                        for rune in slot["runes"]
                    ]
                    for slot in style["slots"]
                ],
            }
            for style in styles
        ],
        "shards": [
            {
                "title": title,
                "options": [
                    {"id": pid, "name": name, "icon": _SHARD_ICONS.format(icon)}
                    for pid, name, icon in options
                ],
            }
            for title, options in SHARD_ROWS
        ],
        "spells": [{"id": sid, "key": key, "name": name} for sid, key, name in SPELLS],
    }


def _index(styles: Sequence[Dict[str, Any]]) -> Dict[int, List[List[int]]]:
    return {s["id"]: [[r["id"] for r in slot["runes"]] for slot in s["slots"]] for s in styles}


def normalize_page(
    styles: Sequence[Dict[str, Any]],
    primary: int,
    sub: int,
    perks: Sequence[int],
    shards: Sequence[int],
) -> Optional[Dict[str, Any]]:
    """Une liste de runes (dans un ordre quelconque) -> `{primary, sub, keystone, rows, subs, shards}`."""
    trees = _index(styles)
    if primary not in trees or sub not in trees or len(shards) != 3:
        return None
    chosen = set(perks)
    keystone = next((r for r in trees[primary][0] if r in chosen), None)
    rows = [next((r for r in trees[primary][i] if r in chosen), None) for i in (1, 2, 3)]
    subs = [r for i in (1, 2, 3) for r in trees[sub][i] if r in chosen]
    if keystone is None or None in rows or len(subs) != 2:
        return None
    return {
        "primary": primary,
        "sub": sub,
        "keystone": keystone,
        "rows": rows,
        "subs": subs,
        "shards": list(shards),
    }


def validate_page(styles: Sequence[Dict[str, Any]], page: Dict[str, Any]) -> None:
    """Lève `Refusal` si la page ne respecte pas les arbres : une rune par rangée, deux rangées au secondaire."""
    trees = _index(styles)
    primary, sub = page["primary"], page["sub"]
    if primary not in trees or sub not in trees or primary == sub:
        raise Refusal("Arbres de runes incompatibles")
    if page["keystone"] not in trees[primary][0]:
        raise Refusal("Rune majeure invalide")
    for row, rune in enumerate(page["rows"], start=1):
        if rune not in trees[primary][row]:
            raise Refusal("Rune de l'arbre principal invalide")
    rows_of_subs = [
        next((row for row in (1, 2, 3) if rune in trees[sub][row]), None) for rune in page["subs"]
    ]
    if None in rows_of_subs or len(set(rows_of_subs)) != 2:
        raise Refusal("Les deux runes secondaires doivent venir de rangées différentes")
    for shard, (_, options) in zip(page["shards"], SHARD_ROWS):
        if shard not in {option[0] for option in options}:
            raise Refusal("Fragment invalide")


def _items(build: onetricks.Build) -> List[Dict[str, Any]]:
    """Les trois blocs montrés (départ, core, bottes), titres sans le pourcentage."""
    wanted = ("Départ", "Core", "Bottes")
    blocks = []
    for title, ids in build.item_blocks:
        base = title.split(" (")[0]
        if base in wanted and ids and all(b["title"] != base for b in blocks):
            blocks.append({"title": base, "ids": list(ids)})
    return blocks


def plan(
    snapshot: Dict[str, Any], champion_id: int, styles: Sequence[Dict[str, Any]]
) -> Dict[str, Any]:
    """La page prévue pour `champion_id` ; `available` faux (avec la raison) si on ne peut pas la lire."""
    row = next((c for c in snapshot.get("champions", []) if c["champion_id"] == champion_id), None)
    if row is None:
        return {"available": False, "reason": "Champion inconnu"}
    lane = snapshot.get("local_role")
    applied = snapshot.get("loadout")
    if applied and applied["champion_id"] == champion_id:
        build = _applied_build(applied)
        source, opponent = "client", None
    else:
        build, opponent = _onetricks_build(row["champion"], lane, snapshot.get("versus"))
        source = "onetricks"
    if build is None:
        return {"available": False, "reason": "Page OneTricks indisponible pour ce champion"}
    page = normalize_page(styles, build.primary_style, build.sub_style, build.perks, build.shards)
    if page is None:
        return {"available": False, "reason": "Arbres de runes indisponibles"}
    return {
        "available": True,
        "source": source,
        "champion_id": champion_id,
        "games": build.games,
        "opponent": opponent,
        "page": page,
        "spells": list(build.spells),
        "items": _items(build),
    }


def _applied_build(applied: Dict[str, Any]) -> onetricks.Build:
    return onetricks.Build(
        primary_style=applied["primary_style"],
        sub_style=applied["sub_style"],
        perks=tuple(applied["perks"]),
        shards=tuple(applied["shards"]),
        item_blocks=tuple((b["title"], tuple(b["items"])) for b in applied["item_blocks"]),
        spells=tuple(applied["spells"]),
        games=applied["games"],
    )


def _onetricks_build(champion: str, lane: Optional[str], opponent: Optional[str]):
    """Build générale, affinée au duel quand l'adversaire de lane est connu (comme l'import du lock-in)."""
    general = onetricks.get_page(champion, lane)
    if general is None:
        return None, None
    build = onetricks.pick_build(general)
    if build is not None and opponent:
        duel = onetricks.get_page(champion, lane, opponent)
        adapted = onetricks.adapt_to_matchup(general, duel) if duel else None
        if adapted is not None:
            return adapted[0], opponent
    return build, None


class _WhitelistedLcu:
    """Ce que `loadout_lcu` attend d'un client LCU, mais qui ne sort que par la liste blanche."""

    def __init__(self, proxy: LcuProxy) -> None:
        self._proxy = proxy

    def _make_request(self, endpoint: str, method: str = "GET", data: Optional[dict] = None):
        if method == "GET":
            return self._proxy.get(endpoint)
        return self._proxy.send(method, endpoint, data)

    def get_champion_select_session(self):
        return self._proxy.get(SESSION)


def send(
    proxy: LcuProxy,
    styles: Sequence[Dict[str, Any]],
    page: Dict[str, Any],
    spells: Sequence[int],
    label: str,
) -> Dict[str, Optional[str]]:
    """Écrit la page et les sorts dans le client ; `Refusal` si la demande est invalide ou rien n'a pu être écrit."""
    validate_page(styles, page)
    if len(spells) != 2 or spells[0] == spells[1] or not set(spells) <= SPELL_IDS:
        raise Refusal("Sorts d'invocateur invalides")
    perks = (page["keystone"], *page["rows"], *page["subs"])
    build = onetricks.Build(
        primary_style=page["primary"],
        sub_style=page["sub"],
        perks=tuple(perks),
        shards=tuple(page["shards"]),
        item_blocks=(),
        spells=(spells[0], spells[1]),
        games=0,
    )
    lcu = _WhitelistedLcu(proxy)
    outcome = {
        "runes": _safely(lambda: _apply_runes(lcu, build, label)),
        "sorts": _safely(lambda: _apply_spells(lcu, build)),
    }
    if all(reason for reason in outcome.values()):
        raise Refusal(
            "Le client LoL a refusé la page et les sorts : " + "; ".join(outcome.values())
        )
    return outcome


def _safely(write) -> Optional[str]:
    try:
        return write()
    except Exception as error:  # pylint: disable=broad-exception-caught
        return f"erreur inattendue ({type(error).__name__})"
