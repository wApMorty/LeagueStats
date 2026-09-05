"""Draft-optimized matchup reads (reduced column set for hot draft-time lookups).

Extracted from src/db.py (dette de code, TODO.md P4) : déplacement verbatim,
aucun changement de comportement. Séparé de ``matchups.py`` (CRUD général)
pour rester sous la limite de 500 lignes tout en gardant les deux lectures
"draft" (colonnes réduites) ensemble, l'une étant le miroir de l'autre.
"""

from sqlite3 import Error
from typing import List, Optional, Union

from ..analysis.aggregation import aggregate_rows
from ..config_constants import analysis_config
from ..models import MatchupDraft


class MatchupsDraftRepository:
    """Lectures matchups optimisées pour le draft (4 colonnes au lieu de 6)."""

    def __init__(self, db) -> None:
        self.db = db

    def get_champion_matchups_for_draft(
        self, champion_name: str, as_dataclass: bool = True, lane: Optional[str] = None
    ) -> Union[List[MatchupDraft], List[tuple]]:
        """
        Optimized query for draft analysis - returns only the columns needed for draft calculations.

        This method returns 4 columns instead of 6 (33% reduction):
        - enemy_name (str): Enemy champion name
        - delta2 (float): Delta2 performance metric
        - pickrate (float): Matchup pickrate percentage
        - games (int): Number of games in sample

        Columns NOT included (not used in draft):
        - winrate: Only used in avg_winrate() which is never called during draft
        - delta1: Only used in legacy generate_by_delta1() tier list method

        Args:
            champion_name: Name of the champion to get matchups for
            as_dataclass: If True, return MatchupDraft objects. If False, return tuples.
                         Default True for new code. Use False for backward compatibility.

        Returns:
            List of MatchupDraft objects or tuples: [(enemy_name, delta2, pickrate, games), ...]
            Empty list if champion not found or no matchups

        Example:
            >>> # New way (dataclass - readable attributes)
            >>> matchups = db.get_champion_matchups_for_draft("Jinx")
            >>> for m in matchups:
            ...     print(f"{m.enemy_name}: {m.delta2} delta2, {m.games} games")

            >>> # Old way (tuples - for backward compatibility)
            >>> matchups = db.get_champion_matchups_for_draft("Jinx", as_dataclass=False)
            >>> for m in matchups:
            ...     print(f"{m[0]}: {m[1]} delta2, {m[3]} games")
        """
        champ_id = self.db.get_champion_id(champion_name)
        if champ_id is None:
            return []

        cursor = self.db.connection.cursor()
        try:
            # Optimized query: only 4 columns needed for draft analysis
            query = """
                SELECT c.name, m.delta2, m.pickrate, m.games
                FROM matchups m
                JOIN champions c ON m.enemy = c.id
                WHERE m.champion = ? AND m.pickrate > ?
            """
            params = [champ_id, analysis_config.MIN_PICKRATE]
            if lane is not None:
                query += " AND m.lane = ?"
                params.append(lane)
            cursor.execute(query, tuple(params))
            # Agrégation multi-lane (cf. src/analysis/aggregation.py)
            rows = [
                (a.peer_name, a.delta2, a.pickrate, a.games)
                for a in aggregate_rows(cursor.fetchall()).values()
            ]

            # Convert to dataclasses if requested (default)
            if as_dataclass:
                return [MatchupDraft.from_tuple(row) for row in rows]
            else:
                # Backward compatibility: return tuples
                return rows
        except Error as e:
            print(f"The error '{e}' occurred")
            return []

    def get_reverse_matchups_for_draft(
        self, champion_name: str, as_dataclass: bool = True, lane: Optional[str] = None
    ) -> Union[List[MatchupDraft], List[tuple]]:
        """
        Get matchups where champion is in ENEMY position (reverse lookup).

        Optimized for ban recommendations and reverse threat analysis.
        Returns champions that PICK AGAINST this champion.

        This method complements get_champion_matchups_for_draft() by inverting the perspective:
        - get_champion_matchups_for_draft("Darius"): Who does Darius face? (Darius as picker)
        - get_reverse_matchups_for_draft("Darius"): Who picks against Darius? (Darius as enemy)

        Returns 4 columns for draft analysis:
        - enemy_name (str): Champion that picks against the given champion
        - delta2 (float): Delta2 performance metric (from picker's perspective)
        - pickrate (float): Matchup pickrate percentage
        - games (int): Number of games in sample

        Args:
            champion_name: Name of the champion (in enemy position)
            as_dataclass: If True, return MatchupDraft objects. If False, return tuples.
                         Default True for new code. Use False for backward compatibility.

        Returns:
            List of MatchupDraft objects or tuples: [(picker_name, delta2, pickrate, games), ...]
            Empty list if champion not found or no matchups

        Example:
            >>> # Find who picks against Darius
            >>> matchups = db.get_reverse_matchups_for_draft("Darius")
            >>> for m in matchups:
            ...     print(f"{m.enemy_name} picks against Darius: {m.delta2} delta2")

            >>> # Tuple format for backward compatibility
            >>> matchups = db.get_reverse_matchups_for_draft("Darius", as_dataclass=False)
            >>> for picker, delta2, pickrate, games in matchups:
            ...     print(f"{picker}: {delta2} delta2, {games} games")
        """
        champ_id = self.db.get_champion_id(champion_name)
        if champ_id is None:
            return []

        cursor = self.db.connection.cursor()
        try:
            # Reverse lookup: find champions that pick against this champion
            # WHERE enemy = champ_id (champion is in enemy position)
            # JOIN on champion (the picker)
            query = """
                SELECT c.name, m.delta2, m.pickrate, m.games
                FROM matchups m
                JOIN champions c ON m.champion = c.id
                WHERE m.enemy = ? AND m.pickrate >= ? AND m.games >= ?
            """
            params = [champ_id, analysis_config.MIN_PICKRATE, analysis_config.MIN_MATCHUP_GAMES]
            if lane is not None:
                query += " AND m.lane = ?"
                params.append(lane)
            cursor.execute(query, tuple(params))
            # Agrégation multi-lane : une entrée par picker distinct
            rows = [
                (a.peer_name, a.delta2, a.pickrate, a.games)
                for a in aggregate_rows(cursor.fetchall()).values()
            ]

            # Convert to dataclasses if requested (default)
            if as_dataclass:
                # Note: We reuse MatchupDraft but enemy_name contains the "picker"
                return [MatchupDraft.from_tuple(row) for row in rows]
            else:
                # Backward compatibility: return tuples
                return rows
        except Error as e:
            print(f"The error '{e}' occurred")
            return []
