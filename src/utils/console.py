"""Console management utilities for cross-platform terminal control."""

import os
import sys
from typing import Optional, Callable

# Global state for console clearing control (set by main entry point)
_CLEAR_ENABLED = True


def set_clear_enabled(enabled: bool) -> None:
    """
    Configure console clearing globally.

    Args:
        enabled: If False, all clear_console() calls become no-ops

    Example:
        # In main():
        if args.no_clear:
            set_clear_enabled(False)
    """
    global _CLEAR_ENABLED
    _CLEAR_ENABLED = enabled


def is_clear_enabled() -> bool:
    """
    Check if console clearing is currently enabled.

    Returns:
        True if clearing is enabled, False otherwise
    """
    return _CLEAR_ENABLED


def clear_console() -> None:
    """
    Clear the console screen (cross-platform).

    Behavior:
        - Windows: Executes 'cls' command
        - Unix/Linux/macOS: Executes 'clear' command
        - If --no-clear flag is set: No-op (for debugging)

    Note:
        This does NOT interfere with ANSI cursor control
        (e.g., assistant.py's live podium updates).
        It uses os.system() which is a full screen clear,
        while ANSI codes control cursor position.
    """
    if not _CLEAR_ENABLED:
        return  # Respect --no-clear flag

    # Cross-platform detection
    if sys.platform == "win32":
        os.system("cls")
    else:
        os.system("clear")


def clear_and_banner(banner_func: Optional[Callable[[], None]] = None) -> None:
    """
    Clear console and optionally re-display banner.

    Args:
        banner_func: Optional function to call after clearing (e.g., print_banner)

    Example:
        from src.ui.menu_system import print_banner
        clear_and_banner(print_banner)
    """
    clear_console()
    if banner_func:
        banner_func()
