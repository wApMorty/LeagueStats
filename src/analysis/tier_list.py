"""Tier list generation for champion pools."""

from typing import List

from ..db import Database
from ..constants import TOP_LIST, JUNGLE_LIST, MID_LIST, ADC_LIST, SUPPORT_LIST
from ..config_constants import analysis_config
from .scoring import ChampionScorer


class TierListGenerator:
    """Generates tier lists based on champion performance metrics."""

    def __init__(self, db: Database, scorer: ChampionScorer, min_games: int = None):
        """
        Initialize TierListGenerator.

        Args:
            db: Database instance
            scorer: ChampionScorer instance for calculating metrics
            min_games: Minimum games threshold (defaults to config value)
        """
        self.db = db
        self.scorer = scorer
        self.min_games = min_games or analysis_config.MIN_GAMES_THRESHOLD

    def generate_by_delta1(self, champion_list: List[str]) -> List[tuple]:
        """
        Generate tier list ranked by average delta1 (gold difference at 15min).

        Args:
            champion_list: List of champion names to rank

        Returns:
            List of (champion, delta1_score) tuples, sorted by score descending
        """
        scores = []
        for champion in champion_list:
            matchups = self.db.get_champion_matchups_by_name(champion)
            if sum(m[5] for m in matchups) < self.min_games:
                continue  # Skip this champion but continue processing others
            score = self.scorer.avg_delta1(matchups)
            scores.append((champion, score))
            scores.sort(key=lambda x: -x[1])
        return scores

    def generate_by_delta2(self, champion_list: List[str]) -> List[tuple]:
        """
        Generate tier list ranked by average delta2 (gold difference at end).

        Args:
            champion_list: List of champion names to rank

        Returns:
            List of (champion, delta2_score) tuples, sorted by score descending
        """
        scores = []
        for champion in champion_list:
            matchups = self.db.get_champion_matchups_by_name(champion)
            if sum(m[5] for m in matchups) < self.min_games:
                continue  # Skip this champion but continue processing others
            score = self.scorer.avg_delta2(matchups)
            scores.append((champion, score))
            scores.sort(key=lambda x: -x[1])
        return scores

    def generate_for_lane(self, lane: str) -> List[tuple]:
        """
        Generate tier list for a specific lane using delta2.

        Args:
            lane: Lane name ('top', 'jungle', 'mid', 'adc', 'support')

        Returns:
            List of (champion, delta2_score) tuples, sorted by score descending
        """
        champion_list = ""
        if lane == "top":
            champion_list = TOP_LIST
        elif lane == "jungle":
            champion_list = JUNGLE_LIST
        elif lane == "mid":
            champion_list = MID_LIST
        elif lane == "adc":
            champion_list = ADC_LIST
        elif lane == "support":
            champion_list = SUPPORT_LIST
        else:
            print("Invalid lane specified.")
            return []
        return self.generate_by_delta2(champion_list)
