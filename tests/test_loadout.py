"""SPEC-15 §3.1 et §3.2.1 : page OneTricks, build générale et affinage au duel.

Hermétique : ``requests.get`` est simulé et les pages viennent de fixtures
enregistrées le 2026-09-24 (Jinx bot, générale et contre Draven), réduites à
l'agrégat utilisé.
"""

import copy
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from src.config_constants import draft_config
from src.draft import loadout
from src.draft.loadout import (
    Build,
    adapt_to_matchup,
    binomial_tail,
    fetch_page,
    get_build,
    get_page,
    option_name,
    pick_build,
)
from src.draft.loadout import _core_path, _option

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def html_for(page_props):
    """Page OneTricks minimale : le JSON Next.js dans sa balise script."""
    data = json.dumps({"props": {"pageProps": page_props}, "page": "/champions/builds/[id]"})
    return f'<html><script id="__NEXT_DATA__" type="application/json">{data}</script></html>'


def ok_response(page_props):
    return Mock(text=html_for(page_props), raise_for_status=Mock())


@pytest.fixture(autouse=True)
def empty_cache():
    loadout._pages.clear()
    yield
    loadout._pages.clear()


class TestPickBuild:
    def test_general_build_from_the_recorded_page(self):
        assert pick_build(load("onetricks_jinx_bot.json")) == Build(
            primary_style=8000,
            sub_style=8300,
            perks=(8008, 8009, 8017, 8313, 8321, 9103),
            shards=(5005, 5008, 5011),
            item_blocks=(
                ("Départ (94%)", (1086, 2003, 2003, 3340)),
                ("Autres départs", ()),
                ("Core (57%)", (2523, 3085)),
                ("Bottes (78%)", (3006, 3008, 3047)),
                ("Composants", (1037, 6670, 1036, 1083, 1038, 3144)),
                ("Situationnels", (3031, 3036, 3033, 3026, 3072)),
                ("Autres cores", (3032, 3046)),
            ),
            spells=(21, 4),
            games=500,
            path_games=283,
        )

    def test_matchup_page_has_the_same_shape(self):
        build = pick_build(load("onetricks_jinx_bot_vs_draven.json"))
        assert build.games == 40
        assert build.spells == (21, 4)

    @pytest.mark.parametrize(
        "breakage",
        [
            lambda page: page.pop("firstItemStats"),
            lambda page: page["firstItemStats"]["all"]["all"].update(popKeystone=[]),
            lambda page: page["firstItemStats"]["all"]["all"].update(popRunes={}),
            lambda page: page["firstItemStats"]["all"]["all"].update(sSpells=[[["21"], 1.0]]),
            lambda page: page.update(patchStats=None),
        ],
    )
    def test_unexpected_structure_gives_none(self, breakage):
        page = load("onetricks_jinx_bot.json")
        breakage(page)
        assert pick_build(page) is None


GENERAL = "onetricks_jinx_bot.json"
DUEL = "onetricks_jinx_bot_vs_draven.json"
AMBESSA = "onetricks_ambessa_top.json"
PAGES = (GENERAL, DUEL, AMBESSA)


def chosen_core(page):
    return _option(page["firstItemStats"]["all"]["all"]["popCore"][0][0])


