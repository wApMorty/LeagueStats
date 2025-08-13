import numpy as np

CHAMPION_POOL = [
    "Ambessa",
    "DrMundo",
    "Malphite",
    "Yorick",
    "Kennen",
    "Jax",
    "Shen",
    "Riven",
    "Tryndamere",
    "Irelia",
    "Fiora",
    "Gwen"
]

# Top lane pool (your main pool)
TOP_SOLOQ_POOL = [
    "Ambessa",
    "Malphite", 
    "Tryndamere"
]

# Support pool (your secondary pool)
SUPPORT_SOLOQ_POOL = [
    "Morgana",
    "Yuumi",
    "Seraphine"
]

# Legacy name for backward compatibility
SOLOQ_POOL = TOP_SOLOQ_POOL

# Extended pools will be defined after the role lists are defined

# Pool dictionary for easy access
ROLE_POOLS = {
    "top": TOP_SOLOQ_POOL,
    "support": SUPPORT_SOLOQ_POOL,
    "supp": SUPPORT_SOLOQ_POOL,  # Alias
    "all": TOP_SOLOQ_POOL + SUPPORT_SOLOQ_POOL  # Combined pool
}

# Extended pools will be defined at the end of the file after all lists

CHAMPIONS_LIST = np.unique([
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
    "Wukong",
    "VelKoz",
    "Tristana",
    "Ryze",
    "Veigar",
    "Sion",
    "Diana",
    "Ambessa",
    "Mel",
    "Yunara"
])

TOP_LIST = [
    "Irelia",
    "Darius",
    "Garen",
    "Jax",
    "Ornn",
    "Gnar",
    "KSante",
    "Malphite",
    "Renekton",
    "Shen",
    "Zac",
    "ChoGath"
    # B Tier
    # "Galio",
    # "Camille",
    # "Aatrox",
    # "Urgot",
    # "Kled",
    # "Gragas",
    # "Mordekaiser",
    # "Poppy",
    # "Illaoi",
    # "Sion",
    # "Tryndamere",
    # "Volibear",
    # "Gwen",
    # "Sett"
]

JUNGLE_LIST = [
    "Elise",
    "DrMundo",
    # "Olaf",
    "Gwen",
    "JarvanIV",
    "Pantheon",
    "XinZhao",
    "Nidalee",
    "Nocturne",
    "Hecarim",
    "Jax",
    # "Darius", NO DATA
    "KhaZix",
    "BelVeth",
    "Kindred",
    "Naafiri",
    "Viego",
    "Wukong",
    "RekSai",
    "Trundle"
    # B Tier
    # "Amumu",
    # "Volibear",
    # "Karthus",
    # "Lillia"
]

MID_LIST = [
    "Ahri",
    "Orianna",
    "Syndra",
    "Hwei",
    "Mel",
    "Viktor",
    "Galio",
    "Naafiri",
    "Vex",
    "Aurora",
    "Sylas",
    "Yone",
    "Taliyah",
    "Fizz",
    "Corki",
    "Akali",
    "TwistedFate",
    "Tristana",
    "Ryze",
    # B Tier
    # "Annie",
    # "AurelionSol",
    # "Azir",
    # "Kassadin",
    # "Diana",
    # "Lissandra",
    # "Ziggs",
    # "Malzahar",
    # "Zoe",
    # "Anivia"
]

ADC_LIST = [
    # "Jhin",
    # "Vayne",
    # "Ashe",
    # "KaiSa",
    # "Ezreal",
    # "Xayah",
    # "Lucian"
]

SUPPORT_LIST = [
    "Lulu",
    "Janna",
    "Nami",
    "Milio",
    "Soraka",
    "Yuumi",
    "Karma",
    "Blitzcrank",
    "Nautilus",
    "Braum",
    "Elise",
    "Leona",
    "Seraphine",
    "Morgana",
    "Rakan",
    "Thresh"
    # B Tier
    # "Alistar",
    # "Amumu",
    # "Camille",
    # "Galio",
    # "Poppy",
    # "Maokai",
    # "Rell",
    # "Renata",
    # "Sona",
    # "Xerath",
    # "Taric",
    # "TahmKench",
    # "Swain",
    # "Zyra",
    # "VelKoz"
]

# Extended pools for Team Builder analysis (using existing curated lists)
# Include user's main champions + extend with the existing role lists
TOP_EXTENDED_POOL = TOP_SOLOQ_POOL + [champ for champ in TOP_LIST if champ not in TOP_SOLOQ_POOL]

SUPPORT_EXTENDED_POOL = SUPPORT_SOLOQ_POOL + [champ for champ in SUPPORT_LIST if champ not in SUPPORT_SOLOQ_POOL]

JUNGLE_EXTENDED_POOL = JUNGLE_LIST.copy()  # Use the existing curated jungle list

MID_EXTENDED_POOL = MID_LIST.copy()  # Use the existing curated mid list

# For ADC, create from champions available in CHAMPIONS_LIST
ADC_EXTENDED_POOL = [champ for champ in CHAMPIONS_LIST if champ in [
    "Jhin", "Vayne", "Ashe", "KaiSa", "Ezreal", "Xayah", "Lucian",
    "Caitlyn", "MissFortune", "Draven", "Jinx", "Sivir", "Aphelios",
    "Samira", "Nilah", "Zeri", "Smolder", "Kalista", "KogMaw", "Twitch", "Varus"
]]

# Extended pools dictionary for Team Builder (more comprehensive analysis)
EXTENDED_POOLS = {
    "top": TOP_EXTENDED_POOL,
    "support": SUPPORT_EXTENDED_POOL,
    "jungle": JUNGLE_EXTENDED_POOL,
    "mid": MID_EXTENDED_POOL,
    "adc": ADC_EXTENDED_POOL,
    "multi-role": TOP_EXTENDED_POOL + SUPPORT_EXTENDED_POOL,
    "all-roles": TOP_EXTENDED_POOL + SUPPORT_EXTENDED_POOL + JUNGLE_EXTENDED_POOL + MID_EXTENDED_POOL + ADC_EXTENDED_POOL
}