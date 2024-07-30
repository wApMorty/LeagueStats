import db
import parser

db = db.Database("db.db")
db.connect()
# parser = parser.Parser()

print(db.get_champion_id("rumble"))

# winrate, games = parser.get_matchup_data("hecarim", "aatrox")
# print(winrate)
# print(games)

# db.init_champion_table()

# parser.close()
db.close()