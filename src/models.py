"""
Data models for League of Legends champion statistics.

This module provides immutable dataclasses to replace obscure tuple indexing
throughout the codebase. Instead of m[3] or m[5], use m.delta2 or m.games.

Key Features:
- Immutable (frozen=True) for thread-safe caching
- Type-safe with comprehensive validation
- Factory methods from database tuples
- Serialization support for JSON/dict conversion

Author: @pj35
Created: 2025-12-28
Sprint: 2 - Tâche #14 (SQLAlchemy ORM Migration - Phase 1)
"""

from dataclasses import dataclass, asdict
from typing import Tuple, Dict, Any


@dataclass(frozen=True)
class Matchup:
    """Champion matchup with full statistics.

    Represents a single matchup between a champion and an enemy champion,
    including win rate, performance deltas, pick rate, and game count.

    Attributes:
        enemy_name: Name of the enemy champion
        winrate: Win rate percentage (0.0-100.0)
        delta1: First performance delta metric
        delta2: Second performance delta metric
        pickrate: Pick rate percentage (0.0-100.0)
        games: Number of games in this matchup

    Example:
        >>> matchup = Matchup("Zed", 52.5, 150.0, 200.0, 12.5, 1000)
        >>> print(f"Against {matchup.enemy_name}: {matchup.winrate}% WR")
        Against Zed: 52.5% WR
    """

    enemy_name: str
    winrate: float
    delta1: float
    delta2: float
    pickrate: float
    games: int

    def __post_init__(self):
        """Validate data integrity on creation.

        Raises:
            ValueError: If any field contains invalid data
        """
        if not isinstance(self.enemy_name, str) or not self.enemy_name.strip():
            raise ValueError(
                f"Invalid enemy_name: must be non-empty string, got {self.enemy_name!r}"
            )

        if not 0.0 <= self.winrate <= 100.0:
            raise ValueError(f"Invalid winrate: must be 0-100, got {self.winrate}")

        # delta1 and delta2 can be negative (performance metrics)
        if not isinstance(self.delta1, (int, float)):
            raise ValueError(f"Invalid delta1: must be numeric, got {type(self.delta1)}")

        if not isinstance(self.delta2, (int, float)):
            raise ValueError(f"Invalid delta2: must be numeric, got {type(self.delta2)}")

        if not 0.0 <= self.pickrate <= 100.0:
            raise ValueError(f"Invalid pickrate: must be 0-100, got {self.pickrate}")

        if not isinstance(self.games, int) or self.games < 0:
            raise ValueError(f"Invalid games: must be non-negative integer, got {self.games}")

    @classmethod
    def from_tuple(cls, data: Tuple) -> "Matchup":
        """Create Matchup from database tuple.

        Args:
            data: 6-element tuple (enemy_name, winrate, delta1, delta2, pickrate, games)

        Returns:
            Matchup instance

        Raises:
            ValueError: If tuple length is not 6

        Example:
            >>> row = cursor.fetchone()  # ('Zed', 52.5, 150.0, 200.0, 12.5, 1000)
            >>> matchup = Matchup.from_tuple(row)
        """
        if len(data) != 6:
            raise ValueError(f"Expected 6-element tuple for Matchup, got {len(data)}: {data!r}")
        return cls(*data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary with all fields

        Example:
            >>> matchup.to_dict()
            {'enemy_name': 'Zed', 'winrate': 52.5, ...}
        """
        return asdict(self)


@dataclass(frozen=True)
class Synergy:
    """Champion synergy with ally statistics.

    Represents synergy between a champion and an ally champion,
    including win rate, performance deltas, pick rate, and game count.
    Structure identical to Matchup but semantic difference: synergies are
    WITH allies (positive relationship), matchups are AGAINST enemies.

    Attributes:
        ally_name: Name of the allied champion
        winrate: Win rate percentage when playing with this ally (0.0-100.0)
        delta1: First performance delta metric
        delta2: Second performance delta metric
        pickrate: Pick rate percentage of this ally combination (0.0-100.0)
        games: Number of games with this synergy

    Example:
        >>> synergy = Synergy("Malphite", 55.0, 180.0, 220.0, 15.0, 1200)
        >>> print(f"With {synergy.ally_name}: {synergy.winrate}% WR")
        With Malphite: 55.0% WR
    """

    ally_name: str
    winrate: float
    delta1: float
    delta2: float
    pickrate: float
    games: int

    def __post_init__(self):
        """Validate data integrity on creation.

        Raises:
            ValueError: If any field contains invalid data
        """
        if not isinstance(self.ally_name, str) or not self.ally_name.strip():
            raise ValueError(f"Invalid ally_name: must be non-empty string, got {self.ally_name!r}")

        if not 0.0 <= self.winrate <= 100.0:
            raise ValueError(f"Invalid winrate: must be 0-100, got {self.winrate}")

        # delta1 and delta2 can be negative (performance metrics)
        if not isinstance(self.delta1, (int, float)):
            raise ValueError(f"Invalid delta1: must be numeric, got {type(self.delta1)}")

        if not isinstance(self.delta2, (int, float)):
            raise ValueError(f"Invalid delta2: must be numeric, got {type(self.delta2)}")

        if not 0.0 <= self.pickrate <= 100.0:
            raise ValueError(f"Invalid pickrate: must be 0-100, got {self.pickrate}")

        if not isinstance(self.games, int) or self.games < 0:
            raise ValueError(f"Invalid games: must be non-negative integer, got {self.games}")

    @classmethod
    def from_tuple(cls, data: Tuple) -> "Synergy":
        """Create Synergy from database tuple.

        Args:
            data: 6-element tuple (ally_name, winrate, delta1, delta2, pickrate, games)

        Returns:
            Synergy instance

        Raises:
            ValueError: If tuple length is not 6

        Example:
            >>> row = cursor.fetchone()  # ('Malphite', 55.0, 180.0, 220.0, 15.0, 1200)
            >>> synergy = Synergy.from_tuple(row)
        """
        if len(data) != 6:
            raise ValueError(f"Expected 6-element tuple for Synergy, got {len(data)}: {data!r}")
        return cls(*data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary with all fields

        Example:
            >>> synergy.to_dict()
            {'ally_name': 'Malphite', 'winrate': 55.0, ...}
        """
        return asdict(self)


@dataclass(frozen=True)
class MatchupDraft:
    """Simplified matchup for draft recommendations.

    Lightweight version of Matchup with only essential draft statistics.
    Used in draft monitoring and real-time recommendations. Optimized query
    returns only 4 columns instead of 6 (33% reduction).

    Database query: SELECT c.name, m.delta2, m.pickrate, m.games

    Attributes:
        enemy_name: Name of the enemy champion
        delta2: Performance delta2 metric
        pickrate: Pick rate percentage (0.0-100.0)
        games: Number of games in this matchup

    Example:
        >>> draft = MatchupDraft("Yasuo", -50.0, 12.5, 500)
        >>> if draft.delta2 < 0:
        ...     print(f"Bad matchup vs {draft.enemy_name}")
    """

    enemy_name: str
    delta2: float
    pickrate: float
    games: int

    def __post_init__(self):
        """Validate data integrity on creation.

        Raises:
            ValueError: If any field contains invalid data
        """
        if not isinstance(self.enemy_name, str) or not self.enemy_name.strip():
            raise ValueError(
                f"Invalid enemy_name: must be non-empty string, got {self.enemy_name!r}"
            )

        if not isinstance(self.delta2, (int, float)):
            raise ValueError(f"Invalid delta2: must be numeric, got {type(self.delta2)}")

        if not 0.0 <= self.pickrate <= 100.0:
            raise ValueError(f"Invalid pickrate: must be 0-100, got {self.pickrate}")

        if not isinstance(self.games, int) or self.games < 0:
            raise ValueError(f"Invalid games: must be non-negative integer, got {self.games}")

    @classmethod
    def from_tuple(cls, data: Tuple) -> "MatchupDraft":
        """Create MatchupDraft from database tuple.

        Args:
            data: 4-element tuple (enemy_name, delta2, pickrate, games)

        Returns:
            MatchupDraft instance

        Raises:
            ValueError: If tuple length is not 4

        Example:
            >>> row = cursor.fetchone()  # ('Yasuo', -50.0, 12.5, 500)
            >>> draft = MatchupDraft.from_tuple(row)
        """
        if len(data) != 4:
            raise ValueError(
                f"Expected 4-element tuple for MatchupDraft, got {len(data)}: {data!r}"
            )
        return cls(*data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary with all fields

        Example:
            >>> draft.to_dict()
            {'enemy_name': 'Yasuo', 'delta2': -50.0, 'pickrate': 12.5, 'games': 500}
        """
        return asdict(self)

    def to_matchup(self, winrate: float = 50.0, delta1: float = 0.0) -> "Matchup":
        """Convert MatchupDraft to full Matchup with default values.

        Used when draft format (4 columns) needs to be converted to standard
        format (6 columns) for compatibility with scoring methods.

        Args:
            winrate: Win rate to use (default: 50.0 = neutral)
            delta1: Delta1 to use (default: 0.0 = neutral)

        Returns:
            Matchup instance with filled fields

        Example:
            >>> draft = MatchupDraft("Yasuo", -50.0, 12.5, 500)
            >>> matchup = draft.to_matchup()
            >>> matchup.winrate  # 50.0 (default)
            >>> matchup.delta2   # -50.0 (from draft)
        """
        return Matchup(
            enemy_name=self.enemy_name,
            winrate=winrate,
            delta1=delta1,
            delta2=self.delta2,
            pickrate=self.pickrate,
            games=self.games,
        )


@dataclass(frozen=True)
class ChampionScore:
    """Champion with calculated score.

    Represents a champion's overall performance score, used in tier lists
    and optimization algorithms.

    Attributes:
        name: Champion name
        score: Calculated performance score (can be positive or negative)

    Example:
        >>> champ = ChampionScore("Jinx", 875.5)
        >>> print(f"{champ.name}: {champ.score:.1f} points")
        Jinx: 875.5 points
    """

    name: str
    score: float

    def __post_init__(self):
        """Validate data integrity on creation.

        Raises:
            ValueError: If any field contains invalid data
        """
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError(f"Invalid name: must be non-empty string, got {self.name!r}")

        if not isinstance(self.score, (int, float)):
            raise ValueError(f"Invalid score: must be numeric, got {type(self.score)}")

    @classmethod
    def from_tuple(cls, data: Tuple) -> "ChampionScore":
        """Create ChampionScore from tuple.

        Args:
            data: 2-element tuple (name, score)

        Returns:
            ChampionScore instance

        Raises:
            ValueError: If tuple length is not 2

        Example:
            >>> result = ("Jinx", 875.5)
            >>> champ = ChampionScore.from_tuple(result)
        """
        if len(data) != 2:
            raise ValueError(
                f"Expected 2-element tuple for ChampionScore, got {len(data)}: {data!r}"
            )
        return cls(*data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary with all fields

        Example:
            >>> champ.to_dict()
            {'name': 'Jinx', 'score': 875.5}
        """
        return asdict(self)
