"""Build OneTricks importée dans le client au lock-in (SPEC-15, ADR-003).

Deux pages par draft au plus : (champion, lane) au lock-in, puis (champion,
lane, adversaire) quand l'adversaire direct est locké. On y lit l'agrégat
« 500 dernières parties de one-tricks » embarqué dans le JSON Next.js de la
page (``__NEXT_DATA__``) : il n'y a pas d'API documentée, donc tout écart de
structure donne ``None`` plutôt qu'une exception dans la boucle de draft.
"""

import json
import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import requests

from ..config_constants import draft_config
from ..constants import normalize_champion_name_for_onetricks
from .onetricks import _LANE_TO_ONETRICKS_ROLE

ONETRICKS_BUILD_URL = "https://www.onetricks.gg/champions/builds/{}"
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)

# (champion, lane, adversaire) -> build ; adversaire None = build générale.
BuildKey = Tuple[str, Optional[str], Optional[str]]


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


_builds: Dict[BuildKey, Build] = {}


def get_build(
    champion: str, lane: Optional[str], opponent: Optional[str] = None
) -> Optional[Build]:
    """``fetch_page`` + ``pick_build``, une seule requête par clé et par session.

    Seuls les succès sont mis en cache : un échec (429 passager) sera retenté
    au prochain déclenchement, qui n'a lieu qu'une fois par clé et par draft.
    """
    key = (champion, lane, opponent)
    if key not in _builds:
        page = fetch_page(champion, lane, opponent)
        build = pick_build(page) if page else None
        if build is None:
            return None
        _builds[key] = build
    return _builds[key]