class TestSituationalsFollowTheCore:
    """SPEC-31 : « Situationnels » = suites du core choisi (popPath), « Autres cores » = le reste."""

    @pytest.mark.parametrize("name", PAGES)
    def test_every_situational_is_in_the_core_path(self, name):
        page = load(name)
        build = pick_build(page)
        path = _core_path(page["firstItemStats"]["all"]["all"], build.games, chosen_core(page))
        blocks = dict(build.item_blocks)
        assert set(blocks["Situationnels"]) <= {item for item, _, _ in path}
        assert build.path_games > 0
        listed = [
            item
            for title, items in build.item_blocks
            for item in items
            if not title.startswith("Départ")
        ]
        assert len(listed) == len(set(listed))  # pas de doublon hors départ

    def test_ambessa_split_between_path_and_other_cores(self):
        page = load(AMBESSA)
        build = pick_build(page)
        names = page["itemData"]
        blocks = {
            title.split(" (")[0]: [names[str(item)] for item in items]
            for title, items in build.item_blocks
        }
        assert blocks["Situationnels"] == [
            "Death's Dance",
            "Maw of Malmortius",
            "Mortal Reminder",
        ]
        assert blocks["Autres cores"] == ["Spear of Shojin", "Voltaic Cyclosword", "Profane Hydra"]
        assert "Bastionbreaker" not in sum(blocks.values(), [])
        assert build.path_games == 147

    def test_path_shares_are_part_of_the_core_games(self):
        page = load(AMBESSA)
        path = _core_path(page["firstItemStats"]["all"]["all"], 500, chosen_core(page))
        assert [(item, games) for item, _, games in path] == [(6333, 77), (3156, 20), (3033, 16)]
        assert path[0][1] == pytest.approx(0.522, abs=0.001)

    def test_thresholds_are_read_from_the_config(self, monkeypatch):
        page = load(AMBESSA)
        stats_ = page["firstItemStats"]["all"]["all"]
        core = chosen_core(page)
        monkeypatch.setattr(draft_config, "LOADOUT_PATH_MIN_SHARE", 0.12)
        assert [item for item, _, _ in _core_path(stats_, 500, core)] == [6333, 3156]
        monkeypatch.setattr(draft_config, "LOADOUT_PATH_MIN_SHARE", 0.0)
        monkeypatch.setattr(draft_config, "LOADOUT_PATH_MIN_GAMES", 17)
        assert [item for item, _, _ in _core_path(stats_, 500, core)] == [6333, 3156]
        monkeypatch.setattr(draft_config, "LOADOUT_PATH_MIN_GAMES", 0)
        assert len(_core_path(stats_, 500, core)) == 5
        assert len(_core_path(stats_, 500, core, filtered=False)) == 5

    def test_unfiltered_path_keeps_the_noise(self):
        page = load(AMBESSA)
        path = _core_path(page["firstItemStats"]["all"]["all"], 500, chosen_core(page), False)
        assert [item for item, _, _ in path][-2:] == [3026, 2517]

    def test_alt_core_size_is_read_from_the_config(self, monkeypatch):
        monkeypatch.setattr(draft_config, "LOADOUT_ALT_CORE_ITEMS", 1)
        assert len(dict(pick_build(load(AMBESSA)).item_blocks)["Autres cores"]) == 1

    @pytest.mark.parametrize(
        "breakage",
        [
            lambda stats_: stats_.pop("popPath"),
            lambda stats_: stats_.update(popPath=[]),
            lambda stats_: stats_.update(popPath=[None]),
            lambda stats_: stats_.update(popPath=[[[["x", "y"]]]]),
            lambda stats_: stats_.update(popCore=[[[6692, 3071], 0.0]]),  # part nulle
        ],
    )
    def test_missing_or_malformed_path_falls_back_to_the_popular_items(self, breakage):
        page = load(AMBESSA)
        stats_ = page["firstItemStats"]["all"]["all"]
        popular = [int(item) for item, _ in stats_["popularItems"]]
        breakage(stats_)
        build = pick_build(page)
        blocks = dict(build.item_blocks)
        assert build.path_games == 0
        assert "Autres cores" not in blocks
        listed = {
            item for title, items in build.item_blocks if title != "Situationnels" for item in items
        }
        assert blocks["Situationnels"] == tuple(
            [item for item in dict.fromkeys(popular) if item not in listed][
                : draft_config.LOADOUT_SITUATIONAL_ITEMS
            ]
        )

    def test_the_core_missing_from_popcore_gives_no_path(self):
        page = load(AMBESSA)
        assert _core_path(page["firstItemStats"]["all"]["all"], 500, (1, 2)) is None


class TestFetchPage:
    def test_request_uses_onetricks_names_role_and_browser_agent(self):
        page = load("onetricks_jinx_bot.json")
        with patch("src.draft.loadout.requests.get", return_value=ok_response(page)) as get:
            assert fetch_page("Lee Sin", "middle", opponent="Kai'Sa") == page

        url = get.call_args.args[0]
        kwargs = get.call_args.kwargs
        assert url == "https://www.onetricks.gg/champions/builds/LeeSin"
        assert kwargs["params"] == {"role": "mid", "matchup": "Kaisa"}
        assert kwargs["headers"]["User-Agent"] == draft_config.LOADOUT_USER_AGENT
        assert kwargs["timeout"] == draft_config.LOADOUT_TIMEOUT_SECONDS

    def test_unknown_lane_sends_no_role(self):
        with patch("src.draft.loadout.requests.get", return_value=ok_response({})) as get:
            fetch_page("Jinx", None)
        assert get.call_args.kwargs["params"] == {}

    @pytest.mark.parametrize(
        "response",
        [
            Mock(raise_for_status=Mock(side_effect=requests.HTTPError("429 checkpoint"))),
            Mock(text="<html>Vercel Security Checkpoint</html>", raise_for_status=Mock()),
            Mock(text='<script id="__NEXT_DATA__">{pas du json</script>', raise_for_status=Mock()),
            Mock(
                text=html_for(None).replace('"pageProps": null', '"x": 1'), raise_for_status=Mock()
            ),
        ],
        ids=["429", "no-next-data", "bad-json", "no-page-props"],
    )
    def test_failures_give_none(self, response):
        with patch("src.draft.loadout.requests.get", return_value=response):
            assert fetch_page("Jinx", "bottom") is None

    def test_network_error_gives_none(self):
        with patch("src.draft.loadout.requests.get", side_effect=requests.Timeout()):
            assert fetch_page("Jinx", "bottom") is None


