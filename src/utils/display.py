"""Display utilities for terminal output with emoji fallback support."""


def safe_print(text: str) -> None:
    """
    Print text with emoji fallback for Windows terminals that don't support UTF-8.

    Args:
        text: Text to print (may contain emojis)

    Note:
        Falls back to ASCII replacements if UnicodeEncodeError occurs.
    """
    try:
        print(text)
    except UnicodeEncodeError:
        # Fallback: replace emojis with text equivalents
        fallback_text = text
        emoji_map = {
            '✅': 'OK', '❌': 'ERROR', '⚠️': 'WARNING', '🎯': 'TARGET',
            '📊': 'STATS', '🔸': '-', '🟢': 'GREEN', '🟡': 'YELLOW',
            '🟠': 'ORANGE', '🔴': 'RED', '💡': 'TIPS', '📈': 'TREND',
            '🛡️': 'SHIELD', '🥇': '1st', '🥈': '2nd', '🥉': '3rd',
            '🎮': 'GAME', '➖': '-', '─': '-', '═': '=', '•': '*', '→': '>',
            '⚔️': '[SWORD]', '💥': '[BOOM]', '≥': '>=', '⭐': '*'
        }
        for emoji, replacement in emoji_map.items():
            fallback_text = fallback_text.replace(emoji, replacement)
        print(fallback_text)
