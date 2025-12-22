"""Pool statistics calculator and viewer.

This module provides statistical analysis for champion pools, including:
- Average delta2 scores across all champions in pool
- Variance and standard deviation of pool performance
- Coverage metrics (data availability for each champion)
- Distribution analysis (min, max, mean, median)
- Outlier detection (champions with insufficient data)
"""

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from statistics import mean, median, stdev, variance
from ..db import Database
from ..analysis.scoring import ChampionScorer


@dataclass
class ChampionStats:
    """Statistics for a single champion."""
    name: str
    avg_delta2: float
    num_matchups: int
    total_games: int
    has_sufficient_data: bool


@dataclass
class PoolStatistics:
    """Aggregated statistics for a champion pool."""
    pool_name: str
    pool_size: int
    champion_stats: List[ChampionStats]

    # Distribution metrics
    avg_delta2_mean: float
    avg_delta2_median: float
    avg_delta2_min: float
    avg_delta2_max: float
    avg_delta2_stddev: float
    avg_delta2_variance: float

    # Coverage metrics
    champions_with_data: int
    champions_without_data: int
    coverage_percentage: float
    total_matchups: int
    total_games: int

    # Outliers
    outliers: List[str]  # Champions with insufficient data


class PoolStatisticsCalculator:
    """Calculates statistics for champion pools."""

    def __init__(self, db: Database, min_games_threshold: int = 100):
        """Initialize calculator.

        Args:
            db: Database instance (must be connected)
            min_games_threshold: Minimum games required for sufficient data
        """
        self.db = db
        self.scorer = ChampionScorer(db, verbose=False)
        self.min_games_threshold = min_games_threshold

    def calculate_champion_stats(self, champion_name: str) -> Optional[ChampionStats]:
        """Calculate statistics for a single champion.

        Args:
            champion_name: Name of the champion

        Returns:
            ChampionStats object, or None if champion not found
        """
        # Get champion ID
        champion_id = self.db.get_champion_id(champion_name)
        if not champion_id:
            return None

        # Get all matchups for this champion
        matchups = self.db.get_champion_matchups(champion_id)
        if not matchups:
            return ChampionStats(
                name=champion_name,
                avg_delta2=0.0,
                num_matchups=0,
                total_games=0,
                has_sufficient_data=False
            )

        # Filter valid matchups (sufficient data)
        valid_matchups = self.scorer.filter_valid_matchups(matchups)

        # Calculate avg_delta2
        avg_d2 = self.scorer.avg_delta2(valid_matchups) if valid_matchups else 0.0

        # Calculate total games
        total_games = sum(m[5] for m in matchups)  # games column (index 5)

        # Determine if champion has sufficient data
        has_sufficient_data = total_games >= self.min_games_threshold and len(valid_matchups) > 0

        return ChampionStats(
            name=champion_name,
            avg_delta2=avg_d2,
            num_matchups=len(valid_matchups),
            total_games=total_games,
            has_sufficient_data=has_sufficient_data
        )

    def calculate_pool_statistics(
        self,
        pool_name: str,
        champion_list: List[str]
    ) -> PoolStatistics:
        """Calculate comprehensive statistics for a champion pool.

        Args:
            pool_name: Name of the pool
            champion_list: List of champion names in the pool

        Returns:
            PoolStatistics object with all calculated metrics
        """
        # Calculate stats for each champion
        champion_stats: List[ChampionStats] = []
        for champ in champion_list:
            stats = self.calculate_champion_stats(champ)
            if stats:
                champion_stats.append(stats)

        # Filter champions with data for distribution metrics
        champs_with_data = [cs for cs in champion_stats if cs.has_sufficient_data]

        # Calculate distribution metrics
        if champs_with_data:
            delta2_values = [cs.avg_delta2 for cs in champs_with_data]
            avg_delta2_mean_val = mean(delta2_values)
            avg_delta2_median_val = median(delta2_values)
            avg_delta2_min_val = min(delta2_values)
            avg_delta2_max_val = max(delta2_values)
            avg_delta2_stddev_val = stdev(delta2_values) if len(delta2_values) > 1 else 0.0
            avg_delta2_variance_val = variance(delta2_values) if len(delta2_values) > 1 else 0.0
        else:
            avg_delta2_mean_val = 0.0
            avg_delta2_median_val = 0.0
            avg_delta2_min_val = 0.0
            avg_delta2_max_val = 0.0
            avg_delta2_stddev_val = 0.0
            avg_delta2_variance_val = 0.0

        # Calculate coverage metrics
        champions_with_data_count = len(champs_with_data)
        champions_without_data_count = len(champion_stats) - champions_with_data_count
        coverage_percentage = (
            (champions_with_data_count / len(champion_stats) * 100)
            if champion_stats else 0.0
        )
        total_matchups = sum(cs.num_matchups for cs in champion_stats)
        total_games = sum(cs.total_games for cs in champion_stats)

        # Identify outliers (champions without sufficient data)
        outliers = [cs.name for cs in champion_stats if not cs.has_sufficient_data]

        return PoolStatistics(
            pool_name=pool_name,
            pool_size=len(champion_list),
            champion_stats=champion_stats,
            avg_delta2_mean=avg_delta2_mean_val,
            avg_delta2_median=avg_delta2_median_val,
            avg_delta2_min=avg_delta2_min_val,
            avg_delta2_max=avg_delta2_max_val,
            avg_delta2_stddev=avg_delta2_stddev_val,
            avg_delta2_variance=avg_delta2_variance_val,
            champions_with_data=champions_with_data_count,
            champions_without_data=champions_without_data_count,
            coverage_percentage=coverage_percentage,
            total_matchups=total_matchups,
            total_games=total_games,
            outliers=outliers
        )


