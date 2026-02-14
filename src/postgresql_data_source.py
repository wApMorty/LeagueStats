"""PostgreSQL Data Source implementation - Adapter for server/src/db.py Database class.

This module provides a READ-ONLY adapter that wraps the server's Database class
to conform to the DataSource interface. It delegates all read operations to the
underlying Database instance (which uses async SQLAlchemy + PostgreSQL).

Design Pattern: Adapter Pattern (Object Adapter)
- Wraps server.src.db.Database instance
- Pure delegation (no business logic)
- READ-ONLY: All save_* methods raise NotImplementedError
- Connection string deobfuscated from credentials.py at runtime

Architecture Note:
    The Database class (server/src/db.py) provides a synchronous wrapper around
    the async PostgreSQL database. It uses asyncio.run() internally to execute
    async queries synchronously, making it compatible with the DataSource interface.

Author: @pj35
Created: 2026-02-11
Sprint: 2 - PostgreSQL Integration (Adapter Pattern Implementation)
"""

import os
from typing import List, Optional, Dict, Union, Tuple

from .data_source import DataSource
from .credentials import deobfuscate, OBFUSCATED_READONLY_CONNECTION_STRING
from server.src.db import Database


class PostgreSQLDataSource(DataSource):
    """
    READ-ONLY adapter for PostgreSQL database access via server Database class.

    This adapter wraps the server's Database class (server/src/db.py) to conform
    to the DataSource interface. All read operations are delegated to the underlying
    Database instance. Write operations (save_*) raise NotImplementedError to enforce
    read-only semantics.

    The PostgreSQL connection string is deobfuscated from credentials.py at runtime
    to avoid exposing credentials in plaintext within the distributed .exe file.

    Attributes:
        _db: Underlying Database instance (private, implementation detail)

    Example:
        >>> data_source = PostgreSQLDataSource()
        >>> data_source.connect()
        >>> matchups = data_source.get_champion_matchups_by_name("Jinx")
        >>> data_source.close()

    Security Note:
        The PostgreSQL user has READ-ONLY permissions (SELECT only) on the database.
        Even if credentials are extracted, write operations are prevented at the
        database level.
    """

    def __init__(self) -> None:
        """
        Initialize PostgreSQL data source with deobfuscated connection string.

        The connection string is deobfuscated from credentials.OBFUSCATED_READONLY_CONNECTION_STRING
        at runtime using ROT13 + Base64 decoding, then set as DATABASE_URL environment variable
        for the Database class to use.
        """
        # Deobfuscate connection string (ROT13 + Base64 decode)
        connection_string = deobfuscate(OBFUSCATED_READONLY_CONNECTION_STRING)

        # Set DATABASE_URL environment variable for Database class
        # Database class reads this via get_session_maker() in server/src/db.py
        os.environ["DATABASE_URL"] = connection_string

        # Initialize Database class (from server/src/db.py)
        # Database provides synchronous wrapper around async SQLAlchemy
        self._db = Database()

    # ==================== Connection Management ====================

    def connect(self) -> None:
        """
        Establish connection to PostgreSQL database.

        Note:
            The Database class (server/src/db.py) manages connections internally
            via SQLAlchemy connection pooling. This method is a no-op for compatibility
            with the DataSource interface.
        """
        # Database class manages connections internally (SQLAlchemy pooling)
        # No explicit connect() needed
        pass

    def close(self) -> None:
        """
        Close PostgreSQL database connection.

        Note:
            The Database class (server/src/db.py) manages connections internally
            via SQLAlchemy connection pooling. This method is a no-op for compatibility
            with the DataSource interface.
        """
        # Database class manages connections internally (SQLAlchemy pooling)
        # No explicit close() needed
        pass

    # ==================== Champion Queries ====================

    def get_champion_id(self, champion: str) -> Optional[int]:
        """Get champion ID by name (delegates to Database)."""
        return self._db.get_champion_id(champion)

    def get_champion_by_id(self, id: int) -> Optional[str]:
        """Get champion name by ID (delegates to Database)."""
        return self._db.get_champion_by_id(id)

    def get_all_champion_names(self) -> Dict[int, str]:
        """
        Get mapping of all champion IDs to names.

        Note:
            Database.get_all_champions() returns List[(id, name)].
            This method converts it to Dict[id -> name] for interface compatibility.
        """
        # Database.get_all_champions() returns List[(id, name)]
        # Convert to Dict[id -> name]
        champions = self._db.get_all_champions()
        return {champ_id: name for champ_id, name in champions}

    def build_champion_cache(self) -> Dict[str, int]:
        """
        Build cache of champion name -> ID mappings.

        Note:
            Database.get_all_champions() returns List[(id, name)].
            This method converts it to Dict[name -> id] with lowercase variants
            for case-insensitive lookups.
        """
        # Database.get_all_champions() returns List[(id, name)]
        # Convert to Dict[name -> id] with lowercase variants
        champions = self._db.get_all_champions()
        cache = {}
        for champ_id, name in champions:
            cache[name] = champ_id  # Exact case
            cache[name.lower()] = champ_id  # Lowercase variant
        return cache

    # ==================== Matchup Queries ====================

    def get_champion_matchups_by_name(
        self, champion_name: str, as_dataclass: bool = True
    ) -> Union[List, List[tuple]]:
        """Get matchups for a champion by name (delegates to Database)."""
        return self._db.get_champion_matchups_by_name(champion_name, as_dataclass)

    def get_champion_matchups_for_draft(
        self, champion_name: str, as_dataclass: bool = True
    ) -> Union[List, List[tuple]]:
        """
        Get optimized matchups for draft analysis.

        Note:
            This method is NOT implemented in Database class (server/src/db.py).
            Falls back to get_champion_matchups_by_name() and filters columns manually.
        """
        # Database does not implement get_champion_matchups_for_draft()
        # Fall back to full matchup query and filter columns
        matchups = self._db.get_champion_matchups_by_name(champion_name, as_dataclass=False)

        if as_dataclass:
            # Import MatchupDraft dataclass
            from .models import MatchupDraft

            # Database returns: (enemy_name, winrate, games, delta2, pickrate)
            # MatchupDraft needs: (enemy_name, delta2, pickrate, games)
            return [
                MatchupDraft(
                    enemy_name=row[0],  # enemy_name
                    delta2=row[3],  # delta2
                    pickrate=row[4],  # pickrate
                    games=row[2],  # games
                )
                for row in matchups
            ]
        else:
            # Return tuples: (enemy_name, delta2, pickrate, games)
            return [(row[0], row[3], row[4], row[2]) for row in matchups]

    def get_reverse_matchups_for_draft(
        self, champion_name: str, as_dataclass: bool = True
    ) -> Union[List, List[tuple]]:
        """
        Get matchups where champion is in ENEMY position (reverse lookup).

        Optimized for ban recommendations and reverse threat analysis.
        Returns champions that PICK AGAINST this champion.

        Note:
            This method is NOT implemented in Database class (server/src/db.py).
            Implements SQL query directly using asyncio.

        Args:
            champion_name: Name of the champion (in enemy position)
            as_dataclass: If True, return MatchupDraft objects. If False, return tuples.

        Returns:
            List of MatchupDraft objects or tuples: [(picker_name, delta2, pickrate, games), ...]
        """
        import asyncio
        from sqlalchemy import select
        from server.src.db import get_session_maker, Champion, Matchup

        async def _get_reverse_matchups():
            session_maker = get_session_maker()
            async with session_maker() as session:
                # Get champion ID first
                result = await session.execute(
                    select(Champion.id).where(Champion.name.ilike(champion_name))
                )
                champ_id = result.scalar_one_or_none()

                if champ_id is None:
                    return []

                # Reverse lookup: find champions that pick against this champion
                # WHERE enemy_id = champ_id (champion is in enemy position)
                # JOIN on champion (the picker)
                result = await session.execute(
                    select(
                        Champion.name,  # picker name
                        Matchup.delta2,
                        Matchup.pickrate,
                        Matchup.games,
                    )
                    .join(Matchup, Matchup.champion_id == Champion.id)
                    .where(Matchup.enemy_id == champ_id)
                    .where(Matchup.pickrate >= 0.5)
                    .where(Matchup.games >= 200)
                )
                return result.all()

        # Run async query synchronously
        rows = asyncio.run(_get_reverse_matchups())

        if as_dataclass:
            # Import MatchupDraft dataclass
            from .models import MatchupDraft

            # Note: In reverse matchups, "enemy_name" field contains the picker
            return [
                MatchupDraft(
                    enemy_name=row[0],  # picker_name (champion picking against us)
                    delta2=row[1],  # delta2
                    pickrate=row[2],  # pickrate
                    games=row[3],  # games
                )
                for row in rows
            ]
        else:
            # Return tuples: (picker_name, delta2, pickrate, games)
            return [(row[0], row[1], row[2], row[3]) for row in rows]

    def get_matchup_delta2(self, champion_name: str, enemy_name: str) -> Optional[float]:
        """Get delta2 value for specific matchup (delegates to Database)."""
        return self._db.get_matchup_delta2(champion_name, enemy_name)

    def get_all_matchups_bulk(self) -> Dict[Tuple[str, str], float]:
        """Load all valid matchups in single query (delegates to Database)."""
        return self._db.get_all_matchups_bulk()

    def get_champion_base_winrate(self, champion_name: str) -> float:
        """
        Calculate champion base winrate.

        Note:
            This method is NOT implemented in Database class (server/src/db.py).
            Returns default 50.0 as fallback.
        """
        # Database does not implement get_champion_base_winrate()
        # Return default 50.0 (neutral winrate)
        return 50.0

    # ==================== Synergy Queries ====================

    def get_champion_synergies_by_name(
        self, champion_name: str, as_dataclass: bool = True
    ) -> Union[List, List[tuple]]:
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
        """
        Get champion scores by champion name.

        Note:
            Database class does not implement champion_scores table caching.
            Returns None (scores computed on-demand in server architecture).
        """
        # Database does not implement champion_scores caching
        return self._db.get_champion_scores_by_name(champion_name)

    def get_all_champion_scores(self) -> List[tuple]:
        """
        Get all champion scores with names.

        Note:
            Database class does not implement champion_scores table caching.
            Returns empty list (scores computed on-demand in server architecture).
        """
        # Database does not implement champion_scores caching
        return self._db.get_all_champion_scores()

    def champion_scores_table_exists(self) -> bool:
        """
        Check if champion_scores table exists and has data.

        Note:
            Database class does not implement champion_scores table.
            Returns False (server uses on-demand computation).
        """
        # Database does not implement champion_scores table
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
        """
        Save or update champion scores in the database.

        Raises:
            NotImplementedError: PostgreSQLDataSource is READ-ONLY.
        """
        raise NotImplementedError(
            "PostgreSQLDataSource is READ-ONLY. Cannot save champion scores to PostgreSQL."
        )

    # ==================== Ban Recommendations ====================

    def get_pool_ban_recommendations(self, pool_name: str, limit: int = 5) -> List[tuple]:
        """
        Get pre-calculated ban recommendations for a champion pool.

        Note:
            Database class does not implement ban_recommendations table.
            Returns empty list (not supported in server architecture).
        """
        # Database does not implement ban_recommendations table
        # Return empty list
        return []

    def pool_has_ban_recommendations(self, pool_name: str) -> bool:
        """
        Check if a pool has pre-calculated ban recommendations.

        Note:
            Database class does not implement ban_recommendations table.
            Returns False (not supported in server architecture).
        """
        # Database does not implement ban_recommendations table
        return False

    def save_pool_ban_recommendations(self, pool_name: str, ban_data: List[tuple]) -> int:
        """
        Save pre-calculated ban recommendations for a champion pool.

        Raises:
            NotImplementedError: PostgreSQLDataSource is READ-ONLY.
        """
        raise NotImplementedError(
            "PostgreSQLDataSource is READ-ONLY. Cannot save ban recommendations to PostgreSQL."
        )