class TestGetBuild:
    def test_one_http_call_per_key(self):
        """§3.5.9 : deux lock-ins sur la même clé, une seule requête."""
        page = load("onetricks_jinx_bot.json")
        with patch("src.draft.loadout.requests.get", return_value=ok_response(page)) as get:
            first = get_build("Jinx", "bottom")
            second = get_build("Jinx", "bottom")
        assert first == second is not None
        assert get.call_count == 1

    def test_failures_are_not_cached(self):
        with patch("src.draft.loadout.requests.get", side_effect=requests.Timeout()) as get:
            assert get_build("Jinx", "bottom") is None
            assert get_build("Jinx", "bottom") is None
        assert get.call_count == 2


class TestGetPage:
    def test_page_is_trimmed_to_the_all_tab_and_names(self):
        page = load("onetricks_jinx_bot.json")
        page["matchHistory"] = [{"lourd": True}]
        with patch("src.draft.loadout.requests.get", return_value=ok_response(page)):
            trimmed = get_page("Jinx", "bottom")
        assert set(trimmed) == {
            "firstItemStats",
            "patchStats",
            "itemData",
            "summonerSpells",
            "runes",
        }
        assert trimmed["summonerSpells"]["3"] == "Exhaust"

    def test_general_and_duel_pages_are_distinct_keys(self):
        page = load("onetricks_jinx_bot.json")
        with patch("src.draft.loadout.requests.get", return_value=ok_response(page)) as get:
            get_page("Jinx", "bottom")
            get_page("Jinx", "bottom", "Draven")
            get_page("Jinx", "bottom", "Draven")
        assert get.call_count == 2


def stats(page):
    return page["firstItemStats"]["all"]["all"]


class TestBinomialTail:
    def test_known_values(self):
        assert binomial_tail(40, 0.5, 0) == pytest.approx(1.0)
        assert binomial_tail(1, 0.3, 1) == pytest.approx(0.3)
        # Fatigue contre Draven, SPEC-15 §3.2.1.
        assert binomial_tail(40, 0.037, 5) == pytest.approx(0.015, abs=0.002)


