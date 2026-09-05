"""Champion name normalization for URLs and external sites.

Extracted from src/constants.py (dette de code, TODO.md P4) : déplacement
verbatim, aucun changement de comportement. Séparé des listes de champions
(données statiques) qui composent l'essentiel de constants.py — une
distinction données/comportement plutôt qu'un découpage par domaine.
Réexporté par constants.py pour ne casser aucun import existant.
"""


def normalize_champion_name_for_url(champion_name: str) -> str:
    """
    Normalize champion names for use in LoLalytics URLs.

    LoLalytics uses lowercase champion names with specific formatting:
    - Remove spaces and special characters
    - Convert to lowercase
    - Handle special cases like Roman numerals
    """
    # Handle special cases first
    special_cases = {
        "JarvanIV": "jarvaniv",
        "AurelionSol": "aurelionsol",
        "DrMundo": "drmundo",
        "Khazix": "khazix",
        "LeeSin": "leesin",
        "Kaisa": "kaisa",
        "MissFortune": "missfortune",
        "TwistedFate": "twistedfate",
        "XinZhao": "xinzhao",
        "Chogath": "chogath",
        "KogMaw": "kogmaw",
        "RekSai": "reksai",
        "TahmKench": "tahmkench",
        "Velkoz": "velkoz",
        "Belveth": "belveth",
        "KSante": "ksante",
        "MasterYi": "masteryi",
        "MonkeyKing": "wukong",
    }

    # Check if it's a special case
    if champion_name in special_cases:
        return special_cases[champion_name]

    # Default normalization: lowercase, remove spaces and special chars
    normalized = champion_name.lower()
    # Remove apostrophes and spaces
    normalized = normalized.replace("'", "").replace(" ", "")

    return normalized


def denormalize_champion_name_from_url(url_name: str) -> str:
    """
    Convert a normalized champion name from URL back to the display name.

    This is the reverse mapping of normalize_champion_name_for_url.
    Used when parsing champion names from LoLalytics URLs.
    """
    # Reverse mapping from URL names to display names
    url_to_display = {
        "jarvaniv": "JarvanIV",
        "aurelionsol": "AurelionSol",
        "drmundo": "DrMundo",
        "khazix": "Khazix",
        "leesin": "LeeSin",
        "kaisa": "Kaisa",
        "missfortune": "MissFortune",
        "twistedfate": "TwistedFate",
        "xinzhao": "XinZhao",
        "chogath": "Chogath",
        "kogmaw": "KogMaw",
        "reksai": "RekSai",
        "tahmkench": "TahmKench",
        "velkoz": "Velkoz",
        "belveth": "Belveth",
        "ksante": "KSante",
        "masteryi": "MasterYi",
        "wukong": "MonkeyKing",
    }

    # Check if it's a special case that needs conversion
    if url_name.lower() in url_to_display:
        return url_to_display[url_name.lower()]

    # For regular champions, capitalize first letter
    return url_name.capitalize()


def normalize_champion_name_for_onetricks(champion_name: str) -> str:
    """
    Normalize champion names for use in Onetricks.gg URLs.

    Onericks.gg uses proper case champion names in URLs like:
    /champions/ranking/ChampionName
    """
    # Handle special cases for OneTriks.gg
    special_cases = {
        "JarvanIV": "JarvanIV",
        "Jarvan IV": "JarvanIV",
        "AurelionSol": "AurelionSol",
        "Aurelion Sol": "AurelionSol",
        "DrMundo": "DrMundo",
        "Dr. Mundo": "DrMundo",
        "Khazix": "Khazix",
        "Kha'Zix": "Khazix",
        "LeeSin": "LeeSin",
        "Lee Sin": "LeeSin",
        "Kaisa": "Kaisa",
        "Kai'Sa": "Kaisa",
        "MissFortune": "MissFortune",
        "Miss Fortune": "MissFortune",
        "TwistedFate": "TwistedFate",
        "Twisted Fate": "TwistedFate",
        "XinZhao": "XinZhao",
        "Xin Zhao": "XinZhao",
        "Chogath": "Chogath",
        "Cho'Gath": "Chogath",
        "KogMaw": "KogMaw",
        "Kog'Maw": "KogMaw",
        "RekSai": "RekSai",
        "Rek'Sai": "RekSai",
        "TahmKench": "TahmKench",
        "Tahm Kench": "TahmKench",
        "Velkoz": "Velkoz",
        "Vel'Koz": "Velkoz",
        "Belveth": "Belveth",
        "Bel'Veth": "Belveth",
        "KSante": "KSante",
        "K'Sante": "KSante",
        "MasterYi": "MasterYi",
        "Master Yi": "MasterYi",
        "MonkeyKing": "Wukong",
        "Wukong": "Wukong",
    }

    # Check if it's a special case
    if champion_name in special_cases:
        return special_cases[champion_name]

    # Default: remove spaces and apostrophes, keep proper case
    normalized = champion_name.replace(" ", "").replace("'", "")
    return normalized
