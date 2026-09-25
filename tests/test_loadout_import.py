"""SPEC-15 §3.2 et §3.5 (critères 1, 2, 3, 8, 9) : déclenchement de l'import.

Une draft rejouée tick par tick : pages OneTricks enregistrées (Jinx bot,
générale et contre Draven) derrière un ``requests.get`` simulé, et le faux
client LCU de ``test_loadout_lcu``. Aucun appel réseau réel.
"""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from src.config_constants import draft_config
from src.draft import loadout
from src.draft.loadout_import import LoadoutImporter, locked_champion
from src.draft.state import DraftState
from tests.test_loadout_lcu import FakeLCU

FIXTURES = Path(__file__).parent / "fixtures"
JINX, DRAVEN, THRESH, KAISA = 222, 119, 412, 145
NAMES = {JINX: "Jinx", DRAVEN: "Draven", THRESH: "Thresh", KAISA: "Kai'Sa"}


def page(name):
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    html = f'<script id="__NEXT_DATA__">{json.dumps({"props": {"pageProps": data}})}</script>'
    return Mock(text=html, raise_for_status=Mock())


def onetricks(url, params=None, **kwargs):
    """Sert la page du duel quand ?matchup= est présent, la générale sinon."""
    if "matchup" in (params or {}):
        return page("onetricks_jinx_bot_vs_draven.json")
    return page("onetricks_jinx_bot.json")


def session(champion=JINX, completed=True):
    """Session de champ select : le joueur local (cellule 2) sur ``champion``."""
    return {
        "localPlayerCellId": 2,
        "myTeam": [{"cellId": 2, "championId": champion}],
        "actions": [
            [{"type": "pick", "actorCellId": 2, "championId": JINX, "completed": completed}]
        ],
    }


def state(enemies=(), lanes=None):
    return DraftState(
        ally_picks=[JINX],
        enemy_picks=list(enemies),
        inferred_roles={JINX: "bottom", **(lanes or {})},
    )


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setattr(draft_config, "AUTO_IMPORT_LOADOUT", True)
    loadout._pages.clear()
    yield
    loadout._pages.clear()


@pytest.fixture
def lcu():
    return FakeLCU()


@pytest.fixture
def importer(lcu):
    monitor = Mock()
    monitor.lcu = lcu
    monitor._get_display_name = lambda champ_id: NAMES[champ_id]
    monitor.hover._resolve_player_lane.return_value = "bottom"
    return LoadoutImporter(monitor)


@pytest.fixture
def http():
    with patch("src.draft.loadout.requests.get", side_effect=onetricks) as get:
        yield get


def writes(lcu):
    return [(method, endpoint) for method, endpoint, _ in lcu.calls if method != "GET"]


class TestLockIn:
    def test_hover_imports_nothing(self, importer, lcu, http):
        """§3.5.1 : ``completed: False`` = simple survol."""
        importer.on_tick(session(completed=False), state())
        assert http.call_count == 0 and writes(lcu) == []

    def test_lock_in_imports_once(self, importer, lcu, http, capsys):
        importer.on_tick(session(), state())
        importer.on_tick(session(), state())

        assert http.call_count == 1
        assert ("POST", "/lol-perks/v1/pages") in writes(lcu)
        assert writes(lcu).count(("POST", "/lol-perks/v1/pages")) == 1
        assert (
            "[OK] Build importée : Jinx bottom (500 parties one-tricks)" in capsys.readouterr().out
        )

    def test_locked_champion_follows_a_trade(self):
        """Après un trade, l'action garde l'ancien champion ; myTeam a le nouveau."""
        assert locked_champion(session(champion=KAISA)) == KAISA
        assert locked_champion(session(completed=False)) is None


