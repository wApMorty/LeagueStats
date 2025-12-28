import numpy as np

CHAMPIONS_LIST = np.unique(
    [
        "Leona",
        "Hecarim",
        "KaiSa",
        "Camille",
        "Akshan",
        "Talon",
        "Rengar",
        "Fiora",
        "Draven",
        "Pyke",
        "Cassiopeia",
        "Udyr",
        "Jinx",
        "Rell",
        "AurelionSol",
        "Seraphine",
        "Lillia",
        "Janna",
        "Jhin",
        "Kindred",
        "Sylas",
        "Zed",
        "Thresh",
        "Ivern",
        "Vayne",
        "Lulu",
        "Taliyah",
        "Viego",
        "KhaZix",
        "Zeri",
        "Nami",
        "Sett",
        "Hwei",
        "Tryndamere",
        "Shaco",
        "Taric",
        "Yasuo",
        "Evelynn",
        "Anivia",
        "Poppy",
        "Ezreal",
        "Gwen",
        "Urgot",
        "Twitch",
        "Yone",
        "Leblanc",
        "BelVeth",
        "Nunu",
        "Ashe",
        "Braum",
        "Sona",
        "KogMaw",
        "Ahri",
        "Darius",
        "RekSai",
        "Aurora",
        "MasterYi",
        "Fiddlesticks",
        "Karma",
        "Aatrox",
        "Kalista",
        "Zilean",
        "Kled",
        "Nilah",
        "TwistedFate",
        "Rammus",
        "Quinn",
        "Zac",
        "Lucian",
        "MissFortune",
        "Jax",
        "Kayn",
        "Qiyana",
        "Milio",
        "Soraka",
        "Irelia",
        "LeeSin",
        "Alistar",
        "Caitlyn",
        "Katarina",
        "Brand",
        "Akali",
        "Riven",
        "Shyvana",
        "Samira",
        "Renata",
        "Amumu",
        "Bard",
        "Skarner",
        "Lissandra",
        "Neeko",
        "Kayle",
        "Nocturne",
        "Kennen",
        "Aphelios",
        "Volibear",
        "Rakan",
        "Galio",
        "Garen",
        "JarvanIV",
        "Shen",
        "Syndra",
        "Sivir",
        "Maokai",
        "Ornn",
        "XinZhao",
        "DrMundo",
        "Swain",
        "Blitzcrank",
        "Xayah",
        "Pantheon",
        "Varus",
        "Nidalee",
        "Xerath",
        "Smolder",
        "Kassadin",
        "Warwick",
        "Karthus",
        "Vex",
        "Olaf",
        "Graves",
        "Nautilus",
        "Rumble",
        "Ekko",
        "Senna",
        "Elise",
        "Gragas",
        "Fizz",
        "Briar",
        "Teemo",
        "Jayce",
        "Naafiri",
        "Vi",
        "Vladimir",
        "Mordekaiser",
        "Gnar",
        "Yuumi",
        "Annie",
        "Trundle",
        "Illaoi",
        "ChoGath",
        "Malzahar",
        "Zyra",
        "KSante",
        "Nasus",
        "Lux",
        "Morgana",
        "Heimerdinger",
        "Sejuani",
        "Singed",
        "Ziggs",
        "Orianna",
        "TahmKench",
        "Gangplank",
        "Zoe",
        "Viktor",
        "Malphite",
        "Renekton",
        "Azir",
        "Corki",
        "Yorick",
        "MonkeyKing",
        "VelKoz",
        "Tristana",
        "Ryze",
        "Veigar",
        "Sion",
        "Diana",
        "Ambessa",
        "Mel",
        "Yunara",
        "Zaahen",
    ]
)

TOP_CHAMPIONS = [
    "Aatrox",
    "Ambessa",
    "Camille",
    "ChoGath",
    "Darius",
    "DrMundo",
    "Fiora",
    "Galio",
    "Gangplank",
    "Garen",
    "Gnar",
    "Gragas",
    "Gwen",
    "Illaoi",
    "Irelia",
    "Jax",
    "Jayce",
    "Kennen",
    "Kled",
    "KSante",
    "Malphite",
    "Mordekaiser",
    "Nasus",
    "Olaf",
    "Ornn",
    "Pantheon",
    "Poppy",
    "Quinn",
    "Renekton",
    "Riven",
    "Rumble",
    "Sett",
    "Shen",
    "Singed",
    "Sion",
    "Teemo",
    "Trundle",
    "Tryndamere",
    "Urgot",
    "Volibear",
    "MonkeyKing",
    "Yasuo",
    "Yone",
    "Yorick",
    "Zac",
    "Zaahen",
]