def format_pool_statistics(stats: PoolStatistics) -> str:
    """Format pool statistics for terminal display.

    Args:
        stats: PoolStatistics object to format

    Returns:
        Formatted string for display
    """
    output = []
    output.append("=" * 70)
    output.append(f"Pool Statistics: {stats.pool_name}")
    output.append("=" * 70)
    output.append("")

    # Pool overview
    output.append("POOL OVERVIEW:")
    output.append(f"  Total Champions: {stats.pool_size}")
    output.append(f"  Champions with Data: {stats.champions_with_data}")
    output.append(f"  Champions without Data: {stats.champions_without_data}")
    output.append(f"  Coverage: {stats.coverage_percentage:.1f}%")
    output.append(f"  Total Matchups: {stats.total_matchups:,}")
    output.append(f"  Total Games: {stats.total_games:,}")
    output.append("")

    # Distribution metrics
    output.append("PERFORMANCE DISTRIBUTION (avg_delta2):")
    output.append(f"  Mean:     {stats.avg_delta2_mean:>8.2f}")
    output.append(f"  Median:   {stats.avg_delta2_median:>8.2f}")
    output.append(f"  Min:      {stats.avg_delta2_min:>8.2f}")
    output.append(f"  Max:      {stats.avg_delta2_max:>8.2f}")
    output.append(f"  Std Dev:  {stats.avg_delta2_stddev:>8.2f}")
    output.append(f"  Variance: {stats.avg_delta2_variance:>8.2f}")
    output.append("")

    # Outliers
    if stats.outliers:
        output.append(f"OUTLIERS ({len(stats.outliers)} champions with insufficient data):")
        for i, outlier in enumerate(stats.outliers, 1):
            output.append(f"  {i}. {outlier}")
        output.append("")

    # Top/Bottom performers
    champs_with_data = [cs for cs in stats.champion_stats if cs.has_sufficient_data]
    if champs_with_data:
        sorted_by_delta2 = sorted(champs_with_data, key=lambda cs: cs.avg_delta2, reverse=True)

        output.append("TOP 5 PERFORMERS (highest avg_delta2):")
        for i, cs in enumerate(sorted_by_delta2[:5], 1):
            output.append(
                f"  {i}. {cs.name:<20} Delta2: {cs.avg_delta2:>7.2f}  "
                f"(Matchups: {cs.num_matchups}, Games: {cs.total_games:,})"
            )
        output.append("")

        output.append("BOTTOM 5 PERFORMERS (lowest avg_delta2):")
        for i, cs in enumerate(sorted_by_delta2[-5:][::-1], 1):
            output.append(
                f"  {i}. {cs.name:<20} Delta2: {cs.avg_delta2:>7.2f}  "
                f"(Matchups: {cs.num_matchups}, Games: {cs.total_games:,})"
            )

    output.append("")
    output.append("=" * 70)

    return "\n".join(output)
