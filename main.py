from db import Database
from parser import Parser
from assistant import Assistant
from constants import CHAMPIONS_LIST

def load_data() -> None:
    db = Database("db.db")
    db.connect()
    parser = Parser()
    
    db.init_champion_table()
    db.init_matchups_table()
    for champion in CHAMPIONS_LIST:
        for matchup in parser.get_champion_data(champion.lower()):
            enemy, winrate, d1, d2, pick, games = matchup
            db.add_matchup(champion, enemy, winrate, d1, d2, pick, games)
    
    parser.close()
    db.close()

if __name__ == "__main__":
    ast = Assistant()
    
    ast.draft(10)
        
    # ast.score_teams_no_input()

    ast.close()