JUNGLE_CHAMPIONS = [
    "Amumu",
    "BelVeth",
    "Briar",
    "Diana",
    "DrMundo",
    "Ekko",
    "Elise",
    "Evelynn",
    "Fiddlesticks",
    "Graves",
    "Gwen",
    "Hecarim",
    "Ivern",
    "JarvanIV",
    "Jax",
    "Karthus",
    "Kayn",
    "KhaZix",
    "Kindred",
    "LeeSin",
    "Lillia",
    "MasterYi",
    "Naafiri",
    "Nidalee",
    "Nocturne",
    "Nunu",
    "Olaf",
    "Pantheon",
    "Poppy",
    "Rammus",
    "RekSai",
    "Rengar",
    "Sejuani",
    "Shaco",
    "Shyvana",
    "Skarner",
    "Sylas",
    "Taliyah",
    "Trundle",
    "Udyr",
    "Vi",
    "Viego",
    "Volibear",
    "Warwick",
    "MonkeyKing",
    "XinZhao",
    "Zac",
]

MID_CHAMPIONS = [
    "Ahri",
    "Akali",
    "Anivia",
    "Annie",
    "AurelionSol",
    "Aurora",
    "Azir",
    "Brand",
    "Cassiopeia",
    "Corki",
    "Diana",
    "Fizz",
    "Galio",
    "Heimerdinger",
    "Hwei",
    "Kassadin",
    "Katarina",
    "Leblanc",
    "Lissandra",
    "Lux",
    "Malzahar",
    "Mel",
    "Naafiri",
    "Neeko",
    "Orianna",
    "Qiyana",
    "Ryze",
    "Sylas",
    "Syndra",
    "Taliyah",
    "Tristana",
    "TwistedFate",
    "Veigar",
    "Vex",
    "Viktor",
    "Vladimir",
    "Xerath",
    "Yasuo",
    "Yone",
    "Zed",
    "Ziggs",
    "Zoe",
]

ADC_CHAMPIONS = [
    "Aphelios",
    "Ashe",
    "Caitlyn",
    "Corki",
    "Draven",
    "Ezreal",
    "Jhin",
    "Jinx",
    "KaiSa",
    "Kalista",
    "KogMaw",
    "Lucian",
    "MissFortune",
    "Nilah",
    "Samira",
    "Senna",
    "Sivir",
    "Smolder",
    "Tristana",
    "Twitch",
    "Varus",
    "Vayne",
    "Xayah",
    "Yunara",
    "Zeri",
]

SUPPORT_CHAMPIONS = [
    "Alistar",
    "Bard",
    "Blitzcrank",
    "Brand",
    "Braum",
    "Janna",
    "Karma",
    "Leona",
    "Lulu",
    "Lux",
    "Maokai",
    "Milio",
    "Morgana",
    "Nami",
    "Nautilus",
    "Pantheon",
    "Pyke",
    "Rakan",
    "Rell",
    "Renata",
    "Senna",
    "Seraphine",
    "Sona",
    "Soraka",
    "Swain",
    "TahmKench",
    "Taric",
    "Thresh",
    "VelKoz",
    "Xerath",
    "Yuumi",
    "Zilean",
    "Zyra",
]

# Champions by role dictionary for easy access
CHAMPIONS_BY_ROLE = {
    "top": TOP_CHAMPIONS,
    "jungle": JUNGLE_CHAMPIONS,
    "mid": MID_CHAMPIONS,
    "adc": ADC_CHAMPIONS,
    "support": SUPPORT_CHAMPIONS,
}

# System pools based on the new champion lists
# These represent complete champion lists by role for system use
TOP_SOLOQ_POOL = TOP_CHAMPIONS.copy()
JUNGLE_SOLOQ_POOL = JUNGLE_CHAMPIONS.copy()
MID_SOLOQ_POOL = MID_CHAMPIONS.copy()
ADC_SOLOQ_POOL = ADC_CHAMPIONS.copy()
SUPPORT_SOLOQ_POOL = SUPPORT_CHAMPIONS.copy()

