"""Database module for LeagueStats Coach API Server.

This module provides asynchronous database access using SQLAlchemy 2.0 with asyncpg driver.
Supports PostgreSQL 15+ (Neon serverless PostgreSQL).

Architecture:
    - SQLAlchemy 2.0 ORM (declarative models)
    - asyncpg driver for async PostgreSQL
    - Connection pooling via AsyncEngine
    - Session management with async_sessionmaker

Example usage:
    from .db import get_session_maker
    from sqlalchemy import select

    session_maker = get_session_maker()
    async with session_maker() as session:
        result = await session.execute(select(Champion))
        champions = result.scalars().all()
"""

from typing import AsyncGenerator, Optional
from sqlalchemy import Column, Integer, String, Float, ForeignKey, Index
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
    AsyncEngine,
)
from sqlalchemy.orm import declarative_base, relationship
from .config import settings

# Base class for all ORM models
Base = declarative_base()


# ========================================
# ORM MODELS
# ========================================


class Champion(Base):
    """Champion model (172 champions).

    Attributes:
        id: Primary key (auto-increment)
        name: Champion name (e.g., "Aatrox", "Ahri")
        lolalytics_id: LoLalytics champion identifier (lowercase, e.g., "aatrox")
    """

    __tablename__ = "champions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    lolalytics_id = Column(String(50), unique=True, nullable=False)

    # Relationships
    matchups_as_champion = relationship(
        "Matchup",
        foreign_keys="Matchup.champion_id",
        back_populates="champion",
        cascade="all, delete-orphan",
    )
    matchups_as_enemy = relationship(
        "Matchup",
        foreign_keys="Matchup.enemy_id",
        back_populates="enemy",
        cascade="all, delete-orphan",
    )
    synergies_as_champion = relationship(
        "Synergy",
        foreign_keys="Synergy.champion_id",
        back_populates="champion",
        cascade="all, delete-orphan",
    )
    synergies_as_ally = relationship(
        "Synergy",
        foreign_keys="Synergy.ally_id",
        back_populates="ally",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Champion(id={self.id}, name='{self.name}')>"


class Matchup(Base):
    """Champion matchup model (36,000+ matchups).

    Stores winrate statistics for champion vs enemy matchups.

    Attributes:
        id: Primary key (auto-increment)
        champion_id: Foreign key to Champion (the champion)
        enemy_id: Foreign key to Champion (the enemy)
        winrate: Win rate percentage (e.g., 52.5 = 52.5%)
        delta2: Delta2 score (statistical significance metric)
        games: Number of games played in this matchup
        pickrate: Pick rate percentage (e.g., 3.2 = 3.2%)
    """

    __tablename__ = "matchups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    champion_id = Column(
        Integer, ForeignKey("champions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    enemy_id = Column(
        Integer, ForeignKey("champions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    winrate = Column(Float, nullable=False)
    delta2 = Column(Float, nullable=False, index=True)  # Indexed for tier list sorting
    games = Column(Integer, nullable=False)
    pickrate = Column(Float, nullable=False)

    # Relationships
    champion = relationship(
        "Champion", foreign_keys=[champion_id], back_populates="matchups_as_champion"
    )
    enemy = relationship("Champion", foreign_keys=[enemy_id], back_populates="matchups_as_enemy")

    # Composite index for fast lookups
    # Removed unique constraint - multi-lane support (same matchup in Top, Jungle, Mid, Support)
    # TODO: Add lane column + UNIQUE(champion_id, enemy_id, lane) constraint in future
    __table_args__ = (Index("ix_matchups_champion_enemy", "champion_id", "enemy_id", unique=False),)

    def __repr__(self) -> str:
        return f"<Matchup(champion_id={self.champion_id}, enemy_id={self.enemy_id}, delta2={self.delta2})>"


class Synergy(Base):
    """Champion synergy model (~30,000 synergies).

    Stores duo synergy statistics for champion+ally combinations.

    Attributes:
        id: Primary key (auto-increment)
        champion_id: Foreign key to Champion (the main champion)
        ally_id: Foreign key to Champion (the ally teammate)
        winrate: Win rate percentage when playing together
        delta2: Delta2 score (synergy strength metric)
        games: Number of games played together
        pickrate: Pick rate percentage for this duo
    """

    __tablename__ = "synergies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    champion_id = Column(
        Integer, ForeignKey("champions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ally_id = Column(
        Integer, ForeignKey("champions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    winrate = Column(Float, nullable=False)
    delta2 = Column(Float, nullable=False, index=True)
    games = Column(Integer, nullable=False)
    pickrate = Column(Float, nullable=False)

    # Relationships
    champion = relationship(
        "Champion", foreign_keys=[champion_id], back_populates="synergies_as_champion"
    )
    ally = relationship("Champion", foreign_keys=[ally_id], back_populates="synergies_as_ally")

    # Composite index for fast lookups
    # Removed unique constraint - multi-lane support (same synergy across multiple lanes)
    # TODO: Add lane column + UNIQUE(champion_id, ally_id, lane) constraint in future
    __table_args__ = (Index("ix_synergies_champion_ally", "champion_id", "ally_id", unique=False),)

    def __repr__(self) -> str:
        return f"<Synergy(champion_id={self.champion_id}, ally_id={self.ally_id}, delta2={self.delta2})>"


# ========================================
# DATABASE ENGINE & SESSION
# ========================================

# Thread-local storage for engines (each thread/event loop gets its own engine)
import threading

_thread_local = threading.local()


def get_engine() -> AsyncEngine:
    """Get or create async database engine (thread-local).

    Each thread gets its own engine to avoid event loop conflicts.

    Returns:
        AsyncEngine configured for PostgreSQL with asyncpg driver
    """
    if not hasattr(_thread_local, "engine") or _thread_local.engine is None:
        # Read DATABASE_URL from environment first (for GitHub Actions), fallback to settings
        import os

        env_db_url = os.environ.get("DATABASE_URL")
        if env_db_url:
            # Manually convert to async format (same logic as settings.get_async_database_url())
            db_url = env_db_url
            # Remove psycopg-specific params
            if "?" in db_url:
                base_url, params = db_url.split("?", 1)
                filtered_params = [
                    p
                    for p in params.split("&")
                    if not p.startswith("sslmode=") and not p.startswith("channel_binding=")
                ]
                if filtered_params:
                    db_url = f"{base_url}?{'&'.join(filtered_params)}"
                else:
                    db_url = base_url
            # Ensure +asyncpg driver
            if "postgresql://" in db_url and "+asyncpg" not in db_url:
                db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
        else:
            # Fallback to settings (for local development with .env file)
            db_url = settings.get_async_database_url()

        _thread_local.engine = create_async_engine(
            db_url,
            echo=False,  # Set to True for SQL query debugging
            pool_size=2,  # Small pool per thread
            max_overflow=5,
            pool_pre_ping=True,  # Verify connections before using
            pool_recycle=300,  # Recycle connections after 5 minutes (daily sync use case)
        )
    return _thread_local.engine


def get_session_maker():
    """Get async session maker (creates new sessions).

    Each call creates a fresh session maker bound to the thread-local engine.

    Returns:
        async_sessionmaker configured with the thread-local engine
    """
    return async_sessionmaker(
        bind=get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )


# Session factory (creates new sessions) - lazy initialization to allow env vars to load first
# Do NOT call get_session_maker() at module level, call it when needed
AsyncSessionLocal = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection for FastAPI endpoints.

    Yields an async database session and ensures it's closed after use.

    Usage in FastAPI:
        @app.get("/api/champions")
        async def get_champions(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Champion))
            return result.scalars().all()

    Yields:
        AsyncSession: Database session
    """
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database (create all tables).

    WARNING: This is for testing only. In production, use Alembic migrations.

    Example:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    """
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database engine and cleanup resources.

    Call this on application shutdown.

    Example:
        @app.on_event("shutdown")
        async def shutdown():
            await close_db()
    """
    if hasattr(_thread_local, "engine") and _thread_local.engine is not None:
        await _thread_local.engine.dispose()
        _thread_local.engine = None


async def close_all_connections() -> None:
    """Close all database connections and dispose engine pool.

    This forces SQLAlchemy to recreate the connection pool on next query.
    Used by admin endpoint after database sync to see fresh data immediately.

    This is different from close_db() in that it's designed to be called
    mid-lifecycle to force pool refresh, not just at shutdown.
    """
    if hasattr(_thread_local, "engine") and _thread_local.engine is not None:
        await _thread_local.engine.dispose()
        _thread_local.engine = None


# ========================================
# SYNCHRONOUS DATABASE WRAPPER
# ========================================


class Database:
    """Synchronous database wrapper for analysis modules compatibility.

    This class provides a synchronous interface to the async database layer,
    allowing legacy analysis modules (src/analysis/*) to work with the server's
    async PostgreSQL database without modification.

    All methods use asyncio to execute async database operations synchronously.
    Uses a shared event loop to avoid issues with multiple asyncio.run() calls.

    Example:
        db = Database()
        champions = db.get_all_champions()
        matchups = db.get_champion_matchups_by_name("Aatrox")
    """

    def __init__(self):
        """Initialize database wrapper."""
        pass

    def _run_async(self, coro):
        """Run an async coroutine synchronously.

        This method always uses asyncio.run() in a thread pool to ensure
        isolation from any existing event loops. This is necessary because:
        1. FastAPI TestClient runs in an event loop
        2. Multiple tests share the same Database instance
        3. We need clean separation between async contexts

        Args:
            coro: Async coroutine to execute

        Returns:
            Result of the coroutine execution
        """
        import asyncio
        import concurrent.futures

        # Always run in a thread pool to isolate from existing event loops
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()

    def get_champion_id(self, name: str) -> Optional[int]:
        """Get champion ID by name.

        Args:
            name: Champion name (case-insensitive)

        Returns:
            Champion ID if found, None otherwise
        """
        from sqlalchemy import select

        async def _get():
            session_maker = get_session_maker()
            async with session_maker() as session:
                result = await session.execute(select(Champion.id).where(Champion.name.ilike(name)))
                champion = result.scalar_one_or_none()
                return champion

        return self._run_async(_get())

    def get_champion_name(self, champion_id: int) -> Optional[str]:
        """Get champion name by ID.

        Args:
            champion_id: Champion ID

        Returns:
            Champion name if found, None otherwise
        """
        from sqlalchemy import select

        async def _get():
            session_maker = get_session_maker()
            async with session_maker() as session:
                result = await session.execute(
                    select(Champion.name).where(Champion.id == champion_id)
                )
                return result.scalar_one_or_none()

        return self._run_async(_get())

    def get_champion_by_id(self, champion_id: int) -> Optional[str]:
        """Get champion name by ID (alias for get_champion_name).

        Args:
            champion_id: Champion ID

        Returns:
            Champion name if found, None otherwise
        """
        return self.get_champion_name(champion_id)

    def get_all_champions(self) -> list:
        """Get all champions as list of tuples (id, name).

        Returns:
            List of (id, name) tuples sorted by name
        """
        from sqlalchemy import select

        async def _get():
            session_maker = get_session_maker()
            async with session_maker() as session:
                result = await session.execute(
                    select(Champion.id, Champion.name).order_by(Champion.name)
                )
                return result.all()

        return self._run_async(_get())

    def get_champion_matchups_by_name(self, name: str, as_dataclass: bool = False) -> list:
        """Get matchups for a champion by name.

        Args:
            name: Champion name
            as_dataclass: If True, return Matchup dataclass objects; if False, return tuples

        Returns:
            List of tuples (enemy_name, winrate, games, delta2, pickrate, delta1) or Matchup dataclasses
            Filtered by pickrate > 0.5
        """
        from sqlalchemy import select

        async def _get():
            session_maker = get_session_maker()
            async with session_maker() as session:
                # Get champion ID first
                result = await session.execute(select(Champion.id).where(Champion.name.ilike(name)))
                champ_id = result.scalar_one_or_none()

                if champ_id is None:
                    return []

                # Get matchups with enemy names (include all fields for dataclass)
                result = await session.execute(
                    select(
                        Champion.name,
                        Matchup.winrate,
                        Matchup.games,
                        Matchup.delta2,
                        Matchup.pickrate,
                    )
                    .join(Matchup, Matchup.enemy_id == Champion.id)
                    .where(Matchup.champion_id == champ_id)
                    .where(Matchup.pickrate > 0.5)
                )
                rows = result.all()

                if as_dataclass:
                    # Import here to avoid circular dependency
                    from dataclasses import dataclass

                    @dataclass
                    class MatchupData:
                        enemy_name: str
                        winrate: float
                        games: int
                        delta2: float
                        pickrate: float
                        delta1: float = 0.0  # Optional field with default

                    return [
                        MatchupData(
                            enemy_name=row[0],
                            winrate=row[1],
                            games=row[2],
                            delta2=row[3],
                            pickrate=row[4],
                            delta1=0.0,  # Not used in current schema
                        )
                        for row in rows
                    ]
                else:
                    return rows

        return self._run_async(_get())

    def get_champion_synergies_by_name(self, name: str, as_dataclass: bool = False) -> list:
        """Get synergies for a champion by name.

        Args:
            name: Champion name
            as_dataclass: If True, return Synergy dataclass objects; if False, return tuples

        Returns:
            List of tuples (ally_name, winrate, games, delta2, pickrate, delta1) or Synergy dataclasses
            Filtered by pickrate > 0.5
        """
        from sqlalchemy import select

        async def _get():
            session_maker = get_session_maker()
            async with session_maker() as session:
                # Get champion ID first
                result = await session.execute(select(Champion.id).where(Champion.name.ilike(name)))
                champ_id = result.scalar_one_or_none()

                if champ_id is None:
                    return []

                # Get synergies with ally names (include all fields for dataclass)
                result = await session.execute(
                    select(
                        Champion.name,
                        Synergy.winrate,
                        Synergy.games,
                        Synergy.delta2,
                        Synergy.pickrate,
                    )
                    .join(Synergy, Synergy.ally_id == Champion.id)
                    .where(Synergy.champion_id == champ_id)
                    .where(Synergy.pickrate > 0.5)
                )
                rows = result.all()

                if as_dataclass:
                    # Import here to avoid circular dependency
                    from dataclasses import dataclass

                    @dataclass
                    class SynergyData:
                        ally_name: str
                        winrate: float
                        games: int
                        delta2: float
                        pickrate: float

                    return [
                        SynergyData(
                            ally_name=row[0],
                            winrate=row[1],
                            games=row[2],
                            delta2=row[3],
                            pickrate=row[4],
                        )
                        for row in rows
                    ]
                else:
                    return rows

        return self._run_async(_get())

    def get_matchup_delta2(self, champion_name: str, enemy_name: str) -> Optional[float]:
        """Get delta2 score for a specific matchup.

        Args:
            champion_name: Champion name
            enemy_name: Enemy champion name

        Returns:
            Delta2 score if matchup exists with sufficient data, None otherwise
        """
        from sqlalchemy import select, and_

        async def _get():
            session_maker = get_session_maker()
            async with session_maker() as session:
                # Get champion IDs
                result = await session.execute(
                    select(Champion.id).where(Champion.name.ilike(champion_name))
                )
                champ_id = result.scalar_one_or_none()

                result = await session.execute(
                    select(Champion.id).where(Champion.name.ilike(enemy_name))
                )
                enemy_id = result.scalar_one_or_none()

                if champ_id is None or enemy_id is None:
                    return None

                # Get matchup delta2
                result = await session.execute(
                    select(Matchup.delta2).where(
                        and_(
                            Matchup.champion_id == champ_id,
                            Matchup.enemy_id == enemy_id,
                            Matchup.pickrate >= 0.5,
                            Matchup.games >= 200,
                        )
                    )
                )
                delta2 = result.scalar_one_or_none()
                return float(delta2) if delta2 is not None else None

        return self._run_async(_get())

    def get_synergy_delta2(self, champion_name: str, ally_name: str) -> Optional[float]:
        """Get delta2 score for a specific champion-ally synergy.

        Args:
            champion_name: Champion name
            ally_name: Ally champion name

        Returns:
            Delta2 score if synergy exists with sufficient data, None otherwise
        """
        from sqlalchemy import select, and_

        async def _get():
            session_maker = get_session_maker()
            async with session_maker() as session:
                # Get champion IDs
                result = await session.execute(
                    select(Champion.id).where(Champion.name.ilike(champion_name))
                )
                champ_id = result.scalar_one_or_none()

                result = await session.execute(
                    select(Champion.id).where(Champion.name.ilike(ally_name))
                )
                ally_id = result.scalar_one_or_none()

                if champ_id is None or ally_id is None:
                    return None

                # Get synergy delta2
                result = await session.execute(
                    select(Synergy.delta2).where(
                        and_(
                            Synergy.champion_id == champ_id,
                            Synergy.ally_id == ally_id,
                            Synergy.pickrate >= 0.5,
                            Synergy.games >= 200,
                        )
                    )
                )
                delta2 = result.scalar_one_or_none()
                return float(delta2) if delta2 is not None else None

        return self._run_async(_get())

    def champion_scores_table_exists(self) -> bool:
        """Check if champion_scores table exists (not implemented).

        The server uses a different caching strategy.

        Returns:
            False - champion_scores table not used in server architecture
        """
        return False

    def get_all_champion_scores(self, pool: str = None, score_type: str = None) -> list:
        """Get cached champion scores (not implemented).

        The server computes scores on-demand rather than caching in database.

        Args:
            pool: Champion pool identifier (ignored)
            score_type: Type of score to retrieve (ignored)

        Returns:
            Empty list - caching not used in server architecture
        """
        return []

    def get_champion_scores_by_name(
        self, name: str, pool: str = None, score_type: str = None
    ) -> Optional[float]:
        """Get cached score for a specific champion (not implemented).

        The server computes scores on-demand rather than caching in database.

        Args:
            name: Champion name
            pool: Champion pool identifier (ignored)
            score_type: Type of score to retrieve (ignored)

        Returns:
            None - caching not used in server architecture
        """
        return None

    def get_all_matchups_bulk(self) -> dict:
        """Load ALL valid matchups in a single query for caching.

        Returns dict mapping (champion_name, enemy_name) -> delta2 value.
        Only includes matchups meeting quality thresholds.

        Returns:
            Dict with keys as tuples (champion_name, enemy_name) and values as delta2 floats
        """
        from sqlalchemy import select, and_, alias

        async def _get():
            session_maker = get_session_maker()
            async with session_maker() as session:
                # Create alias for enemy champion
                enemy_champion = alias(Champion, name="enemy")

                result = await session.execute(
                    select(Champion.name, enemy_champion.c.name, Matchup.delta2)
                    .select_from(Matchup)
                    .join(Champion, Champion.id == Matchup.champion_id)
                    .join(enemy_champion, enemy_champion.c.id == Matchup.enemy_id)
                    .where(and_(Matchup.pickrate >= 0.5, Matchup.games >= 200))
                )

                matchup_cache = {}
                for row in result.all():
                    champion_name, enemy_name, delta2 = row
                    # Normalize to lowercase for case-insensitive lookup
                    key = (champion_name.lower(), enemy_name.lower())
                    matchup_cache[key] = float(delta2)

                return matchup_cache

        return self._run_async(_get())

    def get_all_synergies_bulk(self) -> dict:
        """Load ALL valid synergies in a single query for caching.

        Returns dict mapping (champion_name, ally_name) -> delta2 value.
        Only includes synergies meeting quality thresholds.

        Returns:
            Dict with keys as tuples (champion_name, ally_name) and values as delta2 floats
        """
        from sqlalchemy import select, and_, alias

        async def _get():
            session_maker = get_session_maker()
            async with session_maker() as session:
                # Create alias for ally champion
                ally_champion = alias(Champion, name="ally")

                result = await session.execute(
                    select(Champion.name, ally_champion.c.name, Synergy.delta2)
                    .select_from(Synergy)
                    .join(Champion, Champion.id == Synergy.champion_id)
                    .join(ally_champion, ally_champion.c.id == Synergy.ally_id)
                    .where(and_(Synergy.pickrate >= 0.5, Synergy.games >= 200))
                )

                synergy_cache = {}
                for row in result.all():
                    champion_name, ally_name, delta2 = row
                    # Normalize to lowercase for case-insensitive lookup
                    key = (champion_name.lower(), ally_name.lower())
                    synergy_cache[key] = float(delta2)

                return synergy_cache

        return self._run_async(_get())
