"""Scoring algorithms for champion matchups and team compositions."""

from typing import List, Optional, Union
import math

from ..db import Database
from ..config_constants import analysis_config, role_inference_config
from ..models import Matchup
from .probability import sigmoid, winrate_points_to_logit


def confidence(games: int) -> float:
    """Statistical confidence weight for a sample of `games` games (SPEC-05 B6).

    Composes with `pickrate` (which predicts the opponent's pick, and stays
    untouched) rather than replacing it: the product `pickrate * confidence(games)`
    is the weight to use wherever matchups/synergies are averaged.

    Args:
        games: Number of games backing the sample.

    Returns:
        A value in [0, 1) that tends to 1 as games grows large and to 0 as
        games tends to 0 (half-weight at games == CONFIDENCE_K).
    """
    return games / (games + analysis_config.CONFIDENCE_K)


def estimate_win_probability(individual_winrates: List[float]) -> float:
    """Team win probability from per-champion winrates, via log-odds summation
    (SPEC-05 B7). Replaces the geometric-mean-with-clamp model: no clamp,
    naturally saturating as advantages accumulate.

    Args:
        individual_winrates: e.g. [50 + advantage for advantage in scores],
            where each `advantage` already comes from score_against_team
            (matchup) blended with synergy — see DraftMonitor._final_score.

    Returns:
        Probability in ]0, 1[, never exactly 0 or 1.
    """
    if not individual_winrates:
        return 0.5
    logit_sum = sum(winrate_points_to_logit(wr - 50.0) for wr in individual_winrates)
    return sigmoid(logit_sum)


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
        total_weight = sum(m.pickrate * confidence(m.games) for m in valid_matchups)
        if total_weight == 0:
            return 0.0
        return (
            sum(m.delta1 * m.pickrate * confidence(m.games) for m in valid_matchups) / total_weight
        )

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
        total_weight = sum(m.pickrate * confidence(m.games) for m in valid_matchups)
        if total_weight == 0:
            return 0.0
        return (
            sum(m.delta2 * m.pickrate * confidence(m.games) for m in valid_matchups) / total_weight
        )

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
        total_weight = sum(m.pickrate * confidence(m.games) for m in valid_matchups)
        if total_weight == 0:
            return 0.0
        return (
            sum(m.winrate * m.pickrate * confidence(m.games) for m in valid_matchups) / total_weight
        )

    def delta2_to_win_advantage(self, delta2: float) -> float:
        """Convert a delta2 value to a log-odds contribution (SPEC-05 B7).

        Replaces the old `delta2 * 1.0` identity (linear, unbounded, and
        displayed as if it were already a percentage) with a proper log-odds
        term: `delta2 * K_MATCHUP` points of winrate, converted via
        `winrate_points_to_logit`.

        Internal use only: the result is a log-odds, never displayed raw to
        the user (see score_against_team, which converts back to a saturating
        win-probability delta before returning).

        Args:
            delta2: The delta2 value from matchup data (LoLalytics metric).

        Returns:
            Log-odds contribution (unbounded, additive with other log-odds
            terms — see src/analysis/probability.py).
        """
        return winrate_points_to_logit(delta2 * analysis_config.K_MATCHUP)

    def _lane_weight(
        self, enemy_name: str, enemy_lanes: Optional[dict], player_lane: Optional[str]
    ) -> float:
        """Weight of one enemy's matchup, by lane proximity (SPEC-04 §4.3).

        The enemy sharing our lane is our direct counter and counts more
        than the rest of the enemy team. Defaults to OTHER_LANE_WEIGHT
        (1.0) whenever lane info is missing, which keeps this a no-op
        (identical to pre-SPEC-04 behavior) unless both `player_lane` and
        this enemy's inferred lane are known.
        """
        if not enemy_lanes or not player_lane:
            return role_inference_config.OTHER_LANE_WEIGHT
        enemy_lane = enemy_lanes.get(enemy_name)
        if enemy_lane == player_lane:
            return role_inference_config.SAME_LANE_WEIGHT
        return role_inference_config.OTHER_LANE_WEIGHT

    def score_against_team(
        self,
        matchups: List[Matchup],
        team: List[str],
        champion_name: str = None,
        banned_champions: List[str] = None,
        lane: Optional[str] = None,
        enemy_lanes: Optional[dict] = None,
        player_lane: Optional[str] = None,
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
            lane: Optional lane, transmise aux requêtes inverses internes
                  (self.db.get_matchup_delta2). None = agrégation toutes lanes,
                  comportement inchangé. `matchups` est supposée déjà filtrée par
                  l'appelant si un filtrage par lane est voulu sur ce côté.
            enemy_lanes: Optional enemy name -> inferred lane (SPEC-04 §4.3).
                  Combined with `player_lane` to weight the enemy sharing our
                  lane (SAME_LANE_WEIGHT) above the rest of the team
                  (OTHER_LANE_WEIGHT). None = every enemy weighted equally,
                  comportement inchangé.
            player_lane: Our own champion's lane. Required alongside
                  `enemy_lanes` for the weighting above to take effect.

        Returns:
            Net advantage as a saturating win-probability delta, in percentage
            points (never raw log-odds), positive = favorable for us.
            Numerically close to the old linear delta2 for typical matchups
            (SPEC-05 B7: sigmoid(x) - 0.5 ≈ x/4 near x=0, and the log-odds
            scale is calibrated so this cancels out for k_m=1.0), but bounded
            as advantages accumulate instead of growing without limit.

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

        # SPEC-05 B7: delta2_to_win_advantage now returns a log-odds, so every
        # branch below converts back to a saturating probability delta via
        # sigmoid before returning — never a raw log-odds to the caller.
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
            return (sigmoid(self.delta2_to_win_advantage(avg_delta2_val)) - 0.5) * 100.0

        # STEP 1: Calculate OUR advantage (our champion vs enemy team)
        total_delta2 = 0
        matchup_count = 0
        remaining_matchups = matchups.copy()

        # Calculate delta2 for known matchups, weighted by lane proximity
        # (SPEC-04 §4.3): our direct counter (same lane) counts more than
        # the rest of the enemy team.
        for enemy in team:
            for i, matchup in enumerate(remaining_matchups):
                if matchup.enemy_name.lower() == enemy.lower():
                    weight = self._lane_weight(enemy, enemy_lanes, player_lane)
                    total_delta2 += matchup.delta2 * weight
                    matchup_count += weight
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
        our_advantage = self.delta2_to_win_advantage(our_avg_delta2)

        # STEP 2: Calculate ENEMY advantage (enemy team's perspective vs our champion)
        # This is how strong the enemies think THEY are against us
        enemy_perspective_deltas = []
        missing_enemies = []

        for enemy in team:
            # Query enemy's perspective: their delta2 vs our champion
            enemy_delta2 = self.db.get_matchup_delta2(enemy, champion_name, lane=lane)
            if enemy_delta2 is not None:
                weight = self._lane_weight(enemy, enemy_lanes, player_lane)
                enemy_perspective_deltas.append((enemy_delta2, weight))
            else:
                missing_enemies.append(enemy)

        # Calculate average enemy advantage against us, weighted by lane
        # proximity (SPEC-04 §4.3; equal weighting — i.e. a plain mean — when
        # enemy_lanes/player_lane are absent, which is the pre-SPEC-04 case).
        # NOTE: Unlike our advantage calculation which is weighted by pickrate,
        # enemy advantage otherwise uses simple mean because:
        # 1. We're querying individual matchups (no aggregation needed)
        # 2. Equal weighting of all enemies reflects symmetric team threat
        # 3. Pickrate weighting would undervalue niche counters
        if enemy_perspective_deltas:
            total_weight = sum(weight for _, weight in enemy_perspective_deltas)
            enemy_avg_delta2_against_us = (
                sum(delta2 * weight for delta2, weight in enemy_perspective_deltas) / total_weight
            )
            enemy_advantage_against_us = self.delta2_to_win_advantage(enemy_avg_delta2_against_us)

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
        # Net = how much WE counter them - how much THEY counter us.
        # Both terms are log-odds here (SPEC-05 B7); convert to a saturating
        # win-probability delta only once, at the very end.
        net_advantage_logit = our_advantage - enemy_advantage_against_us

        return (sigmoid(net_advantage_logit) - 0.5) * 100.0

    def calculate_team_winrate(self, individual_winrates: List[float]) -> dict:
        """
        Calculate team win probability from individual champion winrates (SPEC-05 B7).

        Thin wrapper around the module-level `estimate_win_probability`, which
        sums log-odds contributions instead of taking a geometric mean of the
        winrates: five players don't win five independent coin flips, they
        win or lose the same game together, so multiplying probabilities
        never modeled anything real here (see SPEC-05 §1.3). No clamp either
        — [20, 80] on individual winrates and [25, 75] on the result existed
        only to hide the geometric mean's absurd outputs; the log-odds sum
        naturally stays in ]0, 100[ without help.

        Args:
            individual_winrates: List of actual winrates (e.g. [54.2, 48.5, 52.1])

        Returns:
            dict with 'team_winrate', 'individual_winrates'
        """
        if not individual_winrates:
            return {"team_winrate": 50.0, "individual_winrates": []}

        probability = estimate_win_probability(individual_winrates)
        return {"team_winrate": probability * 100.0, "individual_winrates": individual_winrates}

    def calculate_synergy_bonus(
        self, champion_name: str, ally_names: List[str], lane: Optional[str] = None
    ) -> float:
        """Calculate synergy bonus for a champion with given allies.

        Formula: weighted average of delta2 values from synergies table.
        Uses synergy_config.USE_WEIGHTED_AVERAGE to determine aggregation method.

        Args:
            champion_name: Name of the champion
            ally_names: List of allied champion names
            lane: Optional lane filter transmise à get_champion_synergies_by_name.
                  None = agrégation toutes lanes, comportement inchangé.

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

        synergies = self.db.get_champion_synergies_by_name(
            champion_name, as_dataclass=True, lane=lane
        )
        if not synergies:
            return 0.0

        # Filter synergies matching our allies (comparaison insensible à la casse,
        # comme partout ailleurs dans le scoring — cf. score_against_team)
        allies_lower = {name.lower() for name in ally_names}
        relevant_synergies = [s for s in synergies if s.ally_name.lower() in allies_lower]
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
            total_weight = sum(s.pickrate * confidence(s.games) for s in valid_synergies)
            if total_weight == 0:
                return 0.0
            synergy_bonus = (
                sum(s.delta2 * s.pickrate * confidence(s.games) for s in valid_synergies)
                / total_weight
            )
        else:
            synergy_bonus = sum(s.delta2 for s in valid_synergies) / len(valid_synergies)

        return synergy_bonus

    def calculate_final_score_with_synergies(
        self, matchup_score: float, champion_name: str, ally_names: List[str]
    ) -> float:
        """Calculate final score combining matchup score and synergy bonus.

        Formula: final_score = matchup_score + (synergy_bonus * K_SYNERGY)

        SPEC-05 B7: the multiplier is now `analysis_config.K_SYNERGY`, which
        replaces `synergy_config.SYNERGY_BONUS_MULTIPLIER` (same role, same
        default value 0.3 -> 0.5 per the model's calibration constants — the
        two must never coexist, see SPEC-05 §7).

        Args:
            matchup_score: Base score from matchup analysis
            champion_name: Champion being scored
            ally_names: List of allied champions

        Returns:
            Final score with synergy bonus applied

        Example:
            >>> scorer.calculate_final_score_with_synergies(100.0, "Yasuo", ["Malphite"])
            142.75  # 100 + (85.5 * 0.5)
        """
        from ..config_constants import synergy_config

        if not synergy_config.SYNERGIES_ENABLED:
            return matchup_score

        synergy_bonus = self.calculate_synergy_bonus(champion_name, ally_names)
        final_score = matchup_score + (synergy_bonus * analysis_config.K_SYNERGY)

        if self.verbose:
            print(
                f"[SYNERGY] {champion_name}: matchup={matchup_score:.2f}, "
                f"synergy_bonus={synergy_bonus:.2f}, final={final_score:.2f}"
            )

        return final_score
