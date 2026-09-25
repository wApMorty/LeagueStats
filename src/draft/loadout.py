"""Build OneTricks importée dans le client au lock-in (SPEC-15, ADR-003).

Deux pages par draft au plus : (champion, lane) au lock-in, puis (champion,
lane, adversaire) quand l'adversaire direct est locké. On y lit l'agrégat de
l'onglet ALL (tous premiers items, fenêtre des 500 dernières parties de
one-tricks) embarqué dans le JSON Next.js de la page (``__NEXT_DATA__``) : il
n'y a pas d'API documentée, donc tout écart de structure donne ``None`` plutôt
qu'une exception dans la boucle de draft.

La page du duel ne remplace pas la build générale : elle n'y substitue que ce
qu'elle sur-représente significativement (SPEC-15 §3.2.1), parce que sur ~40
parties la build la plus jouée du duel diffère surtout par le bruit.
"""

import json
import math
import re
import uuid
from collections import Counter
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Tuple

import requests

from ..config_constants import draft_config
from ..constants import normalize_champion_name_for_onetricks
from .onetricks import _LANE_TO_ONETRICKS_ROLE

ONETRICKS_BUILD_URL = "https://www.onetricks.gg/champions/builds/{}"
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)

# (champion, lane, adversaire) -> page ; adversaire None = page générale.
PageKey = Tuple[str, Optional[str], Optional[str]]

# Catégories comparées au duel, chacune comme une unité : (nom, clé OneTricks).
CATEGORIES = (
    ("Keystone", "popKeystone"),
    ("Départ", "startingItems"),
    ("Core", "popCore"),
    ("Bottes", "boots"),
    ("Sorts", "sSpells"),
)
# Composants d'items choisis un à un (substituables au duel) : (catégorie, clé).
_ITEM_CHOICES = (("Départ", "startingItems"), ("Core", "popCore"), ("Bottes", "boots"))


@dataclass(frozen=True)
class Build:
    """Ce qu'on pousse dans le client, en identifiants Riot."""

    primary_style: int
    sub_style: int
    # Les 6 runes dans l'ordre de OneTricks (triées par id, pas par
    # emplacement) : apply_build les ordonne si le LCU l'exige.
    perks: Tuple[int, ...]
    shards: Tuple[int, ...]
    item_blocks: Tuple[Tuple[str, Tuple[int, ...]], ...]  # (titre, items)
    spells: Tuple[int, int]
    games: int  # parties one-tricks derrière la page, pour la console


@dataclass(frozen=True)
class Substitution:
    """Un composant de la build générale remplacé pour le duel."""

    category: str
    old: Tuple[int, ...]
    new: Tuple[int, ...]
    duel_share: float
    general_share: float  # majorant si l'option n'est pas publiée en général
    general_listed: bool
    duel_games: int


