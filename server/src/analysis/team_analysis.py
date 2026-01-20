"""Team composition analysis and matchup prediction."""

from typing import List

from ..db import Database
from ..utils.display import safe_print
from .scoring import ChampionScorer


class TeamAnalyzer:
    """Analyzes and compares team compositions for matchup predictions."""

    def __init__(self, db: Database, scorer: ChampionScorer):
        """
        Initialize TeamAnalyzer.

        Args:
            db: Database instance
            scorer: ChampionScorer instance
        """
        self.db = db
        self.scorer = scorer

    def analyze_teams(self, team1: List[str], team2: List[str]) -> None:
        """
        Statistical team analysis using geometric mean for team winrates.

        Compares two complete team compositions and displays:
        - Individual champion advantages
        - Team winrate predictions
        - Matchup confidence level

        Args:
            team1: List of 5 champion names for team 1
            team2: List of 5 champion names for team 2
        """
        # Calculate individual champion advantages
        scores1 = []
        for champion in team1:
            matchups = self.db.get_champion_matchups_by_name(champion)
            advantage = self.scorer.score_against_team(matchups, team2, champion_name=champion)
            scores1.append((champion, advantage))

        scores2 = []
        for champion in team2:
            matchups = self.db.get_champion_matchups_by_name(champion)
            advantage = self.scorer.score_against_team(matchups, team1, champion_name=champion)
            scores2.append((champion, advantage))

        # Convert advantages to winrates for geometric mean calculation
        # score_against_team returns advantage in percentage points from 50% baseline
        # So winrate = 50.0 + advantage (e.g., +3.5% advantage = 53.5% winrate)
        winrates1 = [50.0 + advantage for champion, advantage in scores1]
        winrates2 = [50.0 + advantage for champion, advantage in scores2]

        team1_stats = self.scorer.calculate_team_winrate(winrates1)
        team2_stats = self.scorer.calculate_team_winrate(winrates2)

        # Normalize team winrates to ensure they sum to 100%
        total_winrate = team1_stats["team_winrate"] + team2_stats["team_winrate"]
        if total_winrate > 0:
            team1_normalized = (team1_stats["team_winrate"] / total_winrate) * 100.0
            team2_normalized = (team2_stats["team_winrate"] / total_winrate) * 100.0
        else:
            team1_normalized = team2_normalized = 50.0  # Fallback for edge case

        # Update stats with normalized values
        team1_stats["raw_winrate"] = team1_stats["team_winrate"]
        team2_stats["raw_winrate"] = team2_stats["team_winrate"]
        team1_stats["team_winrate"] = team1_normalized
        team2_stats["team_winrate"] = team2_normalized

        # Display results
        print("=" * 60)
        safe_print(f"🔵 TEAM 1 ANALYSIS:")
        print("-" * 40)
        for champion, advantage in scores1:
            winrate = 50.0 + advantage
            print(f"{champion:<15} | {advantage:+5.2f}% advantage ({winrate:.1f}% winrate)")

        print("-" * 40)
        safe_print(
            f"🎯 Team Winrate: {team1_stats['team_winrate']:.1f}% (raw: {team1_stats['raw_winrate']:.1f}%)"
        )

        print("=" * 60)
        safe_print(f"🔴 TEAM 2 ANALYSIS:")
        print("-" * 40)
        for champion, advantage in scores2:
            winrate = 50.0 + advantage
            print(f"{champion:<15} | {advantage:+5.2f}% advantage ({winrate:.1f}% winrate)")

        print("-" * 40)
        safe_print(
            f"🎯 Team Winrate: {team2_stats['team_winrate']:.1f}% (raw: {team2_stats['raw_winrate']:.1f}%)"
        )

        # Matchup prediction
        print("=" * 60)
        safe_print(f"📊 MATCHUP PREDICTION:")
        team_diff = team1_stats["team_winrate"] - team2_stats["team_winrate"]

        print(
            f"Team 1 vs Team 2: {team1_stats['team_winrate']:.1f}% vs {team2_stats['team_winrate']:.1f}%"
        )
        print(f"Expected advantage: {team_diff:+.1f}% for Team 1")

        # Confidence level based on magnitude
        if abs(team_diff) >= 10:
            safe_print(f"🟢 Strong advantage predicted")
        elif abs(team_diff) >= 5:
            safe_print(f"🟡 Moderate advantage predicted")
        elif abs(team_diff) >= 2:
            safe_print(f"🟠 Small advantage predicted")
        else:
            safe_print(f"⚪ Very close matchup predicted")

        print("=" * 60)

    def analyze_teams_interactive(self) -> None:
        """
        Interactive team analysis with user input.

        Prompts user to input two full team compositions (5 champions each)
        and displays matchup analysis.
        """
        team1 = []
        team2 = []

        for i in range(5):
            team1.append(input(f"Team 1 - Champion {i+1}:"))
        for i in range(5):
            team2.append(input(f"Team 2 - Champion {i+1}:"))

        self.analyze_teams(team1, team2)
