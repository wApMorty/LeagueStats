"""Tests for scripts/update_all.py and src/notifications.py (Horizon 1)."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from src.data_quality import DataCompletenessError
from src.notifications import Notifier


class TestNotifier:
    def test_discord_disabled_without_url(self, monkeypatch):
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        notifier = Notifier(windows_enabled=False)

        with patch("src.notifications.requests.post") as mock_post:
            notifier.notify_success("title", "message")
        mock_post.assert_not_called()

    def test_discord_success_embed(self, monkeypatch):
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/webhook")
        notifier = Notifier(windows_enabled=False)

        with patch("src.notifications.requests.post") as mock_post:
            mock_post.return_value.status_code = 204
            notifier.notify_success("Mise à jour", "172/172 OK")

        payload = mock_post.call_args.kwargs["json"]
        embed = payload["embeds"][0]
        assert embed["title"] == "Mise à jour"
        assert embed["color"] == 0x2ECC71

    def test_discord_failure_embed_color(self, monkeypatch):
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/webhook")
        notifier = Notifier(windows_enabled=False)

        with patch("src.notifications.requests.post") as mock_post:
            mock_post.return_value.status_code = 204
            notifier.notify_failure("Échec", "boom")

        assert mock_post.call_args.kwargs["json"]["embeds"][0]["color"] == 0xE74C3C

    def test_discord_exception_never_raises(self, monkeypatch):
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/webhook")
        notifier = Notifier(windows_enabled=False)

        with patch("src.notifications.requests.post", side_effect=ConnectionError("down")):
            notifier.notify_failure("Échec", "boom")  # must not raise


@pytest.fixture
def update_all_module(monkeypatch):
    """Import scripts.update_all fresh with a harmless argv."""
    monkeypatch.setattr(sys, "argv", ["update_all.py"])
    import scripts.update_all as module

    return module


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


class TestUpdateAllMain:
    def _run(self, module, monkeypatch, completeness_side_effect=None):
        """Run main() with every external dependency mocked; return mocks + exit code."""
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
        assistant.calculate_global_scores.return_value = 172
        assistant.precalculate_all_custom_pool_bans.return_value = {"pool1": 10}
        mocks["assistant"] = assistant

        with patch.dict(
            sys.modules,
            {
                "src.assistant": MagicMock(Assistant=MagicMock(return_value=assistant)),
                "src.sqlite_data_source": MagicMock(),
            },
        ):
            exit_code = module.main()

        return exit_code, mocks

    def test_successful_run_returns_zero_and_writes_meta(self, update_all_module, monkeypatch):
        exit_code, mocks = self._run(update_all_module, monkeypatch)

        assert exit_code == 0
        mocks["scrape"].assert_called_once()
        mocks["completeness"].assert_called_once()
        mocks["assistant"].calculate_global_scores.assert_called_once()
        mocks["assistant"].precalculate_all_custom_pool_bans.assert_called_once()

        meta_keys = [call.args[0] for call in mocks["db"].set_meta.call_args_list]
        assert "last_update_utc" in meta_keys
        assert "matchups_count" in meta_keys
        mocks["notifier"].notify_success.assert_called_once()

    def test_completeness_failure_returns_one_no_meta(self, update_all_module, monkeypatch):
        exit_code, mocks = self._run(
            update_all_module,
            monkeypatch,
            completeness_side_effect=DataCompletenessError("matchups total 16179 < 20000"),
        )

        assert exit_code == 1
        # Freshness must NOT advance on a failed run
        mocks["db"].set_meta.assert_not_called()
        mocks["assistant"].calculate_global_scores.assert_not_called()
        mocks["notifier"].notify_failure.assert_called_once()
        failure_message = mocks["notifier"].notify_failure.call_args.args[1]
        assert "runbook" in failure_message

    def test_scrape_crash_returns_one_with_notification(self, update_all_module, monkeypatch):
        mocks_db = MagicMock()
        monkeypatch.setattr(update_all_module, "Database", MagicMock(return_value=mocks_db))
        monkeypatch.setattr(
            update_all_module,
            "ParallelParser",
            MagicMock(side_effect=RuntimeError("geckodriver missing")),
        )
        notifier = MagicMock()
        monkeypatch.setattr(update_all_module, "Notifier", MagicMock(return_value=notifier))

        assert update_all_module.main() == 1
        notifier.notify_failure.assert_called_once()