def fetch_page(
    champion: str, lane: Optional[str], opponent: Optional[str] = None
) -> Optional[dict]:
    """``pageProps`` de la page OneTricks, ou None (réseau, 429, page inattendue)."""
    params = {}
    if lane:
        params["role"] = _LANE_TO_ONETRICKS_ROLE.get(lane, lane)
    if opponent:
        params["matchup"] = normalize_champion_name_for_onetricks(opponent)
    try:
        response = requests.get(
            ONETRICKS_BUILD_URL.format(normalize_champion_name_for_onetricks(champion)),
            params=params,
            headers={"User-Agent": draft_config.LOADOUT_USER_AGENT},
            timeout=draft_config.LOADOUT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return json.loads(_NEXT_DATA.search(response.text).group(1))["props"]["pageProps"]
    except (requests.RequestException, AttributeError, ValueError, KeyError, TypeError):
        return None


def _trim(page: dict) -> dict:
    """Ne garde de ``pageProps`` que l'onglet ALL et les noms (~250 Ko -> quelques Ko)."""

    def names(table: Optional[dict]) -> Dict[str, str]:
        return {key: value.get("name", key) for key, value in (table or {}).items()}

    return {
        "firstItemStats": {"all": {"all": page["firstItemStats"]["all"]["all"]}},
        "patchStats": page["patchStats"],
        "itemData": names(page.get("itemData")),
        "summonerSpells": names(page.get("summonerSpells")),
        "keystones": names((page.get("runes") or {}).get("keystone")),
    }


_pages: Dict[PageKey, dict] = {}


def get_page(champion: str, lane: Optional[str], opponent: Optional[str] = None) -> Optional[dict]:
    """Page réduite, une seule requête par clé et par session.

    Seuls les succès sont mis en cache : un échec (429 passager) sera retenté
    au prochain déclenchement, qui n'a lieu qu'une fois par clé et par draft.
    """
    key = (champion, lane, opponent)
    if key not in _pages:
        page = fetch_page(champion, lane, opponent)
        try:
            _pages[key] = _trim(page)
        except (KeyError, TypeError, AttributeError):
            return None
    return _pages[key]


def _item_blocks(stats: dict, chosen: Dict[str, Tuple[Tuple[int, ...], float]]) -> tuple:
    """Blocs du set, du choix le plus joué aux alternatives, façon Coachless.

    ``chosen`` : option retenue et sa popularité, par catégorie de
    ``_ITEM_CHOICES``. Chaque bloc suivant ne reprend que les items pas encore
    listés ; le départ garde ses doublons (deux potions).
    """
    (start, start_share), (core, core_share), (boots, boots_share) = (
        chosen[category] for category, _ in _ITEM_CHOICES
    )

    def ids(key: str) -> List[int]:
        return [item for option, _ in stats.get(key) or [] for item in _option(option)]

    blocks = [(f"Départ ({start_share:.0%})", start)]
    seen = set(start)
    for title, items, limit in (
        ("Autres départs", ids("startingItems"), None),
        (f"Core ({core_share:.0%})", core, None),
        ("Cores alternatifs", ids("popCore"), None),
        (f"Bottes ({boots_share:.0%})", boots + tuple(ids("boots")), None),
        ("Composants", ids("componentBuildPaths"), None),
        ("Situationnels", ids("popularItems"), draft_config.LOADOUT_SITUATIONAL_ITEMS),
    ):
        kept = [item for item in dict.fromkeys(items) if item not in seen][:limit]
        seen.update(kept)
        blocks.append((title, tuple(kept)))
    return tuple(blocks)


def _chosen_items(stats: dict) -> Dict[str, Tuple[Tuple[int, ...], float]]:
    """Option la plus jouée de chaque catégorie d'items, avec sa popularité."""
    return {
        category: (_option(stats[key][0][0]), float(stats[key][0][1]))
        for category, key in _ITEM_CHOICES
    }


def pick_build(page: dict) -> Optional[Build]:
    """La build la plus jouée de la page : keystone, page de runes, items, sorts."""
    try:
        stats = page["firstItemStats"]["all"]["all"]
        keystone = stats["popKeystone"][0][0]
        perks, _, (primary_style, sub_style, _) = stats["popRunes"][str(keystone)][0]
        spell1, spell2 = stats["sSpells"][0][0]
        return Build(
            primary_style=int(primary_style),
            sub_style=int(sub_style),
            perks=tuple(int(perk) for perk in perks),
            shards=tuple(int(shard) for shard in stats["popStat"]),
            item_blocks=_item_blocks(stats, _chosen_items(stats)),
            spells=(int(spell1), int(spell2)),
            games=int(page["patchStats"]["all"]),
        )
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def get_build(champion: str, lane: Optional[str]) -> Optional[Build]:
    """Build générale de (champion, lane)."""
    page = get_page(champion, lane)
    return pick_build(page) if page else None


# ---------- affinage au duel ----------


def _option(raw) -> Tuple[int, ...]:
    """Option OneTricks (id seul ou liste d'ids, en str ou int) -> tuple d'ints."""
    return tuple(int(x) for x in raw) if isinstance(raw, list) else (int(raw),)


def binomial_tail(n: int, p: float, k: int) -> float:
    """P(X >= k) pour X ~ Binomiale(n, p)."""
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1))