class TestAdaptToMatchup:
    def test_jinx_vs_draven_swaps_a_rune_and_the_spells(self):
        """§3.5.11 : Cut Down -> Coup de Grâce, Barrière+Flash -> Fatigue+Flash."""
        build, subs = adapt_to_matchup(load(GENERAL), load(DUEL))
        assert [(sub.category, sub.old, sub.new) for sub in subs] == [
            ("Rune 3", (8017,), (8014,)),
            ("Sorts", (21, 4), (3, 4)),
        ]
        spells = subs[1]
        assert spells.duel_games == 40
        assert not spells.general_listed
        assert spells.general_share == pytest.approx(1 - 0.963, abs=0.001)  # masse restante
        assert build == replace(
            pick_build(load(GENERAL)),
            perks=(8008, 8009, 8014, 8313, 8321, 9103),
            spells=(3, 4),
        )

    def test_unlisted_option_is_bounded_by_the_remaining_mass(self, monkeypatch):
        """Le départ général ne publie qu'une option, à 94 % : le majorant d'une
        option absente est la masse restante (6 %), pas 94 %."""
        monkeypatch.setattr(draft_config, "LOADOUT_MATCHUP_ALPHA", 0.2)
        _, subs = adapt_to_matchup(load(GENERAL), load(DUEL))
        start = next(sub for sub in subs if sub.category == "Départ")
        assert start.new == (1055, 2003, 3340)  # Lame de Doran, p ~ 0.098
        assert start.general_share == pytest.approx(1 - 0.938, abs=0.001)

    def test_a_new_core_leaves_the_follow_up_items(self, monkeypatch):
        monkeypatch.setattr(draft_config, "LOADOUT_MATCHUP_ALPHA", 0.3)
        build, subs = adapt_to_matchup(load(GENERAL), load(DUEL))
        blocks = dict(build.item_blocks)
        assert blocks["Core (13%)"] == (2523, 3031)  # popularité dans le duel
        assert blocks["Situationnels"][0] == 3085  # l'ancien core, le plus joué
        assert 3031 not in blocks["Situationnels"]

    def test_most_played_significant_option_wins(self):
        general, duel = load(GENERAL), load(DUEL)
        stats(duel)["sSpells"] = [[["21", "4"], 0.5], [["3", "4"], 0.3], [["14", "4"], 0.2]]
        _, subs = adapt_to_matchup(general, duel)
        assert next(sub for sub in subs if sub.category == "Sorts").new == (3, 4)

    def test_keystone_swap_brings_the_duel_rune_page(self):
        general, duel = load(GENERAL), load(DUEL)
        page = [[8021, 8009, 8014, 8233, 8236, 9103], 0.9, [8000, 8200, 8021]]
        stats(duel)["popKeystone"] = [["8008", 0.6], ["8021", 0.4]]
        stats(duel)["popRunes"]["8021"] = [page]
        build, subs = adapt_to_matchup(general, duel)
        assert ("Keystone", (8008,), (8021,)) in [(s.category, s.old, s.new) for s in subs]
        assert build.perks == tuple(page[0])
        assert (build.primary_style, build.sub_style) == (8000, 8200)
        assert not [s for s in subs if s.category.startswith("Rune")]  # page du duel telle quelle

    def test_one_duel_game_never_flips_a_full_category(self):
        """Somme publiée = 100 % : le majorant tombe à la résolution de
        l'échantillon général (1/500), pas à 0."""
        general, duel = load(GENERAL), load(DUEL)
        stats(general)["boots"] = [["3006", 1.0]]
        stats(duel)["boots"] = [["3006", 39 / 40], ["3047", 1 / 40]]
        _, subs = adapt_to_matchup(general, duel)
        assert "Bottes" not in [sub.category for sub in subs]

    def test_empty_duel_page_changes_nothing(self):
        duel = load(DUEL)
        duel["patchStats"]["all"] = 0
        build, subs = adapt_to_matchup(load(GENERAL), duel)
        assert subs == [] and build == pick_build(load(GENERAL))

    def test_no_substitution_keeps_the_general_build(self):
        general = load(GENERAL)
        build, subs = adapt_to_matchup(general, copy.deepcopy(general))
        assert subs == []
        assert build == pick_build(general)

    @pytest.mark.parametrize(
        "breakage",
        [
            lambda duel: duel.pop("patchStats"),
            lambda duel: stats(duel).pop("sSpells"),
            lambda duel: duel["patchStats"].update(all="n/a"),
        ],
    )
    def test_malformed_duel_page_gives_none(self, breakage):
        duel = load(DUEL)
        breakage(duel)
        assert adapt_to_matchup(load(GENERAL), duel) is None


def put_in_path(page, *items):
    """Suites du core choisi : ajoute ``items`` (25 parties de 500) au 3e item de popPath[0]."""
    stats(page)["popPath"][0][0].extend([item, 0.05] for item in items)


class TestMatchupItems:
    """Situationnels : les items que le duel sur-représente passent en tête."""

    def test_unlisted_item_enters_ahead_of_a_less_significant_one(self):
        general, duel = load(GENERAL), load(DUEL)
        # Kraken Slayer 5,9 % -> 20 % ; Randuin's, non publié (majorant 2,3 %) -> 20 %.
        stats(duel)["popularItems"] = [["6672", 0.2], ["3143", 0.2]]
        put_in_path(general, 6672, 3143)  # SPEC-31 : seules les suites du core montent en tête
        build, subs = adapt_to_matchup(general, duel)
        assert dict(build.item_blocks)["Situationnels"][:2] == (3143, 6672)
        randuin = next(sub for sub in subs if sub.new == (3143,))
        assert not randuin.general_listed
        assert randuin.general_share == pytest.approx(0.023, abs=0.001)

    def test_noise_keeps_the_general_order(self):
        general, duel = load(GENERAL), load(DUEL)
        stats(duel)["popularItems"] = [["6672", 0.1]]  # 4 parties sur 40, p ~ 0.2
        build, subs = adapt_to_matchup(general, duel)
        assert subs[-1].category != "Situationnels"
        assert build.item_blocks == pick_build(general).item_blocks

    def test_general_page_without_popular_items(self):
        general, duel = load(GENERAL), load(DUEL)
        stats(general).pop("popularItems")
        stats(duel)["popularItems"] = [["6672", 0.5]]
        build, subs = adapt_to_matchup(general, duel)
        assert build.item_blocks == pick_build(general).item_blocks
        assert subs[-1].category != "Situationnels"

    def test_item_outside_the_core_path_stays_out_of_the_situationals(self):
        """Kraken Slayer (hors chemin et hors de tout core) : ignoré, non signalé."""
        general, duel = load(GENERAL), load(DUEL)
        stats(duel)["popularItems"] = [["6672", 0.5]]
        build, subs = adapt_to_matchup(general, duel)
        assert 6672 not in [item for _, items in build.item_blocks for item in items]
        assert not [sub for sub in subs if sub.category == "Situationnels"]


