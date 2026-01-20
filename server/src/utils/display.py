"""Display utilities for safe console output."""


def safe_print(text: str) -> None:
    """
    Print text safely, handling encoding errors for special characters.

    Args:
        text: Text to print (may contain emojis or unicode characters)
    """
    try:
        print(text)
    except UnicodeEncodeError:
        # Fallback: Replace emojis and special chars with safe alternatives
        safe_text = text.encode("ascii", errors="replace").decode("ascii")
        print(safe_text)
