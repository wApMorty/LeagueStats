import sqlite3
from sqlite3 import Error
from typing import List
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
        self.execute_query("CREATE TABLE matchups (id INTEGER PRIMARY KEY, champion INTEGER NOT NULL, enemy INTEGER NOT NULL, winrate REAL NOT NULL, delta1 REAL NOT NULL, delta2 REAL NOT NULL, pickrate REAL NOT NULL, games INTEGER NOT NULL)")

    def add_matchup(self, champion: str, enemy: str, winrate: float, delta1: float, delta2: float, pickrate: float, games: int) -> None:
        champ_id = self.get_champion_id(champion)
        enemy_id = self.get_champion_id(enemy)
        if champ_id is None or enemy_id is None or winrate is None or delta1 is None or delta2 is None or pickrate is None or games is None :
            print(f"{champ_id}, {enemy_id}, {winrate}, {delta1}, {delta2}, {pickrate}, {games}")
            return
        self.execute_query(f"INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games) VALUES ({champ_id}, {enemy_id}, {winrate}, {delta1}, {delta2}, {pickrate}, {games})")

    def get_champion_id(self, champion: str) -> int:
        cursor = self.connection.cursor()
        try:
            cursor.execute(f"SELECT id FROM champions WHERE champion = '{champion}' COLLATE NOCASE")
            self.connection.commit()
            return cursor.fetchone()[0]
        except Error as e:
            print(f"The error '{e}' occurred")

    def get_champion_by_id(self, id: int) -> str :
        cursor = self.connection.cursor()
        try:
            cursor.execute(f"SELECT champion FROM champions WHERE id = {id}")
            self.connection.commit()
            return cursor.fetchone()[0]
        except Error as e:
            print(f"The error '{e}' occurred")

    def get_champion_matchups(self, champion: str) -> List[tuple]:
        champ_id = self.get_champion_id(champion)
        cursor = self.connection.cursor()
        try:
            cursor.execute(f"SELECT * FROM matchups WHERE champion = '{champ_id}' AND pickrate > 0.5")
            self.connection.commit()
            result = cursor.fetchall()
            # returns (enemy, winrate, delta1, delta2, pickrate, games)
            return [(self.get_champion_by_id(elem[2]), elem[3], elem[4], elem[5], elem[6], elem[7]) for elem in result]
        except Error as e:
            print(f"The error '{e}' occurred")