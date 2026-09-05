"""Synergies table repository.

Extracted from src/db.py (dette de code, TODO.md P4) : déplacement verbatim,
aucun changement de comportement. ``Database`` reste la façade publique et
délègue ici ; les appels vers d'autres domaines (champions, etc.) repassent
par ``self.db.<method>`` pour ne pas dupliquer la logique.
"""

from sqlite3 import Error
from typing import List, Optional, Tuple, Union

from ..analysis.aggregation import aggregate_full_rows, aggregate_pairs, weighted_delta2
from ..config_constants import scraping_config, synergy_config
from ..models import Synergy


class SynergiesRepository:
    """CRUD et requêtes sur la table ``synergies``."""

    def __init__(self, db) -> None:
        self.db = db

    def init_synergies_table(self) -> None:
        """Create or reset synergies table for champion synergy data.

        Drops existing synergies table and recreates it with proper schema
        and indexes. Structure mirrors matchups table but stores synergies
        WITH allies instead of matchups AGAINST enemies.
        """
        self.db.execute_query("DROP TABLE IF EXISTS synergies")
        self.db.execute_query("""CREATE TABLE synergies (
            id INTEGER PRIMARY KEY,
            champion INTEGER NOT NULL,
            ally INTEGER NOT NULL,
            winrate REAL NOT NULL,
            delta1 REAL NOT NULL,
            delta2 REAL NOT NULL,
            pickrate REAL NOT NULL,
            games INTEGER NOT NULL,
            lane TEXT,
            FOREIGN KEY (champion) REFERENCES champions(id) ON DELETE CASCADE,
            FOREIGN KEY (ally) REFERENCES champions(id) ON DELETE CASCADE
        )""")
        # Create indexes for performance optimization
        cursor = self.db.connection.cursor()
        cursor.execute("CREATE INDEX idx_synergies_champion ON synergies(champion)")
        cursor.execute("CREATE INDEX idx_synergies_ally ON synergies(ally)")
        cursor.execute("CREATE INDEX idx_synergies_pickrate ON synergies(pickrate)")
        cursor.execute(
            "CREATE INDEX idx_synergies_champion_pickrate ON synergies(champion, pickrate)"
        )
        cursor.execute("CREATE INDEX idx_synergies_ally_pickrate ON synergies(ally, pickrate)")
        cursor.execute(
            "CREATE INDEX idx_synergies_champion_lane_pickrate ON synergies(champion, lane, pickrate)"
        )
        cursor.execute(
            "CREATE INDEX idx_synergies_ally_lane_pickrate ON synergies(ally, lane, pickrate)"
        )
        # SPEC-03 B8: uniqueness per (champion, ally, lane). init_synergies_table()
        # DROP/CREATEs the table, bypassing Alembic, so this index is created
        # here too, not only in the migration.
        cursor.execute(
            "CREATE UNIQUE INDEX idx_synergies_unique ON synergies(champion, ally, lane)"
        )

    def add_synergy(
        self,
        champion: str,
        ally: str,
        winrate: float,
        delta1: float,
        delta2: float,
        pickrate: float,
        games: int,
    ) -> None:
        """Add synergy data between champion and ally.

        Args:
            champion: Name of the champion
            ally: Name of the allied champion
            winrate: Win rate percentage with this ally (0.0-100.0)
            delta1: First performance delta metric
            delta2: Second performance delta metric
            pickrate: Pick rate percentage of this ally combination
            games: Number of games with this synergy
        """
        champ_id = self.db.get_champion_id(champion)
        ally_id = self.db.get_champion_id(ally)
        if (
            champ_id is None
            or ally_id is None
            or winrate is None
            or delta1 is None
            or delta2 is None
            or pickrate is None
            or games is None
        ):
            print(
                f"[WARNING] Invalid synergy data: {champ_id}, {ally_id}, {winrate}, {delta1}, {delta2}, {pickrate}, {games}"
            )
            return
        cursor = self.db.connection.cursor()
        try:
            cursor.execute(
                "INSERT INTO synergies (champion, ally, winrate, delta1, delta2, pickrate, games) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (champ_id, ally_id, winrate, delta1, delta2, pickrate, games),
            )
            self.db.connection.commit()
            print(f"Query executed successfully : INSERT INTO synergies")
        except Error as e:
            print(f"The error '{e}' occurred")

    def get_champion_synergies_by_name(
        self, champion_name: str, as_dataclass: bool = True, lane: Optional[str] = None
    ) -> Union[List["Synergy"], List[tuple]]:
        """Get synergies for a champion by name with ally names included.

        Args:
            champion_name: Name of the champion to get synergies for
            as_dataclass: If True, return Synergy objects. If False, return tuples.
                         Default True for new code. Use False for backward compatibility.
            lane: Optional lane filter (e.g. "top"). None = toutes lanes agrégées
                  (comportement historique, inchangé).

        Returns:
            List of Synergy objects or tuples (ally_name, winrate, delta1, delta2, pickrate, games)

        Example:
            >>> # New way (dataclass - readable attributes)
            >>> synergies = db.get_champion_synergies_by_name("Yasuo")
            >>> for s in synergies:
            ...     print(f"With {s.ally_name}: {s.winrate}% WR, {s.delta2} delta2")

            >>> # Old way (tuples - for backward compatibility)
            >>> synergies = db.get_champion_synergies_by_name("Yasuo", as_dataclass=False)
            >>> for s in synergies:
            ...     print(f"With {s[0]}: {s[1]}% WR, {s[3]} delta2")
        """
        champ_id = self.db.get_champion_id(champion_name)
        if champ_id is None:
            return []

        cursor = self.db.connection.cursor()
        try:
            # Join avec la table champions pour obtenir les noms des alliés
            query = """
                SELECT c.name, s.winrate, s.delta1, s.delta2, s.pickrate, s.games
                FROM synergies s
                JOIN champions c ON s.ally = c.id
                WHERE s.champion = ? AND s.pickrate > ?
            """
            params = [champ_id, synergy_config.MIN_SYNERGY_PICKRATE]
            if lane is not None:
                query += " AND s.lane = ?"
                params.append(lane)
            cursor.execute(query, tuple(params))
            # Agrégation multi-lane : une entrée par allié distinct
            rows = [
                (a.peer_name, a.winrate, a.delta1, a.delta2, a.pickrate, a.games)
                for a in aggregate_full_rows(cursor.fetchall()).values()
            ]

            # Convert to dataclasses if requested (default)
            if as_dataclass:
                return [Synergy.from_tuple(row) for row in rows]
            else:
                # Backward compatibility: return tuples
                return rows

        except Error as e:
            print(f"The error '{e}' occurred")
            return []

    def add_synergies_batch(
        self,
        synergies: List[Tuple[str, str, float, float, float, float, int]],
        lane: Optional[str] = None,
    ) -> None:
        """Batch insert synergies for performance.

        Args:
            synergies: List of tuples (champion, ally, winrate, delta1, delta2, pickrate, games)
            lane: Optional lane tag applied to every row of the batch
                  (one batch = one champion scraped on one lane). None = legacy/default lane.
        """
        # SPEC-03 B8: never store NULL lane (SQLite treats NULL != NULL, so
        # the unique index on (champion, ally, lane) would not constrain it).
        lane = lane or scraping_config.DEFAULT_LANE

        cursor = self.db.connection.cursor()
        try:
            # Convert champion/ally names to IDs
            synergy_data = []
            for champion, ally, winrate, delta1, delta2, pickrate, games in synergies:
                champ_id = self.db.get_champion_id(champion)
                ally_id = self.db.get_champion_id(ally)
                if champ_id and ally_id:
                    synergy_data.append(
                        (champ_id, ally_id, winrate, delta1, delta2, pickrate, games, lane)
                    )

            # Batch insert. ON CONFLICT: SPEC-03 B8 — idempotent per
            # (champion, ally, lane), so a repeated scrape/repair run updates
            # instead of duplicating.
            cursor.executemany(
                """
                INSERT INTO synergies (champion, ally, winrate, delta1, delta2, pickrate, games, lane)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(champion, ally, lane) DO UPDATE SET
                    winrate=excluded.winrate, delta1=excluded.delta1, delta2=excluded.delta2,
                    pickrate=excluded.pickrate, games=excluded.games
                """,
                synergy_data,
            )
            self.db.connection.commit()
            print(f"Batch insert successful: {len(synergy_data)} synergies added")
        except Error as e:
            print(f"The error '{e}' occurred during batch synergy insert")

    def clear_synergies_for_champion(self, champion_name: str) -> None:
        """Clear all synergies for a specific champion.

        Used before re-parsing champion synergies to avoid duplicates.

        Args:
            champion_name: Name of the champion to clear synergies for
        """
        champ_id = self.db.get_champion_id(champion_name)
        if champ_id is None:
            print(f"[WARNING] Champion '{champion_name}' not found, cannot clear synergies")
            return

        cursor = self.db.connection.cursor()
        try:
            cursor.execute("DELETE FROM synergies WHERE champion = ?", (champ_id,))
            self.db.connection.commit()
            deleted = cursor.rowcount
            print(f"Deleted {deleted} synergies for {champion_name}")
        except Error as e:
            print(f"The error '{e}' occurred")

    def get_synergy_delta2(
        self, champion_name: str, ally_name: str, lane: Optional[str] = None
    ) -> Optional[float]:
        """Get delta2 value for a specific champion-ally synergy.

        Args:
            champion_name: Name of the champion
            ally_name: Name of the allied champion
            lane: Optional lane filter (e.g. "top"). None = toutes lanes agrégées
                  (comportement historique, inchangé).

        Returns:
            delta2 value if synergy exists, None otherwise
        """
        champ_id = self.db.get_champion_id(champion_name)
        ally_id = self.db.get_champion_id(ally_name)

        if champ_id is None or ally_id is None:
            return None

        try:
            cursor = self.db.connection.cursor()
            query = """
                SELECT delta2, games
                FROM synergies
                WHERE champion = ? AND ally = ?
                AND pickrate >= ?
                AND games >= ?
            """
            params = [
                champ_id,
                ally_id,
                synergy_config.MIN_SYNERGY_PICKRATE,
                synergy_config.MIN_SYNERGY_GAMES,
            ]
            if lane is not None:
                query += " AND lane = ?"
                params.append(lane)
            cursor.execute(query, tuple(params))

            # Agrégation multi-lane pondérée par games, comme pour les matchups
            # (cf. src/analysis/aggregation.py). Avant B1, fetchone() renvoyait
            # une lane arbitraire.
            return weighted_delta2(cursor.fetchall())

        except Exception as e:
            print(f"[ERROR] Database error getting synergy {champion_name} with {ally_name}: {e}")
            return None

    def get_all_synergies_bulk(self, lane: Optional[str] = None) -> dict:
        """Load ALL valid synergies in a single SQL query for caching.

        Returns dict mapping (champion_name, ally_name) -> delta2 value.
        Only includes synergies meeting quality thresholds (pickrate >= 0.5%, games >= 200).

        This is much faster than calling get_synergy_delta2() repeatedly.
        Use this for bulk operations like draft optimization.

        Args:
            lane: Optional lane filter, appliqué avant agrégation. None = toutes
                  lanes agrégées (comportement historique, inchangé).

        Returns:
            Dict with keys as tuples (champion_name, ally_name) and values as delta2 floats
        """
        try:
            cursor = self.db.connection.cursor()

            # Load all valid synergies in one query
            query = """
                SELECT c1.name, c2.name, s.delta2, s.games
                FROM synergies s
                JOIN champions c1 ON s.champion = c1.id
                JOIN champions c2 ON s.ally = c2.id
                WHERE s.pickrate >= ?
                AND s.games >= ?
            """
            params = [synergy_config.MIN_SYNERGY_PICKRATE, synergy_config.MIN_SYNERGY_GAMES]
            if lane is not None:
                query += " AND s.lane = ?"
                params.append(lane)
            cursor.execute(query, tuple(params))

            # Agrégation multi-lane, clés en minuscules : mêmes valeurs que
            # get_synergy_delta2().
            return aggregate_pairs(cursor.fetchall())

        except Exception as e:
            print(f"[ERROR] Failed to load bulk synergies: {e}")
            return {}
