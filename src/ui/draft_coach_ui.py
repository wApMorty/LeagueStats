"""UI for real-time draft coach (League Client integration)."""

from typing import Optional
from ..draft_monitor import DraftMonitor


def run_draft_coach(
    verbose: bool = False,
    auto_hover: bool = False,
    auto_accept_queue: bool = False,
    auto_ban_hover: bool = False,
    open_onetricks: Optional[bool] = None
) -> None:
    """
    Run the real-time draft coach.

    Args:
        verbose: Enable verbose logging
        auto_hover: Auto-hover recommended champions
        auto_accept_queue: Auto-accept queue
        auto_ban_hover: Auto-hover ban recommendations
        open_onetricks: Open champion pages on draft completion
    """
    print("[INFO] Starting Real-time Draft Coach...")
    print("Make sure League of Legends client is running and start a game!")
    if auto_hover:
        print("🎯 [AUTO-HOVER] Champion auto-hover is ENABLED")
    if auto_accept_queue:
        print("🔥 [AUTO-ACCEPT] Queue auto-accept is ENABLED")
    if auto_ban_hover:
        print("🚫 [AUTO-BAN-HOVER] Ban hover is ENABLED")
    if open_onetricks:
        print("🌐 [ONETRICKS] Open champion page on draft completion is ENABLED")
    print("Press Ctrl+C to stop monitoring.\n")

    try:
        monitor = DraftMonitor(
            verbose=verbose,
            auto_select_pool=False,
            auto_hover=auto_hover,
            auto_accept_queue=auto_accept_queue,
            auto_ban_hover=auto_ban_hover,
            open_onetricks=open_onetricks
        )
        monitor.start_monitoring()
    except KeyboardInterrupt:
        print("\n[INFO] Draft Coach stopped by user")
    except Exception as e:
        print(f"[ERROR] Draft coach error: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
