import db
import parser

db = db.Database("db.db")
db.connect()

print(db.get_champion_id("rumble"))

# parser = parser.Parser()
# winrate, games = parser.get_matchup_data("hecarim", "aatrox")
# print(winrate)
# print(games)

#db.init_champion_table()

db.close()