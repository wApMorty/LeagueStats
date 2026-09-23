"""SPEC-15 §3.1 : lecture de la page OneTricks et choix de la build.

Hermétique : ``requests.get`` est simulé et les pages viennent de fixtures
enregistrées le 2026-09-24 (Jinx bot, générale et contre Draven), réduites à
l'agrégat utilisé.
"""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from src.config_constants import draft_config
from src.draft import loadout
from src.draft.loadout import Build, fetch_page, get_build, pick_build

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
    loadout._builds.clear()
    yield
    loadout._builds.clear()


class TestPickBuild:
    def test_general_build_from_the_recorded_page(self):
        assert pick_build(load("onetricks_jinx_bot.json")) == Build(
            primary_style=8000,
            sub_style=8300,
            perks=(8008, 8009, 8017, 8313, 8321, 9103),
            shards=(5005, 5008, 5011),
            item_blocks=(
                ("Départ", (1086, 2003, 2003, 3340)),
                ("Core", (2523, 3085)),
                ("Bottes", (3006,)),
                ("Suite", (3031, 3036, 3026)),
            ),
            spells=(21, 4),
            games=500,
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