# Competitive pool - balanced selection across roles
CHAMPION_POOL = [
    # Top lane meta picks
    "Aatrox",
    "Ambessa",
    "Garen",
    "Jax",
    "Malphite",
    "Ornn",
    "Shen",
    # Jungle meta picks
    "Graves",
    "Hecarim",
    "KhaZix",
    "LeeSin",
    "Viego",
    "Warwick",
    # Mid lane meta picks
    "Ahri",
    "Akali",
    "Orianna",
    "Sylas",
    "Yasuo",
    "Zed",
    # ADC meta picks
    "Ashe",
    "Caitlyn",
    "Jinx",
    "KaiSa",
    "Lucian",
    "Vayne",
    # Support meta picks
    "Leona",
    "Nautilus",
    "Thresh",
    "Lulu",
    "Nami",
    "Morgana",
]

# Legacy compatibility - old list names
TOP_LIST = TOP_CHAMPIONS
JUNGLE_LIST = JUNGLE_CHAMPIONS
MID_LIST = MID_CHAMPIONS
ADC_LIST = ADC_CHAMPIONS
SUPPORT_LIST = SUPPORT_CHAMPIONS

SOLOQ_POOL = TOP_SOLOQ_POOL
ROLE_POOLS = CHAMPIONS_BY_ROLE

# Extended pools (same as base pools since we have complete lists now)
TOP_EXTENDED_POOL = TOP_CHAMPIONS
JUNGLE_EXTENDED_POOL = JUNGLE_CHAMPIONS
MID_EXTENDED_POOL = MID_CHAMPIONS
ADC_EXTENDED_POOL = ADC_CHAMPIONS
SUPPORT_EXTENDED_POOL = SUPPORT_CHAMPIONS

EXTENDED_POOLS = {
    "top": TOP_EXTENDED_POOL,
    "jungle": JUNGLE_EXTENDED_POOL,
    "mid": MID_EXTENDED_POOL,
    "adc": ADC_EXTENDED_POOL,
    "support": SUPPORT_EXTENDED_POOL,
    "multi-role": TOP_EXTENDED_POOL + SUPPORT_EXTENDED_POOL,
    "all-roles": TOP_EXTENDED_POOL
    + SUPPORT_EXTENDED_POOL
    + JUNGLE_EXTENDED_POOL
    + MID_EXTENDED_POOL
    + ADC_EXTENDED_POOL,
}

# ========== Champion Name Normalization Functions ==========


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
        "KhaZix": "khazix",
        "LeeSin": "leesin",
        "KaiSa": "kaisa",
        "MissFortune": "missfortune",
        "TwistedFate": "twistedfate",
        "XinZhao": "xinzhao",
        "ChoGath": "chogath",
        "KogMaw": "kogmaw",
        "RekSai": "reksai",
        "TahmKench": "tahmkench",
        "VelKoz": "velkoz",
        "BelVeth": "belveth",
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
        "khazix": "KhaZix",
        "leesin": "LeeSin",
        "kaisa": "KaiSa",
        "missfortune": "MissFortune",
        "twistedfate": "TwistedFate",
        "xinzhao": "XinZhao",
        "chogath": "ChoGath",
        "kogmaw": "KogMaw",
        "reksai": "RekSai",
        "tahmkench": "TahmKench",
        "velkoz": "VelKoz",
        "belveth": "BelVeth",
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
        "KhaZix": "KhaZix",
        "Kha'Zix": "KhaZix",
        "LeeSin": "LeeSin",
        "Lee Sin": "LeeSin",
        "KaiSa": "KaiSa",
        "Kai'Sa": "KaiSa",
        "MissFortune": "MissFortune",
        "Miss Fortune": "MissFortune",
        "TwistedFate": "TwistedFate",
        "Twisted Fate": "TwistedFate",
        "XinZhao": "XinZhao",
        "Xin Zhao": "XinZhao",
        "ChoGath": "ChoGath",
        "Cho'Gath": "ChoGath",
        "KogMaw": "KogMaw",
        "Kog'Maw": "KogMaw",
        "RekSai": "RekSai",
        "Rek'Sai": "RekSai",
        "TahmKench": "TahmKench",
        "Tahm Kench": "TahmKench",
        "VelKoz": "VelKoz",
        "Vel'Koz": "VelKoz",
        "BelVeth": "BelVeth",
        "Bel'Veth": "BelVeth",
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
