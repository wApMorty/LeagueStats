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

        Uses probability theory for non-linear scaling:
        - log_odds = 0.12 * delta2 (~1.2% win probability per delta2 unit)
        - win_probability = 1 / (1 + exp(-log_odds))  [logistic function]
        - advantage = (win_probability - 0.5) * 100  [deviation from 50% baseline]

        The logistic function provides natural diminishing returns:
        - Small delta2 (~0-100) scales roughly linearly
        - Large delta2 (>200) shows diminishing returns due to asymptotic behavior
        - Theoretical bounds: -50% to +50% (0% to 100% win probability)
        - Practical range: Most matchups fall within ±20% advantage

        NOTE: No explicit bounds applied. Extreme delta2 values (e.g., 1000)
        will produce very high advantages (>40%), which is intentional for
        representing truly dominant matchups.

        Args:
            delta2: The delta2 value from matchup data
            champion_name: Champion name (unused - kept for backward compatibility)

        Returns:
            Win advantage percentage (positive = our team favored)
            Range: Theoretically [-50, +50], typically [-20, +20]
        """
        # Logistic transformation
        log_odds = 0.12 * delta2  # ~1.2% per delta2 unit
        win_probability = 1 / (1 + math.exp(-log_odds))
        advantage = (win_probability - 0.5) * 100  # Percentage points from 50% baseline

        return advantage

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
           - Calculated with blind pick dilution: (sum_known_delta2 + blind_picks * avg_delta2) / 5
           - Weighted average by pickrate for known matchups
        2. Enemy advantage: How well enemy team performs vs us (from their matchup data)
           - Calculated as simple mean: sum(enemy_delta2_vs_us) / len(known_enemies)
           - Only includes enemies with reverse matchup data (missing data excluded from average)

        Net advantage = our_advantage - enemy_advantage_against_us

        IMPORTANT: The two calculations are asymmetric:
        - Our advantage accounts for all 5 enemy slots (blind picks filled with avg_delta2)
        - Enemy advantage only includes enemies with data (graceful degradation)

        This accounts for matchup asymmetry where delta2(A→B) ≠ delta2(B→A).

        Args:
            matchups: List of matchup data tuples for our champion
            team: Enemy team composition (may be partial, e.g., [1-5] enemies)
            champion_name: Name of our champion (required for reverse matchup lookup)

        Returns:
            Net advantage in percentage points (positive = favorable for us)

        Edge cases:
            - Empty team (blind pick): Returns our avg_delta2 advantage (no enemy perspective)
            - Missing champion_name: Returns 0.0 (cannot calculate bidirectional without it)
            - Missing enemy data: Treats enemy_advantage_against_us as 0.0 (unidirectional fallback)
        """
        if not champion_name:
            # Can't calculate accurately without champion name, return 0
            if self.verbose:
                print("[WARNING] score_against_team called without champion_name, returning neutral advantage")
            return 0.0

        # Use logistic transformation for delta2 to advantage conversion
        if not team:
            # Pure blind pick scenario - no enemy perspective available
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

        # STEP 2: Calculate ENEMY advantage (enemy team's perspective vs our champion)
        # This is how strong the enemies think THEY are against us
        enemy_perspective_deltas = []
        missing_enemies = []

        for enemy in team:
            # Query enemy's perspective: their delta2 vs our champion
            enemy_delta2 = self.db.get_matchup_delta2(enemy, champion_name)
            if enemy_delta2 is not None:
                enemy_perspective_deltas.append(enemy_delta2)
            else:
                missing_enemies.append(enemy)

        # Calculate average enemy advantage against us (simple mean, not weighted)
        # NOTE: Unlike our advantage calculation which is weighted by pickrate,
        # enemy advantage uses simple mean because:
        # 1. We're querying individual matchups (no aggregation needed)
        # 2. Equal weighting of all enemies reflects symmetric team threat
        # 3. Pickrate weighting would undervalue niche counters
        if enemy_perspective_deltas:
            enemy_avg_delta2_against_us = sum(enemy_perspective_deltas) / len(enemy_perspective_deltas)
            enemy_advantage_against_us = self.delta2_to_win_advantage(enemy_avg_delta2_against_us, champion_name)

            # Log if we had partial data
            if missing_enemies and self.verbose:
                print(f"[WARNING] Missing enemy matchup data for {champion_name} vs {missing_enemies}")
                print(f"[WARNING] Using {len(enemy_perspective_deltas)}/{len(team)} enemy matchups for calculation")
        else:
            # No enemy data - graceful degradation to unidirectional
            # Design decision: Treat missing enemy advantage as neutral (0.0)
            # rather than failing, to allow recommendations with incomplete data.
            # This means we trust only OUR perspective when enemy data is missing.
            if self.verbose:
                print(f"[WARNING] No enemy matchup data found for {champion_name} vs {team}")
                print(f"[WARNING] Degrading to unidirectional calculation (enemy advantage = 0)")
            enemy_advantage_against_us = 0.0

        # STEP 3: Combine perspectives for net advantage
        # Net = how much WE counter them - how much THEY counter us
        net_advantage = our_advantage - enemy_advantage_against_us

        return net_advantage

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
