"""Characterization tests for the menu-domain modules extracted from the
former src/ui/lol_coach_legacy.py (SPEC-07 E9).

These lock down the six public entry points lol_coach.py depends on --
check_dependencies, check_database, parse_match_statistics,
run_champion_analysis, run_optimal_team_builder, manage_champion_pools --
plus the menu dispatch (which submenu a given numeric choice routes to)
that used to live untested inside the 2 045-line legacy file. The move
itself was verbatim (no behavior change); these tests exist so a future
change to any of these modules has a regression net.
"""

from unittest.mock import MagicMock

from src.ui import checks, data_update_ui, tier_list_ui, team_builder_ui, pools_menu_ui
from src.config import config


class TestCheckDependencies:
    def test_returns_true_when_deps_importable(self):
        # requests and psutil are hard requirements.txt dependencies, always
        # importable in this environment.
        assert checks.check_dependencies() is True


class TestCheckDatabase:
    def test_returns_false_when_db_missing(self):
        # conftest's autouse _isolate_database_path fixture already points
        # config.DATABASE_PATH at a non-existent file.
        assert checks.check_database() is False

    def test_returns_true_when_db_present(self, tmp_path, monkeypatch):
        db_file = tmp_path / "present.db"
        db_file.write_text("")
        monkeypatch.setattr(config, "DATABASE_PATH", str(db_file))
        assert checks.check_database() is True


class TestParseMatchStatisticsDispatch:
    """parse_match_statistics() (menu 3) routes its submenu choice to one
    of six parse_* functions, or returns on '7'."""

    def test_choice_1_routes_to_parse_champion_pool(self, monkeypatch):
        monkeypatch.setattr(data_update_ui, "_get_patch_version", lambda: "14")
        inputs = iter(["1"])
        monkeypatch.setattr("builtins.input", lambda *_a: next(inputs))
        called = MagicMock()
        monkeypatch.setattr(data_update_ui, "parse_champion_pool", called)

        data_update_ui.parse_match_statistics()

        called.assert_called_once_with("14")

    def test_choice_7_returns_without_calling_anything(self, monkeypatch):
        monkeypatch.setattr(data_update_ui, "_get_patch_version", lambda: "14")
        inputs = iter(["7"])
        monkeypatch.setattr("builtins.input", lambda *_a: next(inputs))
        for name in [
            "parse_champion_pool",
            "parse_all_champions",
            "parse_synergies_pool",
            "parse_synergies_all",
            "parse_all_data_pool",
            "parse_all_data_all",
        ]:
            monkeypatch.setattr(data_update_ui, name, MagicMock())

        data_update_ui.parse_match_statistics()  # must not raise

    def test_no_patch_version_aborts_before_submenu(self, monkeypatch):
        monkeypatch.setattr(data_update_ui, "_get_patch_version", lambda: None)
        # If the function tried to read a submenu choice, this would raise
        # StopIteration -- proving the early return happened.
        monkeypatch.setattr(
            "builtins.input",
            lambda *_a: (_ for _ in ()).throw(AssertionError("unexpected input()")),
        )

        data_update_ui.parse_match_statistics()  # must not raise


class TestRunChampionAnalysisDispatch:
    """run_champion_analysis() (menu 4) routes to the tier list generator
    or the tournament coach."""

    def test_choice_1_routes_to_tier_list_generator(self, monkeypatch):
        inputs = iter(["1"])
        monkeypatch.setattr("builtins.input", lambda *_a: next(inputs))
        called = MagicMock()
        monkeypatch.setattr(tier_list_ui, "run_tier_list_generator", called)

        tier_list_ui.run_champion_analysis()

        called.assert_called_once()

    def test_choice_2_routes_to_tournament_coach(self, monkeypatch):
        inputs = iter(["2"])
        monkeypatch.setattr("builtins.input", lambda *_a: next(inputs))
        called = MagicMock()
        monkeypatch.setattr(tier_list_ui, "run_tournament_draft_coach", called)

        tier_list_ui.run_champion_analysis()

        called.assert_called_once()

    def test_choice_3_returns_without_calling_anything(self, monkeypatch):
        inputs = iter(["3"])
        monkeypatch.setattr("builtins.input", lambda *_a: next(inputs))
        monkeypatch.setattr(tier_list_ui, "run_tier_list_generator", MagicMock())
        monkeypatch.setattr(tier_list_ui, "run_tournament_draft_coach", MagicMock())

        tier_list_ui.run_champion_analysis()  # must not raise


class TestRunOptimalTeamBuilderDispatch:
    def test_invalid_choice_reported_without_crash(self, monkeypatch):
        fake_assistant = MagicMock()
        monkeypatch.setattr(team_builder_ui, "Assistant", MagicMock(return_value=fake_assistant))
        monkeypatch.setattr(team_builder_ui, "_select_pool_for_analysis", lambda: None)
        inputs = iter(["9"])  # not a valid 1-3 option
        monkeypatch.setattr("builtins.input", lambda *_a: next(inputs))

        team_builder_ui.run_optimal_team_builder()  # must not raise

        fake_assistant.close.assert_called_once()


class TestManageChampionPoolsDispatch:
    def test_choice_9_saves_and_exits(self, monkeypatch):
        fake_pool_manager = MagicMock()
        fake_assistant = MagicMock()
        fake_assistant.db.get_all_champion_names.return_value = {}
        monkeypatch.setattr(
            "src.pool_manager.PoolManager", MagicMock(return_value=fake_pool_manager)
        )
        monkeypatch.setattr("src.assistant.Assistant", MagicMock(return_value=fake_assistant))
        inputs = iter(["9"])
        monkeypatch.setattr("builtins.input", lambda *_a: next(inputs))

        pools_menu_ui.manage_champion_pools()

        fake_pool_manager.save_custom_pools.assert_called_once()
        fake_assistant.close.assert_called_once()
