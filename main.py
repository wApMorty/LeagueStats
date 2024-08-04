from db import Database
from parser import Parser

db = Database("db.db")
db.connect()
parser = Parser()

# db.init_champion_table()
for matchup in parser.get_champion_data("camille"):
    champ, winrate, d1, d2, pick, games = matchup
    print(f"{champ} - {winrate}% - {d1} - {d2} - {pick} - {games}")

parser.close()
db.close()
