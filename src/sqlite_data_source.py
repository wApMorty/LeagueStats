"""
SQLite Data Source implementation - Thin wrapper around Database class.

This module provides an adapter that wraps the existing Database class to conform
to the DataSource interface. It delegates all calls directly to the underlying
Database instance without adding any business logic.

Design Pattern: Adapter Pattern (Object Adapter)
- Wraps Database instance
- Pure delegation (no business logic)
- Zero behavioral changes
- 100% backward compatible

Author: @pj35
Created: 2026-02-06
Sprint: 2 - API Integration (Adapter Pattern Implementation)
"""

from typing import List, Optional, Dict, Union, Tuple

from .data_source import DataSource
from .db import Database
from .models import Matchup, MatchupDraft, Synergy


class SQLiteDataSource(DataSource):
    """
    Adapter for SQLite database access via Database class.

    This is a thin wrapper that delegates all operations to the existing
    Database class. No business logic is added - this is pure adaptation
    to conform to the DataSource interface.

    Attributes:
        _db: Underlying Database instance (private, implementation detail)

    Example:
        >>> data_source = SQLiteDataSource("data/db.db")
        >>> data_source.connect()
        >>> champion_id = data_source.get_champion_id("Jinx")
        >>> data_source.close()
    """

    def __init__(self, database_path: str) -> None:
        """
        Initialize SQLite data source.

        Args:
            database_path: Path to SQLite database file (e.g., "data/db.db")
        """
        self._db = Database(database_path)

    # ==================== Connection Management ====================

    def connect(self) -> None:
        """Establish connection to SQLite database."""
        self._db.connect()

    def close(self) -> None:
        """Close SQLite database connection."""
        self._db.close()

    # ==================== Champion Queries ====================

    def get_champion_id(self, champion: str) -> Optional[int]:
        """Get champion ID by name (delegates to Database)."""
        return self._db.get_champion_id(champion)

    def get_champion_by_id(self, id: int) -> Optional[str]:
        """Get champion name by ID (delegates to Database)."""
        return self._db.get_champion_by_id(id)

    def get_all_champion_names(self) -> Dict[int, str]:
        """Get mapping of all champion IDs to names (delegates to Database)."""
        return self._db.get_all_champion_names()

    def build_champion_cache(self) -> Dict[str, int]:
        """Build cache of champion name -> ID mappings (delegates to Database)."""
        return self._db.build_champion_cache()

    # ==================== Matchup Queries ====================

    def get_champion_matchups_by_name(
        self, champion_name: str, as_dataclass: bool = True
    ) -> Union[List[Matchup], List[tuple]]:
        """Get matchups for a champion by name (delegates to Database)."""
        return self._db.get_champion_matchups_by_name(champion_name, as_dataclass)

    def get_champion_matchups_for_draft(
        self, champion_name: str, as_dataclass: bool = True
    ) -> Union[List[MatchupDraft], List[tuple]]:
        """Get optimized matchups for draft analysis (delegates to Database)."""
        return self._db.get_champion_matchups_for_draft(champion_name, as_dataclass)

    def get_reverse_matchups_for_draft(
        self, champion_name: str, as_dataclass: bool = True
    ) -> Union[List[MatchupDraft], List[tuple]]:
        """Get reverse matchups for draft analysis (delegates to Database)."""
        return self._db.get_reverse_matchups_for_draft(champion_name, as_dataclass)

    def get_matchup_delta2(self, champion_name: str, enemy_name: str) -> Optional[float]:
        """Get delta2 value for specific matchup (delegates to Database)."""
        return self._db.get_matchup_delta2(champion_name, enemy_name)

    def get_all_matchups_bulk(self) -> Dict[Tuple[str, str], float]:
        """Load all valid matchups in single query (delegates to Database)."""
        return self._db.get_all_matchups_bulk()

    def get_champion_base_winrate(self, champion_name: str) -> float:
        """Calculate champion base winrate (delegates to Database)."""
        return self._db.get_champion_base_winrate(champion_name)

    # ==================== Synergy Queries ====================

    def get_champion_synergies_by_name(
        self, champion_name: str, as_dataclass: bool = True
    ) -> Union[List[Synergy], List[tuple]]:
        """Get synergies for a champion by name (delegates to Database)."""
        return self._db.get_champion_synergies_by_name(champion_name, as_dataclass)

    def get_synergy_delta2(self, champion_name: str, ally_name: str) -> Optional[float]:
        """Get delta2 value for specific synergy (delegates to Database)."""
        return self._db.get_synergy_delta2(champion_name, ally_name)

    def get_all_synergies_bulk(self) -> Dict[Tuple[str, str], float]:
        """Load all valid synergies in single query (delegates to Database)."""
        return self._db.get_all_synergies_bulk()

    # ==================== Champion Scores ====================

    def get_champion_scores_by_name(self, champion_name: str) -> Optional[Dict[str, float]]:
        """Get champion scores by champion name (delegates to Database)."""
        return self._db.get_champion_scores_by_name(champion_name)

    def get_all_champion_scores(self) -> List[tuple]:
        """Get all champion scores with names (delegates to Database)."""
        return self._db.get_all_champion_scores()

    def champion_scores_table_exists(self) -> bool:
        """Check if champion_scores table exists and has data (delegates to Database)."""
        return self._db.champion_scores_table_exists()

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
        """Save or update champion scores in the database."""
        self._db.save_champion_scores(
            champion_id=champion_id,
            avg_delta2=avg_delta2,
            variance=variance,
            coverage=coverage,
            peak_impact=peak_impact,
            volatility=volatility,
            target_ratio=target_ratio,
        )

    # ==================== Ban Recommendations ====================

    def get_pool_ban_recommendations(self, pool_name: str, limit: int = 5) -> List[tuple]:
        """Get pre-calculated ban recommendations (delegates to Database)."""
        return self._db.get_pool_ban_recommendations(pool_name, limit)

    def pool_has_ban_recommendations(self, pool_name: str) -> bool:
        """Check if pool has ban recommendations (delegates to Database)."""
        return self._db.pool_has_ban_recommendations(pool_name)

    def save_pool_ban_recommendations(self, pool_name: str, ban_data: List[tuple]) -> int:
        """Save pre-calculated ban recommendations (delegates to Database)."""
        return self._db.save_pool_ban_recommendations(pool_name, ban_data)
