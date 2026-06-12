"""Pipeline notifications: Windows toast + Discord webhook (Horizon 1).

Used by scripts/update_all.py to report nightly update results. Notification
failures are logged but never raised: notifying is best-effort, the pipeline
outcome (exit code + logs) stays the source of truth.

Discord webhook URL comes from the DISCORD_WEBHOOK_URL environment variable
(loaded from .env by the caller). No URL = Discord silently disabled.
"""

import logging
import os
import sys
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Discord embed colors
_COLOR_SUCCESS = 0x2ECC71  # green
_COLOR_FAILURE = 0xE74C3C  # red

_DISCORD_TIMEOUT = 10
_DISCORD_DESCRIPTION_LIMIT = 4000  # API limit is 4096


class Notifier:
    """Best-effort notification dispatcher (Windows toast + Discord webhook)."""

    def __init__(
        self,
        windows_enabled: bool = True,
        discord_webhook_url: Optional[str] = None,
    ):
        """
        Args:
            windows_enabled: Show Windows toast notifications
            discord_webhook_url: Override the DISCORD_WEBHOOK_URL env variable
        """
        self.discord_webhook_url = discord_webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
        self._toaster = None

        if windows_enabled:
            try:
                from windows_toasts import WindowsToaster

                self._toaster = WindowsToaster("LeagueStats Coach")
            except ImportError:
                logger.warning("windows-toasts not available, toast notifications disabled")

    def notify_success(self, title: str, message: str) -> None:
        self._windows_toast(f"{title} ✅", message)
        self._discord(title, message, success=True)

    def notify_failure(self, title: str, message: str) -> None:
        self._windows_toast(f"{title} ❌", message)
        self._discord(title, message, success=False)

    # ── Channels ─────────────────────────────────────────────────────────────

    def _windows_toast(self, title: str, message: str) -> None:
        if self._toaster is None:
            if hasattr(sys, "stdout") and sys.stdout is not None:
                print(f"[NOTIFICATION] {title}: {message}")
            return
        try:
            from windows_toasts import Toast

            toast = Toast()
            toast.text_fields = [title, message]
            self._toaster.show_toast(toast)
        except Exception as e:
            logger.warning("Windows toast failed: %s", e)

    def _discord(self, title: str, message: str, success: bool) -> None:
        if not self.discord_webhook_url:
            return
        try:
            response = requests.post(
                self.discord_webhook_url,
                json={
                    "embeds": [
                        {
                            "title": title,
                            "description": message[:_DISCORD_DESCRIPTION_LIMIT],
                            "color": _COLOR_SUCCESS if success else _COLOR_FAILURE,
                        }
                    ]
                },
                timeout=_DISCORD_TIMEOUT,
            )
            if response.status_code not in (200, 204):
                logger.warning("Discord webhook returned HTTP %d", response.status_code)
        except Exception as e:
            logger.warning("Discord notification failed: %s", e)
