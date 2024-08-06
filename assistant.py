from typing import List
from constants import CHAMPIONS_LIST
from db import Database

class Assistant:
    def __init__(self) -> None:
        self.db = Database("db.db")
        self.db.connect()
    
    def close(self) -> None:
        self.db.close()

    def avg_delta1(self, matchups: List[tuple]) -> float:
        return sum((m[2]*m[4]) for m in matchups)/len(matchups)

    def avg_delta2(self, matchups: List[tuple]) -> float:
        return sum((m[3]*m[4]) for m in matchups)/len(matchups)

    def score_against_team(self, matchups: List[tuple], team: List[str]) -> float:
        score = 0
        blind_picks = 5 - len(team)
        for enemy in team:
            enemy_idx = 0
            for m in matchups:
                if m[0].lower() == enemy.lower():
                    enemy_idx = matchups.index(m)
                    score += m[3]
                    break
            matchups.pop(enemy_idx)
        score += blind_picks * self.avg_delta2(matchups)
        return score

    def tierlist_delta1(self) -> List[tuple]:
        scores = []
        for champion in CHAMPIONS_LIST:
            matchups = self.db.get_champion_matchups(champion)
            score = self.avg_delta1(matchups)
            scores.append((champion, score))
            scores.sort(key=lambda x: -x[1])
        return scores

    def tierlist_delta2(self) -> List[tuple]:
        scores = []
        for champion in CHAMPIONS_LIST:
            matchups = self.db.get_champion_matchups(champion)
            score = self.avg_delta2(matchups)
            scores.append((champion, score))
            scores.sort(key=lambda x: -x[1])
        return scores

    def draft(self, nb_results: int) -> None:
        scores = []
        enemy_team = []
        _results = nb_results
        
        enemy = input("Champion 1 :")
        while(enemy != "" and len(enemy_team)<4):
            enemy_team.append(enemy)
            enemy = input(f"Champion {len(enemy_team) + 1} :")

        for champion in CHAMPIONS_LIST:
            if champion not in enemy_team:
                matchups = self.db.get_champion_matchups(champion)
                score = self.score_against_team(matchups, enemy_team)
                scores.append((champion, score))
                scores.sort(key=lambda x: -x[1])

        for index in range(_results):
            print(scores[index])
        while (input("Want more ?") == "y"):
            _results += nb_results
            for index in range(_results):
                print(scores[index])

    def blind_pick(self) -> None:
        lst = self.tierlist_delta2()
        _results = 10
        for index in range(_results):
            print(lst[index])
        while (input("Want more ?") == "y"):
            _results += 10
            for index in range(_results):
                print(lst[index])
    
    def score_teams(self, team1: List[str], team2: List[str]) -> None:
        scores1 = []
        for i in range(len(team1)):
            scores1.append((team1[i], self.score_against_team(self.db.get_champion_matchups(team1[i]), team2)))
        scores2 = []
        for i in range(len(team2)):
            scores2.append((team2[i], self.score_against_team(self.db.get_champion_matchups(team2[i]), team1)))
        
        print("=============")
        sm = 0
        for i in range(len(scores1)):
            print(f"{scores1[i][0]} - {scores1[i][1]}")
            sm += scores1[i][1]
        print("---------")
        print(sm/5)
        
        print("=============")
        sm = 0
        for i in range(len(scores2)):
            print(f"{scores2[i][0]} - {scores2[i][1]}")
            sm += scores2[i][1]
        print("---------")
        print(sm/5)
    
    def score_teams_no_input(self):
        team1 = []
        team2 = []

        for i in range(5):
            team1.append(input(f"Team 1 - Champion {i+1}:"))
        for i in range(5):
            team2.append(input(f"Team 2 - Champion {i+1}:"))
        
        return self.score_teams(team1, team2)