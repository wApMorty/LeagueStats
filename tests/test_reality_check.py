"""Tests de src/draft/reality_check.py : résolution des champions, lanes réelles, comparaison (SPEC-27 §6.2-3)."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.client.bus import EventBus
from src.config_constants import draft_config
from src.draft import reality_check
from src.draft.final_analysis import FinalAnalysis
from src.draft.reality_check import RealityCheck, compare, real_lanes, resolve_champions
from src.draft.state import DraftState


def _entry(champion: str, raw: str, team: str, position: str) -> dict:
    return {"champion": champion, "raw": raw, "team": team, "position": position}


def _team(team: str, positions: list) -> list:
    return [_entry(f"Champ{team}{i}", f"Raw{team}{i}", team, p) for i, p in enumerate(positions)]


ROSTER = [
    _entry("Wukong", "MonkeyKing", "ORDER", "JUNGLE"),
    _entry("Nunu & Willump", "Nunu", "ORDER", "JUNGLE"),
    _entry("Renata Glasc", "Renata", "CHAOS", "UTILITY"),
    _entry("Lee Sin", "LeeSin", "CHAOS", "JUNGLE"),
    _entry("Twisted Fate", "TwistedFate", "ORDER", "MIDDLE"),
]


class TestResolveChampions:
    def test_five_names_resolved_via_raw_or_champion(self):
        names = {
            1: "Wukong",
            2: "Nunu & Willump",
            3: "Renata Glasc",
            4: "Lee Sin",
            5: "Twisted Fate",
        }
        resolved = resolve_champions(ROSTER, names)
        assert resolved[1]["champion"] == "Wukong"
        assert resolved[2]["champion"] == "Nunu & Willump"
        assert resolved[3]["champion"] == "Renata Glasc"
        assert resolved[4]["champion"] == "Lee Sin"
        assert resolved[5]["champion"] == "Twisted Fate"

    def test_display_name_matches_raw_key(self):
        roster = [_entry("Wukong", "MonkeyKing", "ORDER", "JUNGLE")]
        assert resolve_champions(roster, {1: "Monkey King"})[1]["champion"] == "Wukong"

    def test_display_name_matches_champion_key(self):
        roster = [_entry("Nunu & Willump", "Nunu", "ORDER", "JUNGLE")]
        assert resolve_champions(roster, {2: "Nunu & Willump"})[2]["champion"] == "Nunu & Willump"

    def test_unknown_name_absent(self):
        assert resolve_champions(ROSTER, {9: "Aatrox"}) == {}

    def test_ambiguous_name_absent(self):
        roster = [
            _entry("Lee Sin", "LeeSin", "ORDER", "JUNGLE"),
            _entry("Lee Sin", "LeeSin", "CHAOS", "JUNGLE"),
        ]
        assert resolve_champions(roster, {4: "Lee Sin"}) == {}

    def test_raw_match_takes_precedence_over_champion_match(self):
        roster = [
            _entry("Wukong", "MonkeyKing", "ORDER", "JUNGLE"),
            _entry("MonkeyKing", "Other", "CHAOS", "TOP"),
        ]
        assert resolve_champions(roster, {1: "MonkeyKing"})[1]["team"] == "ORDER"


class TestRealLanes:
    def test_complete_valid_team_kept(self):
        roster = _team("ORDER", ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"])
        resolved = resolve_champions(roster, {i: r["champion"] for i, r in enumerate(roster)})
        lanes = real_lanes(resolved)
        assert sorted(lanes.values()) == ["bottom", "jungle", "middle", "support", "top"]
        assert len(lanes) == 5

    def test_team_with_four_positions_dropped(self):
        roster = _team("ORDER", ["TOP", "JUNGLE", "MIDDLE", "BOTTOM"]) + _team(
            "CHAOS", ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
        )
        resolved = resolve_champions(roster, {i: r["champion"] for i, r in enumerate(roster)})
        lanes = real_lanes(resolved)
        assert len(lanes) == 5
        assert all(resolved[c]["team"] == "CHAOS" for c in lanes)

    def test_duplicate_position_drops_team(self):
        roster = _team("ORDER", ["TOP", "JUNGLE", "MIDDLE", "MIDDLE", "UTILITY"])
        resolved = resolve_champions(roster, {i: r["champion"] for i, r in enumerate(roster)})
        assert real_lanes(resolved) == {}

    def test_empty_position_drops_team(self):
        roster = _team("ORDER", ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", ""])
        resolved = resolve_champions(roster, {i: r["champion"] for i, r in enumerate(roster)})
        assert real_lanes(resolved) == {}


class TestCompare:
    def test_all_match(self):
        result = compare({1: "top", 2: "jungle"}, {1: "top", 2: "jungle"})
        assert result == {"checked": 2, "mismatches": [], "unverified": []}

    def test_middle_bottom_swap_detected(self):
        result = compare({1: "middle", 2: "bottom"}, {1: "bottom", 2: "middle"})
        assert result["checked"] == 2
        assert {m["champion_id"] for m in result["mismatches"]} == {1, 2}
        assert {"champion_id": 1, "predicted": "middle", "real": "bottom"} in result["mismatches"]

    def test_unverified_and_extra_real_ignored(self):
        result = compare({1: "top", 2: "jungle"}, {1: "top", 3: "support"})
        assert result == {"checked": 1, "mismatches": [], "unverified": [2]}


# ---------- RealityCheck.step (SPEC-27 tâche 126) ----------

POSITIONS = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
LANES = ["top", "jungle", "middle", "bottom", "support"]
ALLIES, ENEMIES = [1, 2, 3, 4, 5], [6, 7, 8, 9, 10]
PUBLISHED = {"lines": [], "win_probability": 0.5, "draft_diff": 0.0, "evaluation": "x"}


def _roster(enemy_positions=POSITIONS):
    ally = [_entry(f"C{i}", f"C{i}", "ORDER", p) for i, p in zip(ALLIES, POSITIONS)]
    enemy = [_entry(f"C{i}", f"C{i}", "CHAOS", p) for i, p in zip(ENEMIES, enemy_positions)]
    return ally + enemy


# Les ennemis du milieu (8) et du bas (9) sont permutés dans la draft.
SWAPPED = ["TOP", "JUNGLE", "BOTTOM", "MIDDLE", "UTILITY"]


@pytest.fixture
def check(monkeypatch):
    bus = EventBus()
    draft = DraftState(
        ally_picks=list(ALLIES),
        enemy_picks=list(ENEMIES),
        inferred_roles={**dict(zip(ALLIES, LANES)), **dict(zip(ENEMIES, LANES))},
    )
    loadout = Mock(manual=False)
    loadout.state.return_value = {"champion_id": 4}
    loadout.direct_opponent.return_value = "C9"
    monitor = SimpleNamespace(
        bus=bus,
        last_draft_state=draft,
        has_analyzed_final_draft=True,
        loadout=loadout,
        _get_display_name=lambda champion_id: f"C{champion_id}",
    )
    build = Mock(
        side_effect=lambda *a, **k: FinalAnalysis(
            lines=[], win_probability=0.4, draft_diff=-20.0, evaluation="y"
        )
    )
    monkeypatch.setattr(reality_check, "build_final_analysis", build)
    bus.publish("game", dict(PUBLISHED))
    reality = RealityCheck(monitor)
    reality.monitor, reality.bus, reality.build = monitor, bus, build
    return reality


def _live(check, roster, t):
    check.bus.publish("ingame", {"state": "live", "game_time": t, "roster": roster})
    check.step()


def _stable(check, roster, t0=0.0):
    """Le même relevé à `t0`, puis une fois la durée de stabilité écoulée."""
    _live(check, roster, t0)
    _live(check, roster, t0 + draft_config.REALITY_STABLE_S)


class TestStep:
    def test_swapped_enemy_team_is_detected_and_recomputed(self, check, capsys):
        _stable(check, _roster(SWAPPED))

        lanes = check.build.call_args.args[3]
        assert lanes[8] == "bottom" and lanes[9] == "middle" and lanes[1] == "top"
        payload = check.bus.latest("game")
        assert payload["win_probability"] == 0.4
        assert payload["reality"]["state"] == "corrected"
        assert payload["reality"]["mismatches"] == [
            {"champion": "C8", "predicted": "milieu", "real": "bas"},
            {"champion": "C9", "predicted": "bas", "real": "milieu"},
        ]
        # ma build (champion 4) suit mon vrai poste et le vrai vis-à-vis
        check.monitor.loadout.retarget.assert_called_once_with(4, "bottom", "C9")
        out = capsys.readouterr().out
        assert "[ALERTE] Postes corrigés en partie : C8 milieu -> bas, C9 bas -> milieu" in out
        assert "[INFO] Face-à-face et build recalculés" in out

    def test_predicted_roles_of_the_draft_are_left_untouched(self, check):
        before = dict(check.monitor.last_draft_state.inferred_roles)
        _stable(check, _roster(SWAPPED))
        assert check.monitor.last_draft_state.inferred_roles == before

    def test_waits_for_a_stable_roster(self, check):
        _live(check, _roster(SWAPPED), 0.0)
        _live(check, _roster(SWAPPED), draft_config.REALITY_STABLE_S - 1)
        assert check.build.call_count == 0
        _live(check, _roster(SWAPPED), draft_config.REALITY_STABLE_S)
        assert check.build.call_count == 1

    def test_a_moving_roster_restarts_the_wait(self, check):
        _live(check, _roster(SWAPPED), 0.0)
        _live(check, _roster(), draft_config.REALITY_STABLE_S - 1)  # échange de lanes
        _live(check, _roster(), draft_config.REALITY_STABLE_S)
        assert check.build.call_count == 0
        assert check.bus.latest("game").get("reality") is None

    def test_conform_roster_confirms_without_recomputing(self, check, capsys):
        _stable(check, _roster())
        assert check.build.call_count == 0
        payload = check.bus.latest("game")
        assert payload["win_probability"] == 0.5  # l'analyse de la draft est restée
        assert payload["reality"] == {
            "state": "ok",
            "checked": 10,
            "mismatches": [],
            "at": 10.0,
        }
        assert "[OK] Postes vérifiés en partie : 10/10 conformes" in capsys.readouterr().out

    def test_incomplete_enemy_team_is_not_touched(self, check):
        roster = _roster(["TOP", "JUNGLE", "BOTTOM", "", "UTILITY"])
        _stable(check, roster)
        assert check.build.call_count == 0
        reality = check.bus.latest("game")["reality"]
        assert reality["state"] == "partial" and reality["checked"] == 5

    def test_an_already_handled_roster_is_not_recomputed(self, check):
        _stable(check, _roster(SWAPPED))
        _live(check, _roster(SWAPPED), 30.0)
        _live(check, _roster(SWAPPED), 60.0)
        assert check.build.call_count == 1

    def test_corrections_are_bounded_per_game(self, check, monkeypatch):
        monkeypatch.setattr(draft_config, "REALITY_MAX_CORRECTIONS", 2)
        t = 0.0
        for enemy in (
            SWAPPED,
            ["TOP", "BOTTOM", "MIDDLE", "JUNGLE", "UTILITY"],
            SWAPPED[::-1],
        ):
            _stable(check, _roster(enemy), t)
            t += 100
        assert check.build.call_count == 2

    def test_reset_forgets_the_game(self, check):
        _stable(check, _roster(SWAPPED))
        check.reset()
        _stable(check, _roster(SWAPPED), 100.0)
        assert check.build.call_count == 2

    def test_manual_loadout_page_is_not_replaced(self, check):
        check.monitor.loadout.manual = True
        _stable(check, _roster(SWAPPED))
        assert check.build.call_count == 1
        check.monitor.loadout.retarget.assert_not_called()

    def test_game_changed_during_the_computation_publishes_nothing(self, check):
        def replaced(*args, **kwargs):
            check.monitor.last_draft_state = DraftState()  # reset_for_next_game
            return FinalAnalysis(lines=[], win_probability=0.4, draft_diff=0, evaluation="y")

        check.build.side_effect = replaced
        _stable(check, _roster(SWAPPED))
        assert check.bus.latest("game") == PUBLISHED


class TestStepNeverRaises:
    @pytest.mark.parametrize("missing", ["bus", "analysis", "ingame", "roster", "not_live"])
    def test_missing_inputs_do_nothing(self, check, missing):
        if missing == "bus":
            check.monitor.bus = None
        elif missing == "analysis":
            check.monitor.has_analyzed_final_draft = False
        elif missing == "roster":
            check.bus.publish("ingame", {"state": "live", "game_time": 99.0})
        elif missing == "not_live":
            check.bus.publish("ingame", {"state": "ended", "roster": _roster(SWAPPED)})
        check.step()
        check.step()
        assert check.build.call_count == 0

    def test_a_failing_evaluator_is_reported_once(self, check, capsys):
        check.build.side_effect = RuntimeError("évaluateur absent")
        _stable(check, _roster(SWAPPED))
        _stable(check, _roster(SWAPPED[::-1]), 100.0)
        out = capsys.readouterr().out
        assert out.count("[INFO] Vérification des postes en partie impossible") == 1


def test_recomputes_even_without_a_locked_champion(check):
    """Spectateur ou page OneTricks absente : le face-à-face est corrigé, la build n'est pas touchée."""
    check.monitor.loadout.state.return_value = None
    _stable(check, _roster(SWAPPED))
    assert check.bus.latest("game")["reality"]["state"] == "corrected"
    check.monitor.loadout.retarget.assert_not_called()


