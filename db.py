import sqlite3
from sqlite3 import Error
from constants import CHAMPIONS_LIST

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
        self.execute_query("DROP TABLE IF EXISTS champions")
        self.execute_query("CREATE TABLE champions (id INTEGER PRIMARY KEY, champion TEXT NOT NULL)")
        
        for champ in CHAMPIONS_LIST:
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