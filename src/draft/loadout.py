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
from collections import Counter
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Tuple

import requests

from ..config_constants import draft_config
from ..constants import normalize_champion_name_for_onetricks

ONETRICKS_BUILD_URL = "https://www.onetricks.gg/champions/builds/{}"
# Lanes internes -> paramètre ?role= d'OneTricks ("mid"/"bot" au lieu de
# "middle"/"bottom" ; top, jungle et support sont identiques).
LANE_TO_ONETRICKS_ROLE = {"middle": "mid", "bottom": "bot"}
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)

# (champion, lane, adversaire) -> page ; adversaire None = page générale.
PageKey = Tuple[str, Optional[str], Optional[str]]
# Une suite du core : (item, part des parties du core, parties).
PathItem = Tuple[int, float, int]

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
# Emplacements de la page de runes comparés au duel, keystone inchangée
# (§3.2.2) : chaque rangée primaire, et l'arbre secondaire avec ses 2 runes.
RUNE_SLOTS = ("Rune 1", "Rune 2", "Rune 3")
SECONDARY = "Secondaire"


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
    path_games: int = 0  # parties du core derrière « Situationnels » (SPEC-31) ; 0 = repli


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
        params["role"] = LANE_TO_ONETRICKS_ROLE.get(lane, lane)
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
        "runes": {"subStyle": (page.get("runes") or {}).get("subStyle") or {}},
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


def _core_path(
    stats: dict, games: int, core: Tuple[int, ...], filtered: bool = True
) -> Optional[List[PathItem]]:
    """Suites du core (3e à 5e items), de la plus à la moins prise (SPEC-31 §4.2).

    ``stats`` : agrégat ALL de la page, ``games`` : ses parties. Le core est repéré par
    égalité exacte dans ``popCore`` ; son indice donne l'entrée de ``popPath``. ``filtered``
    applique ``LOADOUT_PATH_MIN_SHARE`` et ``LOADOUT_PATH_MIN_GAMES`` (bruit de queue).
    None si ``popPath`` est absent, si le core n'est pas listé ou si la structure est inattendue.
    """
    try:
        options = [(_option(raw), float(share)) for raw, share in stats["popCore"]]
        index = [option for option, _ in options].index(core)
        core_share = options[index][1]
        totals: Counter = Counter()
        for rank in stats["popPath"][index]:
            for raw, share in rank:
                totals[int(raw)] += float(share)
        path = [
            (item, total / core_share, round(total * games)) for item, total in totals.most_common()
        ]
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError):
        return None
    if not filtered:
        return path
    return [
        entry
        for entry in path
        if entry[1] >= draft_config.LOADOUT_PATH_MIN_SHARE
        and entry[2] >= draft_config.LOADOUT_PATH_MIN_GAMES
    ]


def _item_blocks(
    stats: dict,
    chosen: Dict[str, Tuple[Tuple[int, ...], float]],
    matchup_items: Tuple[int, ...] = (),
    path: Optional[List[PathItem]] = None,
) -> tuple:
    """Blocs du set, du choix le plus joué aux alternatives, façon Coachless.

    ``chosen`` : option retenue et sa popularité, par catégorie de
    ``_ITEM_CHOICES``. Chaque bloc suivant ne reprend que les items pas encore
    listés ; le départ garde ses doublons (deux potions). ``path`` : suites du
    core choisi (``_core_path``). « Situationnels » n'en contient que des suites ;
    les seconds items des autres cores vont dans « Autres cores », après (un item
    des deux reste situationnel : Death's Dance d'Ambessa, 2026-09-25). Sans
    chemin (None), « Situationnels » garde les items les plus joués.
    ``matchup_items`` : items que le duel sur-représente, en tête du bloc qui les accepte.
    """
    (start, start_share), (core, core_share), (boots, boots_share) = (
        chosen[category] for category, _ in _ITEM_CHOICES
    )

    def ids(key: str) -> List[int]:
        return [item for option, _ in stats.get(key) or [] for item in _option(option)]

    in_path = [] if path is None else [item for item, _, _ in path]
    if path is None:
        situational = [*matchup_items, *ids("popularItems")]
    else:
        situational = [
            *(item for item in matchup_items if item in in_path),
            *in_path,
        ]
    items_of_other_cores = [
        item
        for option, _ in stats.get("popCore") or []
        if _option(option) != core
        for item in _option(option)
        if path is None or item not in in_path
    ]
    blocks = [(f"Départ ({start_share:.0%})", start)]
    seen = set(start)
    sections = [
        ("Autres départs", ids("startingItems"), None),
        (f"Core ({core_share:.0%})", core, None),
        (f"Bottes ({boots_share:.0%})", boots + tuple(ids("boots")), None),
        ("Composants", ids("componentBuildPaths"), None),
        ("Situationnels", situational, draft_config.LOADOUT_SITUATIONAL_ITEMS),
    ]
    if path is not None:
        alt_matchup = [item for item in matchup_items if item in items_of_other_cores]
        sections.append(
            (
                "Autres cores",
                [*alt_matchup, *items_of_other_cores],
                draft_config.LOADOUT_ALT_CORE_ITEMS,
            )
        )
    for title, items, limit in sections:
        kept = [item for item in dict.fromkeys(items) if item not in seen][:limit]
        seen.update(kept)
        blocks.append((title, tuple(kept)))
    return tuple(blocks)


