"""Tests for src/pipeline.py — the single pipeline shared by
scripts/update_all.py and the in-app menu (src/ui/lol_coach_legacy.py),
SPEC-01 A2."""

import sys
from unittest.mock import MagicMock, patch

from src.data_quality import DataCompletenessError


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
    def _run(self, monkeypatch, scores_side_effect=None, completeness_side_effect=None, **kwargs):
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

        mocks["completeness"] = MagicMock(side_effect=completeness_side_effect)
        monkeypatch.setattr(module, "assert_completeness", mocks["completeness"])

        mocks["notifier"] = MagicMock()
        monkeypatch.setattr(module, "Notifier", MagicMock(return_value=mocks["notifier"]))

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
        assert "matchups_count" in meta_keys
        mocks["notifier"].notify_success.assert_called_once()

    def test_completeness_failure_returns_failed_no_meta(self, monkeypatch):
        result, mocks = self._run(
            monkeypatch,
            completeness_side_effect=DataCompletenessError("matchups total 16179 < 20000"),
        )

        assert result.status == "failed"
        mocks["db"].set_meta.assert_not_called()
        mocks["notifier"].notify_failure.assert_called_once()
        assert "runbook" in mocks["notifier"].notify_failure.call_args.args[1]

    def test_scrape_crash_returns_failed_with_notification(self, monkeypatch):
        import src.pipeline as module

        db = MagicMock()
        monkeypatch.setattr(module, "Database", MagicMock(return_value=db))
        monkeypatch.setattr(
            module, "ParallelParser", MagicMock(side_effect=RuntimeError("geckodriver missing"))
        )
        notifier = MagicMock()
        monkeypatch.setattr(module, "Notifier", MagicMock(return_value=notifier))

        result = module.run_pipeline()

        assert result.status == "failed"
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