class TestAfterACorrection:
    def test_a_roster_back_to_the_prediction_restores_the_original_analysis(self, check):
        _stable(check, _roster(SWAPPED))
        assert check.bus.latest("game")["reality"]["state"] == "corrected"
        _stable(check, _roster(), 100.0)

        payload = check.bus.latest("game")
        assert payload["win_probability"] == 0.5  # l'analyse d'origine, pas la recalculée
        assert payload["reality"]["state"] == "ok"
        assert check.monitor.loadout.retarget.call_count == 2  # la build revient aux postes prédits

    def test_a_partial_roster_keeps_the_corrected_analysis(self, check):
        _stable(check, _roster(SWAPPED))
        _stable(check, _roster(["TOP", "JUNGLE", "BOTTOM", "", "UTILITY"]), 100.0)

        payload = check.bus.latest("game")
        assert payload["win_probability"] == 0.4
        assert payload["reality"]["state"] == "corrected"

    def test_the_original_is_forgotten_with_the_game(self, check):
        _stable(check, _roster(SWAPPED))
        check.reset()
        assert check._original is None


class TestBuildNotRecomputed:
    def test_unavailable_onetricks_page_is_said_not_hidden(self, check, capsys):
        check.monitor.loadout.retarget.return_value = None
        _stable(check, _roster(SWAPPED))

        assert check.bus.latest("game")["reality"]["build"] is False
        out = capsys.readouterr().out
        assert "[INFO] Face-à-face recalculé, build conservée" in out
        assert "build recalculés" not in out

    def test_recomputed_build_is_said(self, check, capsys):
        _stable(check, _roster(SWAPPED))
        assert check.bus.latest("game")["reality"]["build"] is True
        assert "[INFO] Face-à-face et build recalculés" in capsys.readouterr().out