class TestRefinement:
    def test_direct_opponent_lock_refines_once(self, importer, lcu, http, capsys):
        """§3.5.2 : Draven locké bot -> une comparaison, Fatigue remplace Barrière."""
        importer.on_tick(session(), state())
        importer.on_tick(session(), state([DRAVEN], {DRAVEN: "bottom"}))
        importer.on_tick(session(), state([DRAVEN], {DRAVEN: "bottom"}))

        assert http.call_count == 2  # §3.5.9 : au plus deux pages par draft
        spells = [data for method, _, data in lcu.calls if method == "PATCH"]
        assert len(spells) == 2
        assert 3 in spells[-1].values()  # Exhaust
        out = capsys.readouterr().out
        assert "[OK] Build affinée vs Draven (40 parties) :" in out
        assert "Barrier+Flash -> Exhaust+Flash" in out
        assert "Cut Down -> Coup de Grace" in out

    def test_enemy_of_another_lane_triggers_nothing(self, importer, lcu, http):
        importer.on_tick(session(), state())
        importer.on_tick(session(), state([THRESH], {THRESH: "support"}))
        assert http.call_count == 1

    def test_no_significant_gap_writes_nothing(self, importer, lcu, http, capsys, monkeypatch):
        """Sans substitution, la build générale déjà écrite n'est pas réécrite."""
        monkeypatch.setattr(draft_config, "LOADOUT_MATCHUP_ALPHA", 1e-9)
        importer.on_tick(session(), state())
        before = len(writes(lcu))
        importer.on_tick(session(), state([DRAVEN], {DRAVEN: "bottom"}))

        assert len(writes(lcu)) == before
        assert "aucun écart significatif, build générale conservée" in capsys.readouterr().out

    def test_opponent_known_at_lock_in_goes_straight_to_the_refined_build(
        self, importer, lcu, http
    ):
        importer.on_tick(session(), state([DRAVEN], {DRAVEN: "bottom"}))
        assert writes(lcu).count(("POST", "/lol-perks/v1/pages")) == 1
        spells = [data for method, _, data in lcu.calls if method == "PATCH"]
        assert 3 in spells[-1].values()


class TestTradeAndReset:
    def test_trade_relaunches_the_import(self, importer, lcu, http):
        """§3.5.3."""
        importer.on_tick(session(), state())
        importer.on_tick(session(champion=KAISA), state())
        assert http.call_count == 2
        # La page « LS » de Jinx est remplacée par celle de Kai'Sa, pas empilée.
        assert [p["name"] for p in lcu.pages] == [draft_config.LOADOUT_PREFIX + "Kai'Sa bottom"]

    def test_reset_arms_the_next_draft(self, importer, lcu, http):
        importer.on_tick(session(), state())
        importer.reset()
        importer.on_tick(session(), state())
        assert writes(lcu).count(("POST", "/lol-perks/v1/pages")) == 2
        assert http.call_count == 1  # la page reste en cache pour la session


class TestSwitchAndFailures:
    def test_flag_off_does_nothing(self, importer, lcu, http, monkeypatch):
        """§3.5.8."""
        monkeypatch.setattr(draft_config, "AUTO_IMPORT_LOADOUT", False)
        importer.on_tick(session(), state([DRAVEN], {DRAVEN: "bottom"}))
        assert http.call_count == 0 and lcu.calls == []

    def test_onetricks_down_is_reported_once(self, importer, lcu, capsys):
        with patch(
            "src.draft.loadout.requests.get", side_effect=requests.ConnectionError("réseau")
        ) as get:
            importer.on_tick(session(), state())
            importer.on_tick(session(), state())
        assert get.call_count == 1  # pas de nouvelle tentative à chaque tick
        assert writes(lcu) == []
        assert "page OneTricks indisponible pour Jinx bottom" in capsys.readouterr().out

    def test_unexpected_error_never_escapes(self, importer, capsys):
        importer.m.hover._resolve_player_lane.side_effect = RuntimeError("boom")
        importer.on_tick(session(), DraftState())  # lane inconnue -> _resolve_player_lane
        assert "erreur inattendue (RuntimeError)" in capsys.readouterr().out
