"""
Abstract Data Source interface for champion statistics.

This module defines the abstract base class for all data sources (SQLite, API, Hybrid).
It establishes a common contract that all implementations must follow, enabling
seamless switching between data sources without modifying client code.

Architecture Pattern: Adapter Pattern
- DataSource: Abstract interface (this file)
- SQLiteDataSource: Adapter for local SQLite database
- APIDataSource: Adapter for remote FastAPI backend
- HybridDataSource: Composite adapter with fallback logic

Author: @pj35
Created: 2026-02-06
Sprint: 2 - API Integration (Adapter Pattern Implementation)
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Union, Tuple


class DataSource(ABC):
    """
    Abstract base class for champion data sources.

    All data source implementations (SQLite, API, Hybrid) must implement this interface.
    This ensures consistent behavior across different backends and enables dependency
    injection in the Assistant class.

    Design Principles:
    - Interface mirrors Database public API for backward compatibility
    - All methods are abstract (no default implementations)
    - Return types match original Database methods
    - Thread-safe implementations are encouraged but not enforced
    """

    # ==================== Connection Management ====================

    @abstractmethod
    def connect(self) -> None:
        """
        Establish connection to the data source.

        For SQLite: Opens database connection
        For API: Validates connectivity (optional warmup)
        For Hybrid: Connects both sources
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """
        Close connection to the data source.

        Should be called when data source is no longer needed.
        Must be idempotent (safe to call multiple times).
        """
        pass

    # ==================== Champion Queries ====================

    @abstractmethod
    def get_champion_id(self, champion: str) -> Optional[int]:
        """
        Get champion ID by name.

        Args:
            champion: Champion name (case-insensitive)

        Returns:
            Champion ID if found, None otherwise
        """
        pass

    @abstractmethod
    def get_champion_by_id(self, id: int) -> Optional[str]:
        """
        Get champion name by ID.

        Args:
            id: Champion Riot ID

        Returns:
            Champion name if found, None otherwise
        """
        pass

    @abstractmethod
    def get_all_champion_names(self) -> Dict[int, str]:
        """
        Get mapping of all champion IDs to names.

        Returns:
            Dictionary mapping champion_id -> champion_name
        """
        pass

    @abstractmethod
    def build_champion_cache(self) -> Dict[str, int]:
        """
        Build cache of champion name -> ID mappings for faster lookups.

        Returns:
            Dictionary mapping champion_name -> champion_id
            Includes both exact case and lowercase variants
        """
        pass

    # ==================== Matchup Queries ====================

    @abstractmethod
    def get_champion_matchups_by_name(
        self, champion_name: str, as_dataclass: bool = True
    ) -> Union[List["Matchup"], List[tuple]]:
        """
        Get matchups for a champion by name with enemy names included.

        Args:
            champion_name: Name of the champion to get matchups for
            as_dataclass: If True, return Matchup objects. If False, return tuples.

        Returns:
            List of Matchup objects or tuples (enemy_name, winrate, delta1, delta2, pickrate, games)
        """
        pass

    @abstractmethod
    def get_champion_matchups_for_draft(
        self, champion_name: str, as_dataclass: bool = True
    ) -> Union[List["MatchupDraft"], List[tuple]]:
        """
        Optimized query for draft analysis - returns only columns needed for draft calculations.

        Returns 4 columns instead of 6 (33% reduction):
        - enemy_name, delta2, pickrate, games

        Args:
            champion_name: Name of the champion to get matchups for
            as_dataclass: If True, return MatchupDraft objects. If False, return tuples.

        Returns:
            List of MatchupDraft objects or tuples (enemy_name, delta2, pickrate, games)
        """
        pass

    @abstractmethod
    def get_matchup_delta2(self, champion_name: str, enemy_name: str) -> Optional[float]:
        """
        Get delta2 value for a specific matchup using direct SQL query.

        Optimized for reverse lookup approach - avoids loading all matchups.

        Args:
            champion_name: Name of our champion
            enemy_name: Name of enemy champion

        Returns:
            delta2 value if matchup exists with sufficient data, None otherwise
        """
        pass

    @abstractmethod
    def get_all_matchups_bulk(self) -> Dict[Tuple[str, str], float]:
        """
        Load ALL valid matchups in a single query for caching.

        Returns dict mapping (champion_name, enemy_name) -> delta2 value.
        Only includes matchups meeting quality thresholds (pickrate >= 0.5%, games >= 200).

        This is much faster than calling get_matchup_delta2() repeatedly.

        Returns:
            Dict with keys as tuples (champion_name, enemy_name) and values as delta2 floats
        """
        pass

    @abstractmethod
    def get_champion_base_winrate(self, champion_name: str) -> float:
        """
        Calculate champion base winrate from all matchup data using weighted average.

        Args:
            champion_name: Name of the champion

        Returns:
            Weighted average winrate (0.0-100.0), or 50.0 if no data
        """
        pass

    # ==================== Synergy Queries ====================

    @abstractmethod
    def get_champion_synergies_by_name(
        self, champion_name: str, as_dataclass: bool = True
    ) -> Union[List["Synergy"], List[tuple]]:
        """
        Get synergies for a champion by name with ally names included.

        Args:
            champion_name: Name of the champion to get synergies for
            as_dataclass: If True, return Synergy objects. If False, return tuples.

        Returns:
            List of Synergy objects or tuples (ally_name, winrate, delta1, delta2, pickrate, games)
        """
        pass

    @abstractmethod
    def get_synergy_delta2(self, champion_name: str, ally_name: str) -> Optional[float]:
        """
        Get delta2 value for a specific champion-ally synergy.

        Args:
            champion_name: Name of the champion
            ally_name: Name of the allied champion

        Returns:
            delta2 value if synergy exists, None otherwise
        """
        pass

    @abstractmethod
    def get_all_synergies_bulk(self) -> Dict[Tuple[str, str], float]:
        """
        Load ALL valid synergies in a single query for caching.

        Returns dict mapping (champion_name, ally_name) -> delta2 value.
        Only includes synergies meeting quality thresholds (pickrate >= 0.5%, games >= 200).

        Returns:
            Dict with keys as tuples (champion_name, ally_name) and values as delta2 floats
        """
        pass

    # ==================== Champion Scores ====================

    @abstractmethod
    def get_champion_scores_by_name(self, champion_name: str) -> Optional[Dict[str, float]]:
        """
        Get champion scores by champion name.

        Args:
            champion_name: Name of the champion

        Returns:
            Dictionary with keys: avg_delta2, variance, coverage, peak_impact, volatility, target_ratio
            None if champion not found or no scores available
        """
        pass

    @abstractmethod
    def get_all_champion_scores(self) -> List[tuple]:
        """
        Get all champion scores with champion names.

        Returns:
            List of tuples (name, avg_delta2, variance, coverage, peak_impact, volatility, target_ratio)
            Sorted by champion name
        """
        pass

    @abstractmethod
    def champion_scores_table_exists(self) -> bool:
        """
        Check if champion_scores table exists and has data.

        Returns:
            True if table exists and has records, False otherwise
        """
        pass

    @abstractmethod
    def save_champion_scores(
        self,
        champion_id: int,
        avg_delta2: float,
        variance: float,
        coverage: float,
        peak_impact: float,
        volatility: float,
        target_ratio: float,
    ) -> None:
        """Save or update champion scores in the database.

        Args:
            champion_id: The champion's database ID
            avg_delta2: Average delta squared metric
            variance: Variance metric
            coverage: Coverage metric
            peak_impact: Peak impact metric
            volatility: Volatility metric
            target_ratio: Target ratio metric
        """
        pass

    # ==================== Ban Recommendations ====================

    @abstractmethod
    def get_pool_ban_recommendations(self, pool_name: str, limit: int = 5) -> List[tuple]:
        """
        Get pre-calculated ban recommendations for a champion pool.

        Args:
            pool_name: Name of the champion pool
            limit: Maximum number of recommendations to return

        Returns:
            List of tuples (enemy_champion, threat_score, best_response_delta2,
                           best_response_champion, matchups_count)
            Sorted by threat_score descending
        """
        pass

    @abstractmethod
    def pool_has_ban_recommendations(self, pool_name: str) -> bool:
        """
        Check if a pool has pre-calculated ban recommendations.

        Args:
            pool_name: Name of the champion pool

        Returns:
            True if recommendations exist, False otherwise
        """
        pass
