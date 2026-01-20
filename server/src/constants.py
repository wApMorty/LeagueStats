"""Champion constants and role lists for LeagueStats Coach API Server."""

# Champion lists by role (used by tier list generation)
TOP_LIST = [
    "Aatrox", "Ambessa", "Camille", "Chogath", "Darius", "DrMundo", "Fiora",
    "Galio", "Gangplank", "Garen", "Gnar", "Gragas", "Gwen", "Illaoi",
    "Irelia", "Jax", "Jayce", "Kennen", "Kled", "KSante", "Malphite",
    "Mordekaiser", "Nasus", "Olaf", "Ornn", "Pantheon", "Poppy", "Quinn",
    "Renekton", "Riven", "Rumble", "Sett", "Shen", "Singed", "Sion", "Teemo",
    "Trundle", "Tryndamere", "Urgot", "Volibear", "MonkeyKing", "Yasuo",
    "Yone", "Yorick", "Zac", "Zaahen"
]

JUNGLE_LIST = [
    "Amumu", "Belveth", "Briar", "Diana", "DrMundo", "Ekko", "Elise",
    "Evelynn", "Fiddlesticks", "Graves", "Gwen", "Hecarim", "Ivern",
    "JarvanIV", "Jax", "Karthus", "Kayn", "Khazix", "Kindred", "LeeSin",
    "Lillia", "MasterYi", "Naafiri", "Nidalee", "Nocturne", "Nunu", "Olaf",
    "Pantheon", "Poppy", "Rammus", "RekSai", "Rengar", "Sejuani", "Shaco",
    "Shyvana", "Skarner", "Sylas", "Taliyah", "Trundle", "Udyr", "Vi",
    "Viego", "Volibear", "Warwick", "MonkeyKing", "XinZhao", "Zac"
]

MID_LIST = [
    "Ahri", "Akali", "Anivia", "Annie", "AurelionSol", "Aurora", "Azir",
    "Brand", "Cassiopeia", "Corki", "Diana", "Fizz", "Galio", "Heimerdinger",
    "Hwei", "Kassadin", "Katarina", "Leblanc", "Lissandra", "Lux", "Malzahar",
    "Mel", "Naafiri", "Neeko", "Orianna", "Qiyana", "Ryze", "Sylas", "Syndra",
    "Taliyah", "Tristana", "TwistedFate", "Veigar", "Vex", "Viktor", "Vladimir",
    "Xerath", "Yasuo", "Yone", "Zed", "Ziggs", "Zoe"
]

ADC_LIST = [
    "Aphelios", "Ashe", "Caitlyn", "Corki", "Draven", "Ezreal", "Jhin",
    "Jinx", "Kaisa", "Kalista", "KogMaw", "Lucian", "MissFortune", "Nilah",
    "Samira", "Senna", "Sivir", "Smolder", "Tristana", "Twitch", "Varus",
    "Vayne", "Xayah", "Yunara", "Zeri"
]

SUPPORT_LIST = [
    "Alistar", "Bard", "Blitzcrank", "Brand", "Braum", "Janna", "Karma",
    "Leona", "Lulu", "Lux", "Maokai", "Milio", "Morgana", "Nami", "Nautilus",
    "Pantheon", "Pyke", "Rakan", "Rell", "Renata", "Senna", "Seraphine",
    "Sona", "Soraka", "Swain", "TahmKench", "Taric", "Thresh", "Velkoz",
    "Xerath", "Yuumi", "Zilean", "Zyra"
]

# SoloQ pool (for backwards compatibility with client code)
SOLOQ_POOL = TOP_LIST.copy()

# Competitive pool (meta champions across roles)
CHAMPION_POOL = [
    # Top lane meta picks
    "Aatrox", "Ambessa", "Garen", "Jax", "Malphite", "Ornn", "Shen",
    # Jungle meta picks
    "Graves", "Hecarim", "Khazix", "LeeSin", "Viego", "Warwick",
    # Mid lane meta picks
    "Ahri", "Akali", "Orianna", "Sylas", "Yasuo", "Zed",
    # ADC meta picks
    "Ashe", "Caitlyn", "Jinx", "Kaisa", "Lucian", "Vayne",
    # Support meta picks
    "Leona", "Nautilus", "Thresh", "Lulu", "Nami", "Morgana"
]
