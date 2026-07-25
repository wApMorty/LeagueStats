"""Display utilities for terminal output with emoji fallback support."""

import sys

# Windows consoles still default to cp1252, which raises UnicodeEncodeError on the
# emojis used throughout the UI. Reconfiguring the stream once replaces the
# 26-entry emoji -> ASCII substitution table this module used to carry: unmappable
# characters degrade to "?" instead of crashing the print.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        # Not a reconfigurable TextIOWrapper (pytest capture, pythonw.exe, pipes)
        pass


def safe_print(text: str) -> None:
    """Print text without ever raising on unencodable characters.

    Args:
        text: Text to print (may contain emojis)
    """
    try:
        print(text)
    except UnicodeEncodeError:
        # Stream could not be reconfigured above -- drop to ASCII rather than crash
        print(text.encode("ascii", "replace").decode("ascii"))
