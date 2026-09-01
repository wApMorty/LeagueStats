"""RSS memory logging for long-running draft monitor sessions.

Extracted from src/draft_monitor.py (SPEC-07 E10, lot 6) : déplacement
verbatim, aucun changement de comportement.
"""

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

# Dedicated logger for memory diagnostics. Writes to logs/draft_monitor_memory.log
# so the RSS trace survives the frequent console clears during a draft session.
_mem_logger = logging.getLogger("leaguestats.draft_monitor.memory")

# Log RSS roughly every 5 minutes (POLL_INTERVAL is 1s by default).
MEMORY_LOG_INTERVAL = 300


def _get_memory_logger() -> logging.Logger:
    """Lazily attach a file handler for the memory diagnostics logger."""
    if not _mem_logger.handlers:
        try:
            log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
            log_dir.mkdir(exist_ok=True)
            handler = logging.FileHandler(log_dir / "draft_monitor_memory.log", encoding="utf-8")
            handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s"))
            _mem_logger.addHandler(handler)
            _mem_logger.setLevel(logging.INFO)
            _mem_logger.propagate = False
        except Exception:
            # Diagnostics must never break the monitor; degrade silently.
            _mem_logger.addHandler(logging.NullHandler())
    return _mem_logger


def log_memory_usage(
    loop_count: int, onetricks_proc: Optional[subprocess.Popen], force: bool = False
) -> None:
    """Record the process RSS to logs/draft_monitor_memory.log periodically.

    This is a lightweight diagnostic to determine whether the monitor's own
    Python process grows over a long session (a leak to bisect) or stays flat
    (pointing at an external cause such as accumulating browser tabs).

    Args:
        loop_count: Current monitor loop iteration count.
        onetricks_proc: The OneTricks browser subprocess, if any.
        force: If True, log immediately regardless of the interval.
    """
    if not force and loop_count % MEMORY_LOG_INTERVAL != 0:
        return
    try:
        import psutil

        rss_mb = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
        _get_memory_logger().info(
            "iteration=%d rss=%.1fMB onetricks_window=%s",
            loop_count,
            rss_mb,
            "open" if onetricks_proc and onetricks_proc.poll() is None else "none",
        )
    except Exception:
        # Diagnostics must never interrupt monitoring.
        pass