class TestRuneSlots:
    """§3.2.2 : la règle des items, emplacement par emplacement de la page."""

    def test_rune_shares_are_renormalised_by_the_published_pages(self):
        _, subs = adapt_to_matchup(load(GENERAL), load(DUEL))
        rune = subs[0]
        # Coup de Grâce : 6,1 % des parties, sur 70,5 % publiés en général.
        assert rune.general_share == pytest.approx(0.0606 / 0.7051, abs=0.001)
        assert rune.duel_share == pytest.approx(0.1512 / 0.6614, abs=0.001)
        assert rune.general_listed

    def test_unlisted_rune_is_bounded_by_the_least_played_page(self, monkeypatch):
        monkeypatch.setattr(draft_config, "LOADOUT_MATCHUP_ALPHA", 0.3)
        _, subs = adapt_to_matchup(load(GENERAL), load(DUEL))
        legend = next(sub for sub in subs if sub.category == "Rune 2")
        assert legend.new == (9104,)  # Legend: Alacrity, absente des pages générales
        assert not legend.general_listed
        assert legend.general_share == pytest.approx(0.0606 / 0.7051, abs=0.001)

    def test_secondary_tree_swaps_as_a_unit(self):
        general, duel = load(GENERAL), load(DUEL)
        sorcery = [[8008, 8009, 8017, 8233, 8236, 9103], 0.6, [8000, 8200, 8008]]
        stats(duel)["popRunes"]["8008"] = [sorcery, stats(duel)["popRunes"]["8008"][0]]
        build, subs = adapt_to_matchup(general, duel)
        secondary = next(sub for sub in subs if sub.category == "Secondaire")
        assert (secondary.old, secondary.new) == ((8313, 8321), (8233, 8236))
        assert build.sub_style == 8200
        assert build.perks == (8008, 8009, 8017, 8233, 8236, 9103)

    def test_sample_is_the_duel_games_with_this_keystone(self):
        duel = load(DUEL)
        stats(duel)["popKeystone"] = [["8008", 0.5]]
        _, subs = adapt_to_matchup(load(GENERAL), duel)
        assert next(sub for sub in subs if sub.category == "Rune 3").duel_games == 20

    def test_page_without_rune_tree_keeps_the_general_runes(self):
        general, duel = load(GENERAL), load(DUEL)
        general.pop("runes")
        build, subs = adapt_to_matchup(general, duel)
        assert [sub.category for sub in subs] == ["Sorts"]
        assert build.perks == pick_build(general).perks

    def test_trimmed_pages_give_the_same_substitutions(self):
        """La boucle de draft compare des pages réduites par ``_trim``."""
        raw = adapt_to_matchup(load(GENERAL), load(DUEL))
        assert adapt_to_matchup(loadout._trim(load(GENERAL)), loadout._trim(load(DUEL))) == raw


class TestOptionName:
    def test_names_come_from_the_page(self):
        page = loadout._trim(load(GENERAL))
        assert option_name(page, "Sorts", (3, 4)) == "Exhaust+Flash"
        assert option_name(page, "Core", (2523, 3031)) == "Hexoptics C44+Infinity Edge"
        assert option_name(page, "Keystone", (8008,)) == "Lethal Tempo"
        assert option_name(page, "Rune 3", (8014,)) == "Coup de Grace"
        assert option_name(page, "Secondaire", (8233, 8236)) == "Absolute Focus+Gathering Storm"

    def test_unknown_id_falls_back_to_the_id(self):
        assert option_name(loadout._trim(load(GENERAL)), "Bottes", (999999,)) == "999999"