def _significant(
    category: str, key: str, general: dict, duel: dict, duel_games: int
) -> Optional[Substitution]:
    """L'option du duel la plus jouée parmi celles que le duel sur-représente."""
    general_options = general["firstItemStats"]["all"]["all"][key]
    duel_options = duel["firstItemStats"]["all"]["all"][key]
    shares = {_option(raw): share for raw, share in general_options}
    chosen = _option(general_options[0][0])
    # Option non publiée : majorée par la plus petite part publiée et par la
    # masse restante, et jamais sous la résolution de l'échantillon général
    # (sinon une seule partie de duel suffirait à la faire passer).
    ceiling = max(
        min(min(shares.values()), 1.0 - sum(shares.values())),
        1.0 / int(general["patchStats"]["all"]),
    )
    best = None
    for raw, share in duel_options:
        option = _option(raw)
        if option == chosen:
            continue
        p0 = shares.get(option, ceiling)
        k = round(share * duel_games)
        if binomial_tail(duel_games, p0, k) >= draft_config.LOADOUT_MATCHUP_ALPHA:
            continue
        if best is None or share > best.duel_share:
            best = Substitution(category, chosen, option, share, p0, option in shares, duel_games)
    return best


def adapt_to_matchup(general: dict, duel: dict) -> Optional[Tuple[Build, List[Substitution]]]:
    """Build générale, avec les substitutions significatives du duel (§3.2.1)."""
    build = pick_build(general)
    if build is None:
        return None
    try:
        duel_games = int(duel["patchStats"]["all"])
        substitutions = [
            sub
            for sub in (
                _significant(category, key, general, duel, duel_games)
                for category, key in CATEGORIES
            )
            if sub is not None
        ]
        general_stats = general["firstItemStats"]["all"]["all"]
        chosen = _chosen_items(general_stats)
        for sub in substitutions:
            if sub.category == "Keystone":
                keystone_pages = duel["firstItemStats"]["all"]["all"]["popRunes"]
                perks, _, (primary_style, sub_style, _) = keystone_pages[str(sub.new[0])][0]
                build = replace(
                    build,
                    primary_style=int(primary_style),
                    sub_style=int(sub_style),
                    perks=tuple(int(perk) for perk in perks),
                )
            elif sub.category == "Sorts":
                build = replace(build, spells=sub.new)
            else:
                chosen[sub.category] = (sub.new, sub.duel_share)
        return replace(build, item_blocks=_item_blocks(general_stats, chosen)), substitutions
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError):
        return None


def option_name(page: dict, category: str, option: Tuple[int, ...]) -> str:
    """Nom lisible d'une option, pour la console (ids en repli)."""
    table = {"Keystone": "keystones", "Sorts": "summonerSpells"}.get(category, "itemData")
    names = page.get(table, {})
    return "+".join(names.get(str(i), str(i)) for i in option)


# ---------- écritures LCU (SPEC-15 §3.3) ----------

FLASH_SPELL_ID = 4


def _owned_by_coach(name) -> bool:
    return str(name or "").startswith(draft_config.LOADOUT_PREFIX)


def _ordered_perks(lcu, build: Build) -> List[int]:
    """Runes rangées par emplacement (principal puis secondaire).

    OneTricks les donne triées par id ; l'ordre attendu par le LCU se lit dans
    /lol-perks/v1/styles. Faute de styles lisibles, on garde l'ordre reçu.
    """
    try:
        styles = {style["id"]: style for style in lcu._make_request("/lol-perks/v1/styles")}
        ordered = [
            perk
            for style_id in (build.primary_style, build.sub_style)
            for slot in styles[style_id]["slots"]
            for perk in slot["perks"]
            if perk in build.perks
        ]
    except (KeyError, TypeError):
        return list(build.perks)
    return ordered if sorted(ordered) == sorted(build.perks) else list(build.perks)


def _apply_runes(lcu, build: Build, name: str) -> Optional[str]:
    """Remplace la page « LS » ; ne touche jamais aux pages du joueur."""
    pages = lcu._make_request("/lol-perks/v1/pages")
    if pages is None:
        return "pages de runes illisibles"
    for page in pages:
        if _owned_by_coach(page.get("name")):
            lcu._make_request(f"/lol-perks/v1/pages/{page['id']}", "DELETE")
    player_pages = [p for p in pages if p.get("isDeletable") and not _owned_by_coach(p.get("name"))]
    owned = (lcu._make_request("/lol-perks/v1/inventory") or {}).get("ownedPageCount")
    if owned is not None and len(player_pages) >= owned:
        return "aucun emplacement de page de runes libre"
    created = lcu._make_request(
        "/lol-perks/v1/pages",
        "POST",
        {
            "name": draft_config.LOADOUT_PREFIX + name,
            "primaryStyleId": build.primary_style,
            "subStyleId": build.sub_style,
            "selectedPerkIds": _ordered_perks(lcu, build) + list(build.shards),
            "current": True,
        },
    )
    return None if created is not None else "page de runes refusée par le client"


