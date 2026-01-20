"""Scoring algorithms for champion matchups and team compositions."""

from typing import List, Union
import math

from ..db import Database
from ..config_constants import analysis_config
from ..models import Matchup


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

    def filter_valid_matchups(self, matchups: List[Matchup]) -> List[Matchup]:
        """
        Filter matchups with sufficient pick rate and games data.

        Args:
            matchups: List of Matchup objects

        Returns:
            Filtered list of valid matchups
        """
        return [
            m
            for m in matchups
            if m.pickrate >= analysis_config.MIN_PICKRATE
            and m.games >= analysis_config.MIN_MATCHUP_GAMES
        ]

    def avg_delta1(self, matchups: List[Matchup]) -> float:
        """
        Calculate weighted average delta1 from valid matchups.

        Args:
            matchups: List of Matchup objects

        Returns:
            Weighted average delta1
        """
        valid_matchups = self.filter_valid_matchups(matchups)
        if not valid_matchups:
            return 0.0
        total_weight = sum(m.pickrate for m in valid_matchups)
        if total_weight == 0:
            return 0.0
        return sum(m.delta1 * m.pickrate for m in valid_matchups) / total_weight

    def avg_delta2(self, matchups: List[Matchup]) -> float:
        """
        Calculate weighted average delta2 from valid matchups.

        Args:
            matchups: List of Matchup objects

        Returns:
            Weighted average delta2
        """
        valid_matchups = self.filter_valid_matchups(matchups)
        if not valid_matchups:
            return 0.0
        total_weight = sum(m.pickrate for m in valid_matchups)
        if total_weight == 0:
            return 0.0
        return sum(m.delta2 * m.pickrate for m in valid_matchups) / total_weight

    def avg_winrate(self, matchups: List[Matchup]) -> float:
        """
        Calculate weighted average winrate from valid matchups.

        Args:
            matchups: List of Matchup objects

        Returns:
            Weighted average winrate
        """
        valid_matchups = self.filter_valid_matchups(matchups)
        if not valid_matchups:
            return 0.0
        total_weight = sum(m.pickrate for m in valid_matchups)
        if total_weight == 0:
            return 0.0
        return sum(m.winrate * m.pickrate for m in valid_matchups) / total_weight

    def delta2_to_win_advantage(self, delta2: float, champion_name: str) -> float:
        """
        Convert delta2 value to win advantage using empirically-validated linear scaling.

        Based on analysis of 36,000+ matchups in the database:
        - delta2 from LoLalytics is already correlated with winrate delta
        - Empirical ratio: 1 delta2 ≈ 1.0 percentage point advantage
        - Previous logistic transformation incorrectly amplified values by ~3x

        The linear conversion is validated by database analysis showing:
        - delta2 = 3.40 → actual winrate delta = ~3-5% (not 10%+ from logistic)
        - delta2 range in DB: -51.43 to +31.74
        - Typical matchups: delta2 between -10 and +10

        Args:
            delta2: The delta2 value from matchup data (LoLalytics metric)
            champion_name: Champion name (unused - kept for backward compatibility)

        Returns:
            Win advantage percentage (positive = our team favored)
            Range: Typically [-10, +10], extreme cases up to ±30%

        Example:
            delta2 = 3.40 → advantage = 3.40% (not 10.06% from old formula)
        """
        # Simple linear conversion (1:1 ratio validated empirically)
        # No sigmoid needed - delta2 is not a log-odds, it's already performance-correlated
        advantage = delta2 * 1.0

        return advantage

    def score_against_team(
        self,
        matchups: List[Matchup],
        team: List[str],
        champion_name: str = None,
        banned_champions: List[str] = None,
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
            matchups: List of Matchup objects for our champion
            team: Enemy team composition (may be partial, e.g., [1-5] enemies)
            champion_name: Name of our champion (required for reverse matchup lookup)
            banned_champions: List of banned champion names to exclude from blind pick calculations

        Returns:
            Net advantage in percentage points (positive = favorable for us)

        Edge cases:
            - Empty team (blind pick): Returns our avg_delta2 advantage (no enemy perspective)
            - Missing champion_name: Returns 0.0 (cannot calculate bidirectional without it)
            - Missing enemy data: Treats enemy_advantage_against_us as 0.0 (unidirectional fallback)
            - Banned champions: Excluded from remaining matchup pool when calculating avg_delta2 for blind picks
        """
        if not champion_name:
            # Can't calculate accurately without champion name, return 0
            if self.verbose:
                print("[WARNING] score_against_team() called without champion_name parameter")
                print(
                    "[WARNING] Cannot calculate bidirectional advantage - returning 0.0 (neutral)"
                )
                print("[ACTION] Pass champion_name parameter to enable bidirectional calculation")
            return 0.0

        # Use logistic transformation for delta2 to advantage conversion
        if not team:
            # Pure blind pick scenario - no enemy perspective available
            # Filter out banned champions from matchup pool
            available_matchups = matchups
            if banned_champions:
                banned_lower = [name.lower() for name in banned_champions]
                available_matchups = [
                    m for m in matchups if m.enemy_name.lower() not in banned_lower
                ]
            avg_delta2_val = self.avg_delta2(available_matchups)
            return self.delta2_to_win_advantage(avg_delta2_val, champion_name)

        # STEP 1: Calculate OUR advantage (our champion vs enemy team)
        total_delta2 = 0
        matchup_count = 0
        remaining_matchups = matchups.copy()

        # Calculate delta2 for known matchups
        for enemy in team:
            for i, matchup in enumerate(remaining_matchups):
                if matchup.enemy_name.lower() == enemy.lower():
                    delta2 = matchup.delta2
                    total_delta2 += delta2
                    matchup_count += 1
                    remaining_matchups.pop(i)
                    break

        # Calculate delta2 for unknown matchups (blind picks)
        blind_picks = 5 - len(team)
        if blind_picks > 0:
            # Filter out banned champions from remaining matchup pool
            available_matchups = remaining_matchups
            if banned_champions:
                banned_lower = [name.lower() for name in banned_champions]
                available_matchups = [
                    m for m in remaining_matchups if m.enemy_name.lower() not in banned_lower
                ]
            avg_delta2_val = self.avg_delta2(available_matchups)
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
            enemy_avg_delta2_against_us = sum(enemy_perspective_deltas) / len(
                enemy_perspective_deltas
            )
            enemy_advantage_against_us = self.delta2_to_win_advantage(
                enemy_avg_delta2_against_us, champion_name
            )

            # Log if we had partial data
            if missing_enemies and self.verbose:
                print(f"[WARNING] Missing enemy matchup data: {champion_name} vs {missing_enemies}")
                print(
                    f"[INFO] Using {len(enemy_perspective_deltas)}/{len(team)} enemy matchups for calculation"
                )
                print(f"[ACTION] Update database to include matchup data for missing enemies")
        else:
            # No enemy data - graceful degradation to unidirectional
            # Design decision: Treat missing enemy advantage as neutral (0.0)
            # rather than failing, to allow recommendations with incomplete data.
            # This means we trust only OUR perspective when enemy data is missing.
            if self.verbose:
                print(f"[WARNING] No enemy matchup data found for {champion_name} vs {team}")
                print(f"[INFO] Degrading to unidirectional calculation (enemy advantage = 0)")
                print(
                    f"[ACTION] Scrape enemy champion data or update database to enable bidirectional calculation"
                )
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
            return {"team_winrate": 50.0, "individual_winrates": []}

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

        return {"team_winrate": team_winrate, "individual_winrates": clamped_winrates}

    def calculate_synergy_bonus(self, champion_name: str, ally_names: List[str]) -> float:
        """Calculate synergy bonus for a champion with given allies.

        Formula: weighted average of delta2 values from synergies table.
        Uses synergy_config.USE_WEIGHTED_AVERAGE to determine aggregation method.

        Args:
            champion_name: Name of the champion
            ally_names: List of allied champion names

        Returns:
            Synergy bonus score (weighted average delta2 from allies)

        Example:
            >>> scorer.calculate_synergy_bonus("Yasuo", ["Malphite", "Diana"])
            85.5  # Positive synergy bonus
        """
        from ..config_constants import synergy_config

        # Feature toggle: return 0 if synergies disabled
        if not synergy_config.SYNERGIES_ENABLED:
            return 0.0

        if not ally_names:
            return 0.0

        synergies = self.db.get_champion_synergies_by_name(champion_name, as_dataclass=True)
        if not synergies:
            return 0.0

        # Filter synergies matching our allies
        relevant_synergies = [s for s in synergies if s.ally_name in ally_names]
        if not relevant_synergies:
            return 0.0

        # Filter by quality thresholds (similar to matchups)
        valid_synergies = [
            s
            for s in relevant_synergies
            if s.pickrate >= synergy_config.MIN_SYNERGY_PICKRATE
            and s.games >= synergy_config.MIN_SYNERGY_GAMES
        ]

        if not valid_synergies:
            return 0.0

        # Calculate bonus (weighted or simple average)
        if synergy_config.USE_WEIGHTED_AVERAGE:
            total_weight = sum(s.pickrate for s in valid_synergies)
            if total_weight == 0:
                return 0.0
            synergy_bonus = sum(s.delta2 * s.pickrate for s in valid_synergies) / total_weight
        else:
            synergy_bonus = sum(s.delta2 for s in valid_synergies) / len(valid_synergies)

        return synergy_bonus

    def calculate_final_score_with_synergies(
        self, matchup_score: float, champion_name: str, ally_names: List[str]
    ) -> float:
        """Calculate final score combining matchup score and synergy bonus.

        Formula: final_score = matchup_score + (synergy_bonus * multiplier)

        Args:
            matchup_score: Base score from matchup analysis
            champion_name: Champion being scored
            ally_names: List of allied champions

        Returns:
            Final score with synergy bonus applied

        Example:
            >>> scorer.calculate_final_score_with_synergies(100.0, "Yasuo", ["Malphite"])
            125.65  # 100 + (85.5 * 0.3)
        """
        from ..config_constants import synergy_config

        if not synergy_config.SYNERGIES_ENABLED:
            return matchup_score

        synergy_bonus = self.calculate_synergy_bonus(champion_name, ally_names)
        final_score = matchup_score + (synergy_bonus * synergy_config.SYNERGY_BONUS_MULTIPLIER)

        if self.verbose:
            print(
                f"[SYNERGY] {champion_name}: matchup={matchup_score:.2f}, "
                f"synergy_bonus={synergy_bonus:.2f}, final={final_score:.2f}"
            )

        return final_score
