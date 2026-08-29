"""Tests for src/pipeline.py — the single pipeline shared by
scripts/update_all.py and the in-app menu (src/ui/lol_coach_legacy.py),
SPEC-01 A2."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import scripts.repair_data as repair_data_module
from src.data_quality import CompletenessReport, DataCompletenessError


def _scrape_stats():
    return {
        "lane_map": {"Aatrox": ["top"]},
        "discovery_failures": [],
        "pages_total": 2,
        "matchups": {"top": {"success": 1, "failed": 0, "total": 1}},
        "synergies": {"top": {"success": 1, "failed": 0, "total": 1}},
        "success": 2,
        "failed": 0,
        "total": 2,
    }


class TestRunPipeline:
    def _run(
        self,
        monkeypatch,
        scores_side_effect=None,
        completeness_side_effect=None,
        completeness_return_value=None,
        repair_results=None,
        **kwargs,
    ):
        """Run run_pipeline() with every external dependency mocked."""
        import src.pipeline as module

        mocks = {}

        db = MagicMock()
        db.connection.cursor.return_value.fetchone.return_value = [25000]
        mocks["db"] = db
        monkeypatch.setattr(module, "Database", MagicMock(return_value=db))

        mocks["parser"] = MagicMock()
        monkeypatch.setattr(module, "ParallelParser", MagicMock(return_value=mocks["parser"]))

        mocks["scrape"] = MagicMock(return_value=_scrape_stats())
        monkeypatch.setattr(module, "scrape_all_multilane", mocks["scrape"])

        if completeness_return_value is None:
            # Default: a clean report (SPEC-01 A4 grading not triggered).
            completeness_return_value = MagicMock(
                warnings=[],
                incomplete_matchup_champions=[],
                incomplete_synergy_champions=[],
            )
        mocks["completeness"] = MagicMock(
            side_effect=completeness_side_effect, return_value=completeness_return_value
        )
        monkeypatch.setattr(module, "assert_completeness", mocks["completeness"])

        mocks["repair"] = MagicMock(return_value=repair_results or {})
        monkeypatch.setattr(module, "_repair_incomplete_champions", mocks["repair"])

        mocks["notifier"] = MagicMock()
        monkeypatch.setattr(module, "Notifier", MagicMock(return_value=mocks["notifier"]))

        mocks["backup_database"] = MagicMock(
            return_value=Path("data/db.backup-20260101T000000Z.db")
        )
        monkeypatch.setattr(module, "backup_database", mocks["backup_database"])
        mocks["restore_database"] = MagicMock()
        monkeypatch.setattr(module, "restore_database", mocks["restore_database"])
        mocks["purge_old_backups"] = MagicMock()
        monkeypatch.setattr(module, "purge_old_backups", mocks["purge_old_backups"])

        assistant = MagicMock()
        if scores_side_effect is not None:
            assistant.calculate_global_scores.side_effect = scores_side_effect
        else:
            assistant.calculate_global_scores.return_value = 172
        assistant.precalculate_all_custom_pool_bans.return_value = {"pool1": 10}
        mocks["assistant"] = assistant

        with patch.dict(
            sys.modules,
            {"src.assistant": MagicMock(Assistant=MagicMock(return_value=assistant))},
        ):
            result = module.run_pipeline(**kwargs)

        return result, mocks

    def test_successful_run_writes_meta_and_notifies(self, monkeypatch):
        result, mocks = self._run(monkeypatch)

        assert result.status == "ok"
        assert result.scores_count == 172
        mocks["scrape"].assert_called_once()
        mocks["completeness"].assert_called_once()
        mocks["assistant"].calculate_global_scores.assert_called_once()
        mocks["assistant"].precalculate_all_custom_pool_bans.assert_called_once()

        meta_keys = [call.args[0] for call in mocks["db"].set_meta.call_args_list]
        assert "last_update_utc" in meta_keys
        assert "last_scrape_utc" in meta_keys
        assert "matchups_count" in meta_keys
        meta_calls = {call.args[0]: call.args[1] for call in mocks["db"].set_meta.call_args_list}
        assert meta_calls["last_scrape_status"] == "ok"
        assert "last_full_success_utc" in meta_keys
        mocks["notifier"].notify_success.assert_called_once()
        mocks["repair"].assert_not_called()

        # SPEC-01 A5: a backup is taken before the scrape (DROP happens
        # inside scrape_all_multilane) and kept + pruned on a clean run.
        mocks["backup_database"].assert_called_once()
        mocks["purge_old_backups"].assert_called_once()
        mocks["restore_database"].assert_not_called()

    def test_completeness_failure_still_writes_scrape_meta(self, monkeypatch):
        """SPEC-01 A3: a blocked completeness gate must not erase the trace
        that a scrape happened — last_scrape_utc/status are written even on
        failure, only last_full_success_utc is withheld."""
        result, mocks = self._run(
            monkeypatch,
            completeness_side_effect=DataCompletenessError("matchups total 16179 < 20000"),
        )

        assert result.status == "failed"
        meta_keys = [call.args[0] for call in mocks["db"].set_meta.call_args_list]
        assert "last_scrape_utc" in meta_keys
        assert "matchups_count" in meta_keys
        meta_calls = {call.args[0]: call.args[1] for call in mocks["db"].set_meta.call_args_list}
        assert meta_calls["last_scrape_status"] == "failed"
        assert "last_full_success_utc" not in meta_keys
        mocks["notifier"].notify_failure.assert_called_once()
        assert "runbook" in mocks["notifier"].notify_failure.call_args.args[1]

        # SPEC-01 A5: blocking completeness failures restore the pre-scrape
        # backup instead of leaving the volumetric-collapse data in place.
        mocks["restore_database"].assert_called_once()
        mocks["purge_old_backups"].assert_not_called()
        assert "restaurée" in mocks["notifier"].notify_failure.call_args.args[1]

    def test_warnings_only_report_triggers_partial_status_and_repair(self, monkeypatch):
        """SPEC-01 A4: a handful of incomplete champions (report.warnings, not
        blocking_failures) must not fail the run — it recomputes scores/bans,
        attempts a targeted repair, and reports status="partial"."""
        completeness_report = MagicMock(
            warnings=["1 champion(s) below 50 synergies: Aphelios=0"],
            incomplete_matchup_champions=[],
            incomplete_synergy_champions=["Aphelios"],
        )
        completeness_report.summary.return_value = (
            "Completeness check PARTIAL: 172 champions, 25000 matchups, 20000 synergies\n"
            "  - [warning] 1 champion(s) below 50 synergies: Aphelios=0"
        )
        result, mocks = self._run(
            monkeypatch,
            completeness_return_value=completeness_report,
            repair_results={"synergies": {"success": 1, "failed": 0, "total": 1, "duration": 1.2}},
        )

        assert result.status == "partial"
        assert result.completeness_warnings == completeness_report.warnings
        mocks["repair"].assert_called_once()
        assert mocks["repair"].call_args.args[0] is mocks["db"]
        assert mocks["repair"].call_args.args[1] is completeness_report

        meta_calls = {call.args[0]: call.args[1] for call in mocks["db"].set_meta.call_args_list}
        meta_keys = [call.args[0] for call in mocks["db"].set_meta.call_args_list]
        assert meta_calls["last_scrape_status"] == "partial"
        assert "last_full_success_utc" not in meta_keys
        mocks["notifier"].notify_success.assert_called_once()

    def test_scrape_crash_returns_failed_with_notification(self, monkeypatch):
        import src.pipeline as module

        db = MagicMock()
        monkeypatch.setattr(module, "Database", MagicMock(return_value=db))
        monkeypatch.setattr(
            module, "ParallelParser", MagicMock(side_effect=RuntimeError("geckodriver missing"))
        )
        notifier = MagicMock()
        monkeypatch.setattr(module, "Notifier", MagicMock(return_value=notifier))
        backup_path = Path("data/db.backup-20260101T000000Z.db")
        monkeypatch.setattr(module, "backup_database", MagicMock(return_value=backup_path))
        restore_mock = MagicMock()
        monkeypatch.setattr(module, "restore_database", restore_mock)

        result = module.run_pipeline()

        assert result.status == "failed"
        notifier.notify_failure.assert_called_once()
        # SPEC-01 A5: the tables are DROPped before ParallelParser is even
        # created, so a crash here must restore the pre-scrape backup.
        restore_mock.assert_called_once_with(backup_path, module.config.DATABASE_PATH)

    def test_keyboard_interrupt_restores_backup_without_raising(self, monkeypatch):
        """SPEC-01 A5: a Ctrl+C mid-scrape must not propagate (callers only
        check result.status) and must restore the pre-scrape backup, same as
        any other crash in that window."""
        import src.pipeline as module

        db = MagicMock()
        monkeypatch.setattr(module, "Database", MagicMock(return_value=db))
        monkeypatch.setattr(module, "ParallelParser", MagicMock(side_effect=KeyboardInterrupt))
        notifier = MagicMock()
        monkeypatch.setattr(module, "Notifier", MagicMock(return_value=notifier))
        backup_path = Path("data/db.backup-20260101T000000Z.db")
        monkeypatch.setattr(module, "backup_database", MagicMock(return_value=backup_path))
        restore_mock = MagicMock()
        monkeypatch.setattr(module, "restore_database", restore_mock)

        result = module.run_pipeline()

        assert result.status == "failed"
        restore_mock.assert_called_once_with(backup_path, module.config.DATABASE_PATH)
        notifier.notify_failure.assert_called_once()

    def test_recompute_only_skips_scrape_and_completeness(self, monkeypatch):
        result, mocks = self._run(monkeypatch, recompute_only=True)

        assert result.status == "ok"
        mocks["scrape"].assert_not_called()
        mocks["completeness"].assert_not_called()
        mocks["assistant"].calculate_global_scores.assert_called_once()
        mocks["assistant"].precalculate_all_custom_pool_bans.assert_called_once()

        meta_keys = [call.args[0] for call in mocks["db"].set_meta.call_args_list]
        assert "last_recompute_utc" in meta_keys
        assert "last_update_utc" not in meta_keys
        assert "last_scrape_utc" not in meta_keys
        assert "last_scrape_status" not in meta_keys
        assert "last_full_success_utc" not in meta_keys
        mocks["notifier"].notify_success.assert_called_once()

    def test_pool_scoped_run_skips_whole_roster_completeness_check(self, monkeypatch):
        result, mocks = self._run(monkeypatch, champions=["Ahri", "Zed"])

        assert result.status == "ok"
        mocks["scrape"].assert_called_once()
        mocks["completeness"].assert_not_called()
        assert mocks["scrape"].call_args.kwargs["champions"] == ["Ahri", "Zed"]

    def test_skip_completeness_flag_skips_check(self, monkeypatch):
        result, mocks = self._run(monkeypatch, skip_completeness=True)

        assert result.status == "ok"
        mocks["completeness"].assert_not_called()

    def test_include_matchups_and_synergies_forwarded_to_scrape(self, monkeypatch):
        _result, mocks = self._run(monkeypatch, include_matchups=False, include_synergies=True)

        call_kwargs = mocks["scrape"].call_args.kwargs
        assert call_kwargs["include_matchups"] is False
        assert call_kwargs["include_synergies"] is True

    def test_score_recalculation_failure_is_not_silent_success(self, monkeypatch):
        """Regression (2026-08-25 incident): calculate_global_scores() raised
        AttributeError, champion_scores stayed empty, and the run reported
        success anyway because nothing checked its outcome. The pipeline must
        surface this as a failed status, not a silent success."""
        result, mocks = self._run(
            monkeypatch, recompute_only=True, scores_side_effect=AttributeError("boom")
        )

        assert result.status == "failed"
        mocks["db"].set_meta.assert_not_called()
        mocks["notifier"].notify_failure.assert_called_once()
        # SPEC-01 A5: recompute-only never DROPs matchups/synergies, so there
        # is nothing to back up.
        mocks["backup_database"].assert_not_called()

    def test_scoring_failure_after_scrape_marks_scrape_status_failed(self, monkeypatch):
        """When the scrape itself succeeded but a later step (scoring)
        crashes, last_scrape_utc must already be recorded (written right
        after the scrape) and last_scrape_status must flip to 'failed' —
        but last_full_success_utc must never appear."""
        result, mocks = self._run(monkeypatch, scores_side_effect=AttributeError("boom"))

        assert result.status == "failed"
        meta_keys = [call.args[0] for call in mocks["db"].set_meta.call_args_list]
        assert "last_scrape_utc" in meta_keys
        assert "last_full_success_utc" not in meta_keys
        meta_calls = {call.args[0]: call.args[1] for call in mocks["db"].set_meta.call_args_list}
        assert meta_calls["last_scrape_status"] == "failed"
        # SPEC-01 A5: the scrape already DROPped+repopulated the tables by
        # this point, so a downstream crash still needs a restore.
        mocks["restore_database"].assert_called_once()


class TestRepairIncompleteChampions:
    """SPEC-01 A4: _repair_incomplete_champions() reuses scripts/repair_data.py's
    MATCHUPS/SYNERGIES targets for a targeted re-scrape, without ever raising."""

    def test_no_incomplete_champions_skips_repair(self, monkeypatch):
        import src.pipeline as module

        report = CompletenessReport(champions_total=173)
        repair_mock = MagicMock()
        monkeypatch.setattr(repair_data_module, "repair_parallel", repair_mock)
        monkeypatch.setattr(module, "discover_lanes_for_champions", MagicMock())

        result = module._repair_incomplete_champions(MagicMock(), report, "14", None)

        assert result == {}
        repair_mock.assert_not_called()

    def test_repairs_matchups_and_synergies_separately(self, monkeypatch):
        import src.pipeline as module

        report = CompletenessReport(
            champions_total=173,
            champions_without_matchups=["Aphelios"],
            synergies_below_threshold=[("Zed", 10)],
        )
        discover_mock = MagicMock(
            side_effect=lambda champions, patch, normalize_func: {
                champ: ["bottom"] for champ in champions
            }
        )
        monkeypatch.setattr(module, "discover_lanes_for_champions", discover_mock)
        repair_mock = MagicMock(
            return_value={"success": 1, "failed": 0, "total": 1, "duration": 1.0}
        )
        monkeypatch.setattr(repair_data_module, "repair_parallel", repair_mock)

        result = module._repair_incomplete_champions(MagicMock(), report, "14", 3)

        assert set(result.keys()) == {"matchups", "synergies"}
        assert repair_mock.call_count == 2
        called_targets = {call.args[0].name for call in repair_mock.call_args_list}
        assert called_targets == {"matchups", "synergies"}
        # patch and max_workers must reach repair_parallel unchanged
        for call in repair_mock.call_args_list:
            assert call.args[3] == "14"
            assert call.args[4] == 3

    def test_repair_failure_is_caught_and_reported(self, monkeypatch):
        """A crash mid-repair (e.g. geckodriver missing) must not escalate —
        the pipeline stays 'partial', it never becomes 'failed' over this."""
        import src.pipeline as module

        report = CompletenessReport(champions_total=173, champions_without_matchups=["Aphelios"])
        monkeypatch.setattr(
            module,
            "discover_lanes_for_champions",
            MagicMock(return_value={"Aphelios": ["bottom"]}),
        )
        monkeypatch.setattr(
            repair_data_module,
            "repair_parallel",
            MagicMock(side_effect=RuntimeError("geckodriver missing")),
        )

        result = module._repair_incomplete_champions(MagicMock(), report, "14", None)

        assert "error" in result["matchups"]
        assert "geckodriver missing" in result["matchups"]["error"]
