"""
Main Assistant class - Coordinator for champion analysis and recommendations.

This is the new modular version that delegates to specialized modules while
maintaining backward compatibility with the original API.
"""

from typing import List, Optional

from .db import Database
from .config import config
from .config_constants import analysis_config

# Import specialized modules
from .analysis.scoring import ChampionScorer
from .analysis.tier_list import TierListGenerator
from .analysis.recommendations import RecommendationEngine
from .analysis.team_analysis import TeamAnalyzer
from .utils.champion_utils import (
    validate_champion_name,
    validate_champion_data,
    validate_champion_pool,
    select_champion_pool,
    select_extended_champion_pool,
    print_champion_list
)


class Assistant:
    """
    Main coordinator for League of Legends draft analysis.

    Delegates to specialized modules while maintaining backward compatibility
    with the original monolithic API.
    """

    def __init__(self, verbose: bool = False) -> None:
        """
        Initialize Assistant and all sub-components.

        Args:
            verbose: Enable verbose logging
        """
        self.MIN_GAMES = analysis_config.MIN_GAMES_THRESHOLD
        self.db = Database(config.DATABASE_PATH)
        self.db.connect()
        self.verbose = verbose

        # Initialize specialized components
        self.scorer = ChampionScorer(self.db, verbose=verbose)
        self.tier_list_gen = TierListGenerator(self.db, self.scorer)
        self.recommender = RecommendationEngine(self.db, self.scorer)
        self.team_analyzer = TeamAnalyzer(self.db, self.scorer)

    def close(self) -> None:
        """Close database connection."""
        self.db.close()

    # ==================== Champion Pool Selection ====================
    # Delegated to utils.champion_utils

    def select_champion_pool(self) -> List[str]:
        """Interactive pool selection for the user."""
        return select_champion_pool()

    def select_extended_champion_pool(self) -> List[str]:
        """Interactive extended pool selection for Team Builder analysis."""
        return select_extended_champion_pool()

    def validate_champion_name(self, name: str) -> Optional[str]:
        """Validate and normalize champion name with fuzzy matching."""
        return validate_champion_name(name)

    def _validate_champion_data(self, champion: str) -> tuple:
        """Validate if a champion has sufficient data in database."""
        return validate_champion_data(self.db, champion)

    def _validate_champion_pool(self, champion_pool: List[str]) -> tuple:
        """Validate entire champion pool and return viable champions."""
        return validate_champion_pool(self.db, champion_pool)

    def print_champion_list(self, champion_list: List[tuple]) -> None:
        """Print formatted champion list."""
        print_champion_list(champion_list)

    # ==================== Scoring Methods ====================
    # Delegated to analysis.scoring.ChampionScorer

    def _filter_valid_matchups(self, matchups: List[tuple]) -> List[tuple]:
        """Filter matchups with sufficient pick rate and games data."""
        return self.scorer.filter_valid_matchups(matchups)

    def avg_delta1(self, matchups: List[tuple]) -> float:
        """Calculate weighted average delta1 from valid matchups."""
        return self.scorer.avg_delta1(matchups)

    def avg_delta2(self, matchups: List[tuple]) -> float:
        """Calculate weighted average delta2 from valid matchups."""
        return self.scorer.avg_delta2(matchups)

    def avg_winrate(self, matchups: List[tuple]) -> float:
        """Calculate weighted average winrate from valid matchups."""
        return self.scorer.avg_winrate(matchups)

    def score_against_team(
        self,
        matchups: List[tuple],
        team: List[str],
        champion_name: str = None
    ) -> float:
        """Calculate advantage against a team composition."""
        return self.scorer.score_against_team(matchups, team, champion_name)

    def _delta2_to_win_advantage(self, delta2: float, champion_name: str) -> float:
        """Convert delta2 value to win advantage using logistic transformation."""
        return self.scorer.delta2_to_win_advantage(delta2, champion_name)

    def _calculate_team_winrate(self, individual_winrates: List[float]) -> dict:
        """Calculate team win probability from individual champion winrates."""
        return self.scorer.calculate_team_winrate(individual_winrates)

    # ==================== Tier List Generation ====================
    # Delegated to analysis.tier_list.TierListGenerator

    def tierlist_delta1(self, champion_list: List[str]) -> List[tuple]:
        """Generate tier list ranked by average delta1."""
        return self.tier_list_gen.generate_by_delta1(champion_list)

    def tierlist_delta2(self, champion_list: List[str]) -> List[tuple]:
        """Generate tier list ranked by average delta2."""
        return self.tier_list_gen.generate_by_delta2(champion_list)

    def tierlist_lane(self, lane: str) -> List[tuple]:
        """Generate tier list for a specific lane using delta2."""
        return self.tier_list_gen.generate_for_lane(lane)

    # ==================== Recommendations ====================
    # Delegated to analysis.recommendations.RecommendationEngine

    def draft(self, nb_results: int) -> None:
        """Interactive draft recommendation (legacy simple version)."""
        return self.recommender.draft_simple(nb_results)

    def _calculate_and_display_recommendations(
        self,
        enemy_team: List[str],
        ally_team: List[str],
        nb_results: int,
        champion_pool: List[str] = None,
        banned_champions: List[str] = None
    ) -> List[tuple]:
        """Calculate champion recommendations and display top results."""
        return self.recommender.calculate_and_display_recommendations(
            enemy_team, ally_team, nb_results, champion_pool, banned_champions
        )

    # ==================== Team Analysis ====================
    # Delegated to analysis.team_analysis.TeamAnalyzer

    def score_teams(self, team1: List[str], team2: List[str]) -> None:
        """Statistical team analysis using geometric mean for team winrates."""
        return self.team_analyzer.analyze_teams(team1, team2)

    def score_teams_no_input(self) -> None:
        """Interactive team analysis with user input."""
        return self.team_analyzer.analyze_teams_interactive()
