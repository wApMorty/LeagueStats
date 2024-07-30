import sqlite3
from sqlite3 import Error
import numpy as np

class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self.connection = None

    def connect(self) -> None:
        try:
            self.connection = sqlite3.connect(self.path)
            print("Connection to SQLite DB successful")
        except Error as e:
            print(f"The error '{e}' occurred")

    def close(self) -> None:
        self.connection.close()

    def execute_query(self, query: str) -> None:
        cursor = self.connection.cursor()
        try:
            cursor.execute(query)
            self.connection.commit()
            print(f"Query executed successfully : {query}")
        except Error as e:
            print(f"The error '{e}' occurred")

    def init_champion_table(self) -> None:
        _champion_list = np.unique([
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
            "Sion"
        ])
        
        self.execute_query("DROP TABLE IF EXISTS champions")
        self.execute_query("CREATE TABLE champions (id INTEGER PRIMARY KEY, champion TEXT NOT NULL)")
        
        for champ in _champion_list:
            self.execute_query(f"INSERT INTO champions (champion) VALUES ('{champ}')")

    def init_matchups_table(self) -> None:
        self.execute_query("DROP TABLE IF EXISTS matchups")
        self.execute_query("CREATE TABLE matchups (id INTEGER PRIMARY KEY, champion INTEGER NOT NULL, enemy INTEGER NOT NULL, winrate REAL NOT NULL, games INTEGER NOT NULL)")

    def add_matchup(self, champion: str, enemy: str, winrate: float, games: int) -> None:
        champ_id = self.get_champion_id(champion)
        enemy_id = self.get_champion_id(enemy)
        self.execute_query(f"INSERT INTO matchups (champion, enemy, winrate, games) VALUES ({champ_id}, {enemy_id}, {winrate}, {games})")

    def get_champion_id(self, champion: str) -> None:
        cursor = self.connection.cursor()
        try:
            cursor.execute(f"SELECT id FROM champions WHERE champion = '{champion}' COLLATE NOCASE")
            self.connection.commit()
            return cursor.fetchone()[0]
        except Error as e:
            print(f"The error '{e}' occurred")