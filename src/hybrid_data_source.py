"""
Hybrid Data Source implementation - API with SQLite fallback.

This module provides a composite data source that tries the API first and
falls back to SQLite on errors. It supports multiple modes:
- api_only: Use API only, fail if unavailable
- sqlite_only: Use SQLite only (offline mode)
- hybrid: Try API first, fallback to SQLite (default)

Design Pattern: Composite Pattern + Strategy Pattern
- Composes APIDataSource + SQLiteDataSource
- Selects strategy based on api_config.MODE
- Graceful degradation on API failures
- Warning logs for diagnostics

Author: @pj35
Created: 2026-02-06
Sprint: 2 - API Integration (Adapter Pattern Implementation)
"""

import logging
from typing import List, Optional, Dict, Union, Tuple

from .data_source import DataSource
from .api_data_source import APIDataSource
from .sqlite_data_source import SQLiteDataSource
from .config_constants import api_config
from .models import Matchup, MatchupDraft, Synergy

# Configure logging
logger = logging.getLogger(__name__)


class HybridDataSource(DataSource):
    """
    Hybrid data source with API-first strategy and SQLite fallback.

    This composite data source provides robust access to champion statistics
    by trying the remote API first and falling back to local SQLite on errors.

    Modes (configurable via api_config.MODE):
    - "hybrid": Try API first, fallback to SQLite (default)
    - "api_only": Use API only, fail if unavailable
    - "sqlite_only": Use SQLite only (offline mode)

    Attributes:
        api_source: APIDataSource instance (optional)
        sqlite_source: SQLiteDataSource instance
        _mode: Current operation mode

    Example:
        >>> # Default hybrid mode
        >>> data_source = HybridDataSource()
        >>> data_source.connect()
        >>> champion_id = data_source.get_champion_id("Jinx")  # Try API, fallback SQLite
        >>> data_source.close()

        >>> # Force SQLite only
        >>> from src.config_constants import api_config
        >>> api_config.MODE = "sqlite_only"
        >>> data_source = HybridDataSource()
        >>> data_source.connect()
    """

    def __init__(self, database_path: Optional[str] = None) -> None:
        """
        Initialize hybrid data source.

        Args:
            database_path: Path to SQLite database (default: from config)
        """
        self._mode = api_config.MODE

        # Initialize API source (unless sqlite_only mode)
        if self._mode != "sqlite_only" and api_config.ENABLED:
            try:
                self.api_source = APIDataSource()
            except Exception as e:
                logger.warning(f"[HYBRID] Failed to initialize API source: {e}")
                self.api_source = None
        else:
            self.api_source = None

        # Initialize SQLite source (unless api_only mode)
        if self._mode != "api_only":
            if database_path:
                from .config import config

                database_path = database_path or config.DATABASE_PATH
            from .config import config

            self.sqlite_source = SQLiteDataSource(database_path or config.DATABASE_PATH)
        else:
            self.sqlite_source = None

    # ==================== Connection Management ====================

    def connect(self) -> None:
        """Establish connections to available data sources."""
        if self.api_source is not None:
            try:
                self.api_source.connect()
                logger.info("[HYBRID] API source connected")
            except Exception as e:
                logger.warning(f"[HYBRID] API source connection failed: {e}")
                if self._mode == "api_only":
                    raise

        if self.sqlite_source is not None:
            try:
                self.sqlite_source.connect()
                logger.info("[HYBRID] SQLite source connected")
            except Exception as e:
                logger.error(f"[HYBRID] SQLite source connection failed: {e}")
                if self._mode == "sqlite_only":
                    raise

    def close(self) -> None:
        """Close connections to all data sources."""
        if self.api_source is not None:
            try:
                self.api_source.close()
            except Exception as e:
                logger.warning(f"[HYBRID] Error closing API source: {e}")

        if self.sqlite_source is not None:
            try:
                self.sqlite_source.close()
            except Exception as e:
                logger.warning(f"[HYBRID] Error closing SQLite source: {e}")

    def _try_api_with_fallback(self, method_name: str, *args, **kwargs):
        """
        Try API method first, fallback to SQLite on error.

        This is the core hybrid strategy logic. Logs warnings when fallback occurs.

        Args:
            method_name: Name of the method to call
            *args: Positional arguments to pass to method
            **kwargs: Keyword arguments to pass to method

        Returns:
            Result from API or SQLite (whichever succeeds)

        Raises:
            Exception: If both sources fail or in api_only mode
        """
        # Try API first (if available and not sqlite_only mode)
        if self.api_source is not None and self._mode != "sqlite_only":
            try:
                method = getattr(self.api_source, method_name)
                return method(*args, **kwargs)
            except Exception as e:
                logger.warning(f"[HYBRID] API call failed for {method_name}: {e}")
                if self._mode == "api_only":
                    raise  # No fallback in api_only mode

        # Fallback to SQLite
        if self.sqlite_source is not None:
            try:
                method = getattr(self.sqlite_source, method_name)
                return method(*args, **kwargs)
            except Exception as e:
                logger.error(f"[HYBRID] SQLite fallback failed for {method_name}: {e}")
                raise

        # No sources available
        raise RuntimeError(f"[HYBRID] No data sources available for {method_name}")

    # ==================== Champion Queries ====================

    def get_champion_id(self, champion: str) -> Optional[int]:
        """Get champion ID by name (hybrid: API first, SQLite fallback)."""
        return self._try_api_with_fallback("get_champion_id", champion)

    def get_champion_by_id(self, id: int) -> Optional[str]:
        """Get champion name by ID (hybrid: API first, SQLite fallback)."""
        return self._try_api_with_fallback("get_champion_by_id", id)

    def get_all_champion_names(self) -> Dict[int, str]:
        """Get mapping of all champion IDs to names (hybrid: API first, SQLite fallback)."""
        return self._try_api_with_fallback("get_all_champion_names")

    def build_champion_cache(self) -> Dict[str, int]:
        """Build cache of champion name -> ID mappings (hybrid: API first, SQLite fallback)."""
        return self._try_api_with_fallback("build_champion_cache")

    # ==================== Matchup Queries ====================

    def get_champion_matchups_by_name(
        self, champion_name: str, as_dataclass: bool = True
    ) -> Union[List[Matchup], List[tuple]]:
        """Get matchups for a champion by name (hybrid: API first, SQLite fallback)."""
        return self._try_api_with_fallback(
            "get_champion_matchups_by_name", champion_name, as_dataclass
        )

    def get_champion_matchups_for_draft(
        self, champion_name: str, as_dataclass: bool = True
    ) -> Union[List[MatchupDraft], List[tuple]]:
        """Get optimized matchups for draft (hybrid: API first, SQLite fallback)."""
        return self._try_api_with_fallback(
            "get_champion_matchups_for_draft", champion_name, as_dataclass
        )

    def get_matchup_delta2(self, champion_name: str, enemy_name: str) -> Optional[float]:
        """Get delta2 value for specific matchup (hybrid: API first, SQLite fallback)."""
        return self._try_api_with_fallback("get_matchup_delta2", champion_name, enemy_name)

    def get_all_matchups_bulk(self) -> Dict[Tuple[str, str], float]:
        """Load all valid matchups in single query (hybrid: API first, SQLite fallback)."""
        return self._try_api_with_fallback("get_all_matchups_bulk")

    def get_champion_base_winrate(self, champion_name: str) -> float:
        """Calculate champion base winrate (hybrid: API first, SQLite fallback)."""
        return self._try_api_with_fallback("get_champion_base_winrate", champion_name)

    # ==================== Synergy Queries ====================

    def get_champion_synergies_by_name(
        self, champion_name: str, as_dataclass: bool = True
    ) -> Union[List[Synergy], List[tuple]]:
        """Get synergies for a champion by name (hybrid: API first, SQLite fallback)."""
        return self._try_api_with_fallback(
            "get_champion_synergies_by_name", champion_name, as_dataclass
        )

    def get_synergy_delta2(self, champion_name: str, ally_name: str) -> Optional[float]:
        """Get delta2 value for specific synergy (hybrid: API first, SQLite fallback)."""
        return self._try_api_with_fallback("get_synergy_delta2", champion_name, ally_name)

    def get_all_synergies_bulk(self) -> Dict[Tuple[str, str], float]:
        """Load all valid synergies in single query (hybrid: API first, SQLite fallback)."""
        return self._try_api_with_fallback("get_all_synergies_bulk")

    # ==================== Champion Scores ====================

    def get_champion_scores_by_name(self, champion_name: str) -> Optional[Dict[str, float]]:
        """Get champion scores by champion name (hybrid: API first, SQLite fallback)."""
        return self._try_api_with_fallback("get_champion_scores_by_name", champion_name)

    def get_all_champion_scores(self) -> List[tuple]:
        """Get all champion scores with names (hybrid: API first, SQLite fallback)."""
        return self._try_api_with_fallback("get_all_champion_scores")

    def champion_scores_table_exists(self) -> bool:
        """Check if champion_scores data exists (hybrid: API first, SQLite fallback)."""
        return self._try_api_with_fallback("champion_scores_table_exists")

    # ==================== Ban Recommendations ====================

    def get_pool_ban_recommendations(self, pool_name: str, limit: int = 5) -> List[tuple]:
        """Get pre-calculated ban recommendations (hybrid: API first, SQLite fallback)."""
        return self._try_api_with_fallback("get_pool_ban_recommendations", pool_name, limit)

    def pool_has_ban_recommendations(self, pool_name: str) -> bool:
        """Check if pool has ban recommendations (hybrid: API first, SQLite fallback)."""
        return self._try_api_with_fallback("pool_has_ban_recommendations", pool_name)