def _apply_items(lcu, build: Build, champion_id: int, name: str) -> Optional[str]:
    """Remplace le set « LS » ; les sets du joueur sont renvoyés à l'identique."""
    summoner_id = (lcu._make_request("/lol-summoner/v1/current-summoner") or {}).get("summonerId")
    if summoner_id is None:
        return "invocateur inconnu"
    endpoint = f"/lol-item-sets/v1/item-sets/{summoner_id}/sets"
    current = lcu._make_request(endpoint)
    if current is None:
        return "sets d'items illisibles"
    item_set = {
        "uid": str(uuid.uuid4()),
        "title": draft_config.LOADOUT_PREFIX + name,
        "type": "custom",
        "map": "any",
        "mode": "any",
        "priority": False,
        "sortrank": 0,
        "startedFrom": "blank",
        "associatedChampions": [champion_id],
        "associatedMaps": [],
        "blocks": [
            {
                "type": title,
                "items": [{"id": str(item), "count": n} for item, n in Counter(items).items()],
            }
            for title, items in build.item_blocks
            if items
        ],
    }
    kept = [s for s in current.get("itemSets", []) if not _owned_by_coach(s.get("title"))]
    saved = lcu._make_request(endpoint, "PUT", {**current, "itemSets": kept + [item_set]})
    return None if saved is not None else "set d'items refusé par le client"


def _local_player(session: dict) -> dict:
    cell_id = session.get("localPlayerCellId")
    return next((m for m in session.get("myTeam", []) if m.get("cellId") == cell_id), {})


def _apply_spells(lcu, build: Build) -> Optional[str]:
    """Pose les sorts en gardant Flash sur la touche où le joueur l'avait."""
    spell1, spell2 = build.spells
    me = _local_player(lcu.get_champion_select_session() or {})
    if FLASH_SPELL_ID in build.spells:
        other = spell2 if spell1 == FLASH_SPELL_ID else spell1
        if me.get("spell1Id") == FLASH_SPELL_ID:
            spell1, spell2 = FLASH_SPELL_ID, other
        elif me.get("spell2Id") == FLASH_SPELL_ID:
            spell1, spell2 = other, FLASH_SPELL_ID
    done = lcu._make_request(
        "/lol-champ-select/v1/session/my-selection",
        "PATCH",
        {"spell1Id": spell1, "spell2Id": spell2},
    )
    if done is None:
        return "sorts refusés par le client"
    # Relu dans la session : un PATCH accepté puis ignoré (fin de draft) doit
    # se voir en console plutôt que passer pour un succès.
    me = _local_player(lcu.get_champion_select_session() or {})
    if (me.get("spell1Id"), me.get("spell2Id")) != (spell1, spell2):
        return "sorts ignorés par le client"
    return None


def apply_build(lcu, build: Build, champion_id: int, name: str) -> Dict[str, Optional[str]]:
    """Les trois écritures, indépendantes et best-effort.

    Renvoie, par écriture (``runes``, ``items``, ``sorts``), None si elle a
    réussi, sinon la raison de l'échec. Ne lève jamais : une erreur du client
    ne doit pas interrompre la boucle de draft.
    """
    writes = {
        "runes": lambda: _apply_runes(lcu, build, name),
        "items": lambda: _apply_items(lcu, build, champion_id, name),
        "sorts": lambda: _apply_spells(lcu, build),
    }
    outcome: Dict[str, Optional[str]] = {}
    for part, write in writes.items():
        try:
            outcome[part] = write()
        except Exception as error:  # best-effort : aucune erreur ne remonte
            outcome[part] = f"erreur inattendue ({type(error).__name__})"
    return outcome