def _path_games(path: Optional[List[PathItem]], core_share: float, games: int) -> int:
    """Parties du core derrière son chemin ; 0 quand le chemin manque (repli)."""
    return 0 if path is None else round(core_share * games)


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
        games = int(page["patchStats"]["all"])
        chosen = _chosen_items(stats)
        path = _core_path(stats, games, chosen["Core"][0])
        return Build(
            primary_style=int(primary_style),
            sub_style=int(sub_style),
            perks=tuple(int(perk) for perk in perks),
            shards=tuple(int(shard) for shard in stats["popStat"]),
            item_blocks=_item_blocks(stats, chosen, path=path),
            spells=(int(spell1), int(spell2)),
            games=games,
            path_games=_path_games(path, chosen["Core"][1], games),
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


def _best_option(
    category: str,
    chosen: Tuple[int, ...],
    general: Dict[Tuple[int, ...], float],
    duel: Dict[Tuple[int, ...], float],
    ceiling: float,
    duel_games: int,
) -> Optional[Substitution]:
    """L'option du duel la plus jouée parmi celles que le duel sur-représente.

    ``general`` et ``duel`` : part de chaque option publiée ; ``ceiling`` :
    majorant de la part générale d'une option non publiée.
    """
    best = None
    for option, share in duel.items():
        if option == chosen:
            continue
        p0 = general.get(option, ceiling)
        k = round(share * duel_games)
        if binomial_tail(duel_games, p0, k) >= draft_config.LOADOUT_MATCHUP_ALPHA:
            continue
        if best is None or share > best.duel_share:
            best = Substitution(category, chosen, option, share, p0, option in general, duel_games)
    return best


def _significant(
    category: str, key: str, general: dict, duel: dict, duel_games: int
) -> Optional[Substitution]:
    """Substitution d'une catégorie publiée comme options (keystone, items, sorts)."""
    general_options = general["firstItemStats"]["all"]["all"][key]
    shares = {_option(raw): share for raw, share in general_options}
    # Option non publiée : majorée par la plus petite part publiée et par la
    # masse restante, et jamais sous la résolution de l'échantillon général
    # (sinon une seule partie de duel suffirait à la faire passer).
    ceiling = max(
        min(min(shares.values()), 1.0 - sum(shares.values())),
        1.0 / int(general["patchStats"]["all"]),
    )
    duel_shares = {_option(raw): share for raw, share in duel["firstItemStats"]["all"]["all"][key]}
    chosen = _option(general_options[0][0])
    return _best_option(category, chosen, shares, duel_shares, ceiling, duel_games)


def _matchup_items(general: dict, duel: dict, duel_games: int) -> List[Substitution]:
    """Items que le duel sur-représente significativement, du plus significatif au moins.

    Chaque item est testé seul : ``popularItems`` donne la part des parties
    où il est acheté, pas un choix exclusif. Un item non publié en général est
    majoré par le moins acheté des items publiés.
    """
    general_items = general["firstItemStats"]["all"]["all"].get("popularItems") or []
    shares = {_option(raw): share for raw, share in general_items}
    if not shares:
        return []
    ceiling = max(min(shares.values()), 1.0 / int(general["patchStats"]["all"]))
    found = []
    for raw, share in duel["firstItemStats"]["all"]["all"].get("popularItems") or []:
        item = _option(raw)
        p0 = shares.get(item, ceiling)
        p_value = binomial_tail(duel_games, p0, round(share * duel_games))
        if p_value < draft_config.LOADOUT_MATCHUP_ALPHA:
            sub = Substitution("Situationnels", (), item, share, p0, item in shares, duel_games)
            found.append((p_value, sub))
    return [sub for _, sub in sorted(found, key=lambda pair: pair[0])]


def _rune_table(page: dict) -> Dict[int, Tuple[int, int, str]]:
    """Rune -> (arbre, rangée, nom) ; la rangée 0 est celle des keystones."""
    trees = (page.get("runes") or {}).get("subStyle") or {}
    return {
        rune["id"]: (int(style), row, rune.get("name", str(rune["id"])))
        for style, tree in trees.items()
        for row, slot in enumerate(tree["slots"])
        for rune in slot["runes"]
    }


def _rune_choices(perks, primary: int, table: dict) -> Dict[str, Tuple[int, ...]]:
    """Choix d'une page pour chaque emplacement de ``RUNE_SLOTS`` et ``SECONDARY``."""
    choices = {
        RUNE_SLOTS[table[perk][1] - 1]: (perk,)
        for perk in perks
        if table[perk][0] == primary and table[perk][1]
    }
    choices[SECONDARY] = tuple(sorted(perk for perk in perks if table[perk][0] != primary))
    return choices


def _rune_shares(pages: list, table: dict) -> Dict[str, Counter]:
    """Part de chaque option d'emplacement, déduite des pages publiées.

    ponytail: OneTricks ne publie que ~4 pages par keystone (~70 % des
    parties) ; les parts sont renormalisées par leur somme, en supposant que
    le non-publié se répartit comme le publié (§3.2.2). Borne stricte (part +
    masse restante) si les substitutions se révèlent trop bruitées.
    """
    coverage = sum(share for _, share, _ in pages)
    shares = {category: Counter() for category in (*RUNE_SLOTS, SECONDARY)}
    for perks, share, (primary, _, _) in pages:
        for category, option in _rune_choices(perks, int(primary), table).items():
            shares[category][option] += share / coverage
    return shares


def _rune_substitutions(
    build: Build, general: dict, duel: dict, duel_games: int
) -> List[Substitution]:
    """Emplacements de la page générale que le duel change, à keystone égale."""
    table = _rune_table(general)
    general_stats = general["firstItemStats"]["all"]["all"]
    duel_stats = duel["firstItemStats"]["all"]["all"]
    keystone = str(general_stats["popKeystone"][0][0])
    general_pages = general_stats["popRunes"][keystone]
    duel_pages = duel_stats["popRunes"].get(keystone)
    if not table or not duel_pages:
        return []
    # Le test porte sur les parties du duel jouées avec cette keystone.
    keystone_games = round(duel_games * dict(duel_stats["popKeystone"]).get(keystone, 0.0))
    # Rune non publiée : pas plus jouée que la moins jouée des pages publiées.
    general_shares = [share for _, share, _ in general_pages]
    ceiling = max(
        min(general_shares) / sum(general_shares), 1.0 / int(general["patchStats"]["all"])
    )
    chosen = _rune_choices(build.perks, build.primary_style, table)
    general_options = _rune_shares(general_pages, table)
    duel_options = _rune_shares(duel_pages, table)
    substitutions = (
        _best_option(
            category,
            chosen.get(category, ()),
            general_options[category],
            duel_options[category],
            ceiling,
            keystone_games,
        )
        for category in (*RUNE_SLOTS, SECONDARY)
    )
    return [sub for sub in substitutions if sub is not None]


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
        if all(sub.category != "Keystone" for sub in substitutions):
            substitutions = _rune_substitutions(build, general, duel, duel_games) + substitutions
        general_stats = general["firstItemStats"]["all"]["all"]
        chosen = _chosen_items(general_stats)
        table = _rune_table(general)
        runes = _rune_choices(build.perks, build.primary_style, table) if table else {}
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
            elif sub.category in runes:
                runes[sub.category] = sub.new
                keystone = next(perk for perk in build.perks if table[perk][1] == 0)
                build = replace(
                    build,
                    sub_style=table[runes[SECONDARY][0]][0],
                    perks=tuple(sorted(sum(runes.values(), (keystone,)))),
                )
            else:
                chosen[sub.category] = (sub.new, sub.duel_share)
        matchup = _matchup_items(general, duel, duel_games)
        # Chemin du core final, lu sur la page générale (SPEC-31).
        general_games = int(general["patchStats"]["all"])
        path = _core_path(general_stats, general_games, chosen["Core"][0])
        blocks = _item_blocks(general_stats, chosen, tuple(sub.new[0] for sub in matchup), path)
        # Seuls ceux qui atterrissent en situationnels changent le set (pas un item du core).
        situational = dict(blocks)["Situationnels"]
        substitutions += [sub for sub in matchup if sub.new[0] in situational]
        build = replace(build, path_games=_path_games(path, chosen["Core"][1], general_games))
        return replace(build, item_blocks=blocks), substitutions
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError):
        return None


def option_name(page: dict, category: str, option: Tuple[int, ...]) -> str:
    """Nom lisible d'une option, pour la console (ids en repli)."""
    if category in ("Keystone", *RUNE_SLOTS, SECONDARY):
        names = {str(rune): name for rune, (_, _, name) in _rune_table(page).items()}
    else:
        names = page.get({"Sorts": "summonerSpells"}.get(category, "itemData"), {})
    return "+".join(names.get(str(i), str(i)) for i in option)
