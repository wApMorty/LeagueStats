"""Scoring algorithms for champion matchups and team compositions."""

from typing import List
import math

from ..db import Database
from ..config_constants import analysis_config


class ChampionScorer:
    """Handles scoring calculations for champion matchups and team compositions."""

    def __init__(self, db: Database, verbose: bool = False):
        """
        Initialize ChampionScorer.

        Args:
            db: Database instance
            verbose: Enable verbose logging
        """
        self.db = db
        self.verbose = verbose

    def filter_valid_matchups(self, matchups: List[tuple]) -> List[tuple]:
        """
        Filter matchups with sufficient pick rate and games data.

        Args:
            matchups: List of matchup tuples

        Returns:
            Filtered list of valid matchups
        """
        return [
            m for m in matchups
            if m[4] >= analysis_config.MIN_PICKRATE and m[5] >= analysis_config.MIN_MATCHUP_GAMES
        ]

    def avg_delta1(self, matchups: List[tuple]) -> float:
        """
        Calculate weighted average delta1 from valid matchups.

        Args:
            matchups: List of matchup tuples

        Returns:
            Weighted average delta1
        """
        valid_matchups = self.filter_valid_matchups(matchups)
        if not valid_matchups:
            return 0.0
        total_weight = sum(m[4] for m in valid_matchups)
        if total_weight == 0:
            return 0.0
        return sum(m[2] * m[4] for m in valid_matchups) / total_weight

    def avg_delta2(self, matchups: List[tuple]) -> float:
        """
        Calculate weighted average delta2 from valid matchups.

        Args:
            matchups: List of matchup tuples

        Returns:
            Weighted average delta2
        """
        valid_matchups = self.filter_valid_matchups(matchups)
        if not valid_matchups:
            return 0.0
        total_weight = sum(m[4] for m in valid_matchups)
        if total_weight == 0:
            return 0.0
        return sum(m[3] * m[4] for m in valid_matchups) / total_weight

    def avg_winrate(self, matchups: List[tuple]) -> float:
        """
        Calculate weighted average winrate from valid matchups.

        Args:
            matchups: List of matchup tuples

        Returns:
            Weighted average winrate
        """
        valid_matchups = self.filter_valid_matchups(matchups)
        if not valid_matchups:
            return 0.0
        total_weight = sum(m[4] for m in valid_matchups)
        if total_weight == 0:
            return 0.0
        return sum(m[1] * m[4] for m in valid_matchups) / total_weight

    def delta2_to_win_advantage(self, delta2: float, champion_name: str) -> float:
        """
        Convert delta2 value to win advantage using logistic transformation.

        Uses mathematical model:
        - Logistic scaling for realistic bounds and diminishing returns
        - log_odds = 0.12 * delta2 (~1.2% per delta2 unit)
        - advantage = (win_probability - 0.5) * 100

        Args:
            delta2: The delta2 value from matchup data
            champion_name: Champion name (kept for interface compatibility)

        Returns:
            Win advantage percentage (positive = our team favored)
        """
        # Logistic transformation for realistic bounds
        log_odds = 0.12 * delta2  # ~1.2% per delta2 unit
        win_probability = 1 / (1 + math.exp(-log_odds))
        advantage = (win_probability - 0.5) * 100  # Percentage points from 50% baseline

        # Apply conservative bounds (-10% to +10%)
        return max(-10.0, min(10.0, advantage))

    def score_against_team(
        self,
        matchups: List[tuple],
        team: List[str],
        champion_name: str = None
    ) -> float:
        """
        Calculate bidirectional advantage against a team composition.

        Combines two perspectives for more accurate predictions:
        1. Our advantage: How well our champion performs vs enemy team (from our matchup data)
        2. Opponent advantage: How well enemy team performs vs us (from their matchup data)

        Net advantage = our_advantage - opponent_advantage

        This accounts for asymmetric matchups where delta2 is not symmetric
        (e.g., Aatrox vs Darius may differ from Darius vs Aatrox).

        Args:
            matchups: List of matchup data tuples for our champion
            team: Enemy team composition
            champion_name: Name of our champion (required for bidirectional calculation)

        Returns:
            Net advantage in percentage points (positive = favorable for us)
        """
        if not champion_name:
            # Can't calculate accurately without champion name, return 0
            if self.verbose:
                print("[WARNING] score_against_team called without champion_name, returning neutral advantage")
            return 0.0

        # Use logistic transformation for delta2 to advantage conversion
        if not team:
            # Pure blind pick scenario - no opponent perspective available
            avg_delta2_val = self.avg_delta2(matchups)
            return self.delta2_to_win_advantage(avg_delta2_val, champion_name)

        # STEP 1: Calculate OUR advantage (our champion vs enemy team)
        total_delta2 = 0
        matchup_count = 0
        remaining_matchups = matchups.copy()

        # Calculate delta2 for known matchups
        for enemy in team:
            for i, matchup in enumerate(remaining_matchups):
                if matchup[0].lower() == enemy.lower():
                    delta2 = matchup[3]
                    total_delta2 += delta2
                    matchup_count += 1
                    remaining_matchups.pop(i)
                    break

        # Calculate delta2 for unknown matchups (blind picks)
        blind_picks = 5 - len(team)
        if blind_picks > 0:
            avg_delta2_val = self.avg_delta2(remaining_matchups)
            total_delta2 += blind_picks * avg_delta2_val
            matchup_count += blind_picks

        # Convert average delta2 to advantage
        if matchup_count == 0:
            return 0.0  # No data available

        our_avg_delta2 = total_delta2 / matchup_count
        our_advantage = self.delta2_to_win_advantage(our_avg_delta2, champion_name)

        # STEP 2: Calculate OPPONENT advantage (enemy team vs our champion)
        opponent_deltas = []
        for enemy in team:
            # Query enemy's perspective: their delta2 vs our champion
            enemy_delta2 = self.db.get_matchup_delta2(enemy, champion_name)
            if enemy_delta2 is not None:
                opponent_deltas.append(enemy_delta2)

        # Calculate average opponent advantage (simple mean, not weighted)
        if opponent_deltas:
            opponent_avg_delta2 = sum(opponent_deltas) / len(opponent_deltas)
            opponent_advantage = self.delta2_to_win_advantage(opponent_avg_delta2, champion_name)
        else:
            # No opponent data - graceful degradation to unidirectional
            opponent_advantage = 0.0

        # STEP 3: Combine perspectives for net advantage
        net_advantage = our_advantage - opponent_advantage

        # Apply conservative bounds
        return max(-10.0, min(10.0, net_advantage))

    def calculate_team_winrate(self, individual_winrates: List[float]) -> dict:
        """
        Calculate team win probability from individual champion winrates using geometric mean.

        Uses probability theory to combine individual winrates:
        - Converts winrates to probabilities (divide by 100)
        - Calculates team probability using geometric mean (multiplicative effects)
        - More mathematically sound than arithmetic averaging

        Args:
            individual_winrates: List of actual winrates (e.g. [54.2, 48.5, 52.1])

        Returns:
            dict with 'team_winrate', 'individual_winrates'
        """
        if not individual_winrates:
            return {'team_winrate': 50.0, 'individual_winrates': []}

        # Clamp individual winrates to realistic bounds
        clamped_winrates = []
        for winrate in individual_winrates:
            clamped_winrate = max(20.0, min(80.0, winrate))
            clamped_winrates.append(clamped_winrate)

        # Convert to probabilities and calculate geometric mean
        geometric_mean = 1.0
        for winrate in clamped_winrates:
            probability = winrate / 100.0  # Convert to probability (0.0 to 1.0)
            geometric_mean *= probability

        # Take nth root to get geometric mean probability
        geometric_mean = geometric_mean ** (1.0 / len(clamped_winrates))

        # Convert back to percentage
        team_winrate = geometric_mean * 100.0

        # Apply conservative bounds (extreme team winrates are unrealistic)
        team_winrate = max(25.0, min(75.0, team_winrate))

        return {
            'team_winrate': team_winrate,
            'individual_winrates': clamped_winrates
        }
