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
_ITEM_BLOCK = {"Départ": 0, "Core": 1, "Bottes": 2}  # index dans Build.item_blocks


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


def pick_build(page: dict) -> Optional[Build]:
    """La build la plus jouée de la page : keystone, page de runes, core, sorts."""
    try:
        stats = page["firstItemStats"]["all"]["all"]
        keystone = stats["popKeystone"][0][0]
        perks, _, (primary_style, sub_style, _) = stats["popRunes"][str(keystone)][0]
        blocks = (
            ("Départ", stats["startingItems"][0][0]),
            ("Core", stats["popCore"][0][0]),
            ("Bottes", [stats["boots"][0][0]]),
            ("Suite", [slot[0][0] for slot in stats["popPath"][0] if slot]),
        )
        spell1, spell2 = stats["sSpells"][0][0]
        return Build(
            primary_style=int(primary_style),
            sub_style=int(sub_style),
            perks=tuple(int(perk) for perk in perks),
            shards=tuple(int(shard) for shard in stats["popStat"]),
            item_blocks=tuple((title, tuple(int(i) for i in items)) for title, items in blocks),
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
        blocks = list(build.item_blocks)
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
                index = _ITEM_BLOCK[sub.category]
                blocks[index] = (blocks[index][0], sub.new)
        # Un item passé dans le core ne doit pas réapparaître en « Suite ».
        core = set(blocks[1][1])
        blocks[3] = (blocks[3][0], tuple(i for i in blocks[3][1] if i not in core))
        return replace(build, item_blocks=tuple(blocks)), substitutions
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError):
        return None


def option_name(page: dict, category: str, option: Tuple[int, ...]) -> str:
    """Nom lisible d'une option, pour la console (ids en repli)."""
    table = {"Keystone": "keystones", "Sorts": "summonerSpells"}.get(category, "itemData")
    names = page.get(table, {})
    return "+".join(names.get(str(i), str(i)) for i in option)
