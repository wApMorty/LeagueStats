"""Tests for scripts/update_all.py and src/notifications.py (Horizon 1)."""

import sys
from unittest.mock import MagicMock, patch

import pytest

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


class TestUpdateAllMain:
    """scripts/update_all.py is now a thin CLI wrapper around
    src.pipeline.run_pipeline() (SPEC-01 A2) — these tests only check that
    CLI args are forwarded correctly and the exit code reflects the result.
    Pipeline behavior itself is covered by tests/test_pipeline.py.
    """

    def _run(self, module, monkeypatch, result_status="ok", argv=None):
        from src.pipeline import PipelineResult

        if argv is not None:
            monkeypatch.setattr(sys, "argv", argv)

        mock_run_pipeline = MagicMock(return_value=PipelineResult(status=result_status))
        monkeypatch.setattr(module, "run_pipeline", mock_run_pipeline)
        monkeypatch.setattr(module, "_set_process_priority", MagicMock())
        monkeypatch.setattr(module, "_setup_logging", MagicMock())

        exit_code = module.main()
        return exit_code, mock_run_pipeline

    def test_successful_run_returns_zero(self, update_all_module, monkeypatch):
        exit_code, mock_run_pipeline = self._run(update_all_module, monkeypatch)

        assert exit_code == 0
        mock_run_pipeline.assert_called_once()

    def test_failed_run_returns_one(self, update_all_module, monkeypatch):
        exit_code, _ = self._run(update_all_module, monkeypatch, result_status="failed")

        assert exit_code == 1

    def test_recompute_only_flag_forwarded(self, update_all_module, monkeypatch):
        exit_code, mock_run_pipeline = self._run(
            update_all_module, monkeypatch, argv=["update_all.py", "--recompute-only"]
        )

        assert exit_code == 0
        assert mock_run_pipeline.call_args.kwargs["recompute_only"] is True

    def test_skip_synergies_flag_forwarded_as_include_synergies_false(
        self, update_all_module, monkeypatch
    ):
        _exit_code, mock_run_pipeline = self._run(
            update_all_module, monkeypatch, argv=["update_all.py", "--skip-synergies"]
        )

        assert mock_run_pipeline.call_args.kwargs["include_synergies"] is False

    def test_skip_completeness_flag_forwarded(self, update_all_module, monkeypatch):
        _exit_code, mock_run_pipeline = self._run(
            update_all_module, monkeypatch, argv=["update_all.py", "--skip-completeness"]
        )

        assert mock_run_pipeline.call_args.kwargs["skip_completeness"] is True

    def test_patch_and_workers_forwarded(self, update_all_module, monkeypatch):
        _exit_code, mock_run_pipeline = self._run(
            update_all_module,
            monkeypatch,
            argv=["update_all.py", "--patch", "15.1", "--workers", "4"],
        )

        assert mock_run_pipeline.call_args.kwargs["patch"] == "15.1"
        assert mock_run_pipeline.call_args.kwargs["workers"] == 4
