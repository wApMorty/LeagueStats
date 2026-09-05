"""Matchups table repository.

Extracted from src/db.py (dette de code, TODO.md P4) : déplacement verbatim,
aucun changement de comportement. ``Database`` reste la façade publique et
délègue ici ; les appels vers d'autres domaines (champions, etc.) repassent
par ``self.db.<method>`` pour ne pas dupliquer la logique. Les lectures
optimisées draft (``get_champion_matchups_for_draft``,
``get_reverse_matchups_for_draft``) vivent dans ``matchups_draft.py``, séparé
pour rester sous la limite de 500 lignes.
"""

from sqlite3 import Error
from typing import Dict, List, Optional, Union

from ..analysis.aggregation import aggregate_full_rows, aggregate_pairs, weighted_delta2
from ..config_constants import analysis_config, scraping_config
from ..models import Matchup


class MatchupsRepository:
    """CRUD et requêtes sur la table ``matchups``."""

    def __init__(self, db) -> None:
        self.db = db

    def init_matchups_table(self) -> None:
        self.db.execute_query("DROP TABLE IF EXISTS matchups")
        self.db.execute_query("""CREATE TABLE matchups (
            id INTEGER PRIMARY KEY,
            champion INTEGER NOT NULL,
            enemy INTEGER NOT NULL,
            winrate REAL NOT NULL,
            delta1 REAL NOT NULL,
            delta2 REAL NOT NULL,
            pickrate REAL NOT NULL,
            games INTEGER NOT NULL,
            lane TEXT,
            FOREIGN KEY (champion) REFERENCES champions(id) ON DELETE CASCADE,
            FOREIGN KEY (enemy) REFERENCES champions(id) ON DELETE CASCADE
        )""")
        # Create indexes for performance optimization
        self.db.create_database_indexes()

    def add_matchup(
        self,
        champion: str,
        enemy: str,
        winrate: float,
        delta1: float,
        delta2: float,
        pickrate: float,
        games: int,
    ) -> None:
        champ_id = self.db.get_champion_id(champion)
        enemy_id = self.db.get_champion_id(enemy)
        if (
            champ_id is None
            or enemy_id is None
            or winrate is None
            or delta1 is None
            or delta2 is None
            or pickrate is None
            or games is None
        ):
            print(f"{champ_id}, {enemy_id}, {winrate}, {delta1}, {delta2}, {pickrate}, {games}")
            return
        cursor = self.db.connection.cursor()
        try:
            cursor.execute(
                "INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (champ_id, enemy_id, winrate, delta1, delta2, pickrate, games),
            )
            self.db.connection.commit()
            print(f"Query executed successfully : INSERT INTO matchups")
        except Error as e:
            print(f"The error '{e}' occurred")

    def get_champion_matchups(self, champion_id: int) -> List[tuple]:
        """Get matchups for a champion by Riot ID."""
        cursor = self.db.connection.cursor()
        try:
            cursor.execute(
                "SELECT * FROM matchups WHERE champion = ? AND pickrate > ?",
                (champion_id, analysis_config.MIN_PICKRATE),
            )
            # No commit needed for SELECT queries!
            result = cursor.fetchall()
            # returns (enemy_id, winrate, delta1, delta2, pickrate, games)
            return [(elem[2], elem[3], elem[4], elem[5], elem[6], elem[7]) for elem in result]
        except Error as e:
            print(f"The error '{e}' occurred")
            return []

    def get_champion_matchups_by_name(
        self, champion_name: str, as_dataclass: bool = True, lane: Optional[str] = None
    ) -> Union[List[Matchup], List[tuple]]:
        """Get matchups for a champion by name with enemy names included.

        Args:
            champion_name: Name of the champion to get matchups for
            as_dataclass: If True, return Matchup objects. If False, return tuples.
                         Default True for new code. Use False for backward compatibility.
            lane: Optional lane filter (e.g. "top"). None = toutes lanes agrégées
                  (comportement historique, inchangé).

        Returns:
            List of Matchup objects or tuples (enemy_name, winrate, delta1, delta2, pickrate, games)

        Example:
            >>> # New way (dataclass - readable attributes)
            >>> matchups = db.get_champion_matchups_by_name("Jinx")
            >>> for m in matchups:
            ...     print(f"{m.enemy_name}: {m.winrate}% WR, {m.delta2} delta2")

            >>> # Old way (tuples - for backward compatibility)
            >>> matchups = db.get_champion_matchups_by_name("Jinx", as_dataclass=False)
            >>> for m in matchups:
            ...     print(f"{m[0]}: {m[1]}% WR, {m[3]} delta2")
        """
        champ_id = self.db.get_champion_id(champion_name)
        if champ_id is None:
            return []

        cursor = self.db.connection.cursor()
        try:
            # Join avec la table champions pour obtenir les noms des ennemis
            query = """
                SELECT c.name, m.winrate, m.delta1, m.delta2, m.pickrate, m.games
                FROM matchups m
                JOIN champions c ON m.enemy = c.id
                WHERE m.champion = ? AND m.pickrate > ?
            """
            params = [champ_id, analysis_config.MIN_PICKRATE]
            if lane is not None:
                query += " AND m.lane = ?"
                params.append(lane)
            cursor.execute(query, tuple(params))
            # Agrégation multi-lane : une entrée par adversaire distinct
            # (cf. src/analysis/aggregation.py). La forme des tuples reste
            # inchangée, seules les valeurs bougent.
            rows = [
                (a.peer_name, a.winrate, a.delta1, a.delta2, a.pickrate, a.games)
                for a in aggregate_full_rows(cursor.fetchall()).values()
            ]

            # Convert to dataclasses if requested (default)
            if as_dataclass:
                return [Matchup.from_tuple(row) for row in rows]
            else:
                # Backward compatibility: return tuples
                return rows
        except Error as e:
            print(f"The error '{e}' occurred")
            return []

    def add_matchups_batch(
        self,
        matchup_data: List[tuple],
        champion_cache: Dict[str, int] = None,
        lane: Optional[str] = None,
    ) -> int:
        """
        Add multiple matchups in a single transaction for much better performance.

        Args:
            matchup_data: List of tuples (champion_name, enemy_name, winrate, delta1, delta2, pickrate, games)
            champion_cache: Optional pre-built cache of champion name->ID mappings
            lane: Optional lane tag applied to every row of the batch
                  (one batch = one champion scraped on one lane). None = legacy/default lane.

        Returns:
            Number of matchups successfully inserted
        """
        if not matchup_data:
            return 0

        # Build cache if not provided
        if champion_cache is None:
            champion_cache = self.db.build_champion_cache()

        # SPEC-03 B8: never store NULL lane (SQLite treats NULL != NULL, so
        # the unique index on (champion, enemy, lane) would not constrain it).
        lane = lane or scraping_config.DEFAULT_LANE

        try:
            cursor = self.db.connection.cursor()

            # Prepare data for batch insert
            batch_data = []
            skipped = 0

            for champion, enemy, winrate, delta1, delta2, pickrate, games in matchup_data:
                # Get IDs from cache (much faster than individual queries)
                champ_id = champion_cache.get(champion) or champion_cache.get(champion.lower())
                enemy_id = champion_cache.get(enemy) or champion_cache.get(enemy.lower())

                if (
                    champ_id
                    and enemy_id
                    and all(x is not None for x in [winrate, delta1, delta2, pickrate, games])
                ):
                    batch_data.append(
                        (champ_id, enemy_id, winrate, delta1, delta2, pickrate, games, lane)
                    )
                else:
                    skipped += 1
                    if self.db.connection.total_changes % 100 == 0:  # Occasional debug
                        print(
                            f"[DEBUG] Skipped matchup: {champion} vs {enemy} (missing data or IDs)"
                        )

            if not batch_data:
                print(f"[WARNING] No valid matchups to insert from {len(matchup_data)} provided")
                return 0

            # Single transaction with batch insert (much faster!)
            # ON CONFLICT: SPEC-03 B8 — idempotent per (champion, enemy, lane),
            # so a repeated scrape/repair run updates instead of duplicating.
            cursor.executemany(
                """
                INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games, lane)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(champion, enemy, lane) DO UPDATE SET
                    winrate=excluded.winrate, delta1=excluded.delta1, delta2=excluded.delta2,
                    pickrate=excluded.pickrate, games=excluded.games
            """,
                batch_data,
            )
            self.db.connection.commit()

            inserted = len(batch_data)
            if skipped > 0:
                print(f"[INFO] Inserted {inserted} matchups, skipped {skipped}")

            return inserted

        except Exception as e:
            try:
                self.db.connection.rollback()
            except:
                pass
            print(f"[ERROR] Batch insert failed: {e}")
            return 0

    def clear_matchups_for_champion(
        self, champion_name: str, champion_cache: Dict[str, int] = None
    ) -> bool:
        """Clear existing matchups for a champion before inserting new data."""
        try:
            if champion_cache is None:
                champ_id = self.db.get_champion_id(champion_name)
            else:
                champ_id = champion_cache.get(champion_name) or champion_cache.get(
                    champion_name.lower()
                )

            if not champ_id:
                print(f"[WARNING] Champion not found: {champion_name}")
                return False

            cursor = self.db.connection.cursor()
            cursor.execute("DELETE FROM matchups WHERE champion = ?", (champ_id,))
            deleted = cursor.rowcount

            if deleted > 0:
                print(f"[INFO] Cleared {deleted} existing matchups for {champion_name}")

            return True

        except Exception as e:
            print(f"[ERROR] Error clearing matchups for {champion_name}: {e}")
            return False

    def get_matchup_delta2(
        self, champion_name: str, enemy_name: str, lane: Optional[str] = None
    ) -> Optional[float]:
        """
        Get delta2 value for a specific matchup using direct SQL query.

        Aggregates multi-lane matchup data using weighted average by games.
        Optimized for reverse lookup approach - avoids loading all matchups.

        Args:
            champion_name: Name of our champion
            enemy_name: Name of enemy champion
            lane: Optional lane filter (e.g. "top"). None = toutes lanes agrégées
                  (comportement historique, inchangé).

        Returns:
            Weighted average delta2 value if matchup exists with sufficient data, None otherwise
        """
        try:
            cursor = self.db.connection.cursor()

            # Direct SQL join - aggregation done in Python for consistency
            query = """
                SELECT m.delta2, m.games
                FROM matchups m
                JOIN champions c1 ON m.champion = c1.id
                JOIN champions c2 ON m.enemy = c2.id
                WHERE c1.name = ? COLLATE NOCASE
                AND c2.name = ? COLLATE NOCASE
                AND m.pickrate >= ?
                AND m.games >= ?
            """
            params = [
                champion_name,
                enemy_name,
                analysis_config.MIN_PICKRATE,
                analysis_config.MIN_MATCHUP_GAMES,
            ]
            if lane is not None:
                query += " AND m.lane = ?"
                params.append(lane)
            cursor.execute(query, tuple(params))

            # Politique d'agrégation unique : SUM(delta2 * games) / SUM(games)
            # (cf. src/analysis/aggregation.py). Doit rester cohérente avec
            # get_all_matchups_bulk() — c'est l'incohérence M2 de l'audit.
            return weighted_delta2(cursor.fetchall())

        except Exception as e:
            # Always log database errors - these are unexpected and need visibility
            print(f"[ERROR] Database error getting matchup {champion_name} vs {enemy_name}: {e}")
            return None

    def get_all_matchups_bulk(self, lane: Optional[str] = None) -> dict:
        """
        Load ALL valid matchups in a single SQL query for caching.

        Returns dict mapping (champion_name, enemy_name) -> delta2 value.
        Only includes matchups meeting quality thresholds (pickrate >= 0.5%, games >= 200).

        This is much faster than calling get_matchup_delta2() repeatedly.
        Use this for bulk operations like holistic optimizer.

        Args:
            lane: Optional lane filter, appliqué avant agrégation. None = toutes
                  lanes agrégées (comportement historique, inchangé). La forme du
                  dict retourné ne change pas — cf. SPEC-03 §3/B2, option (b).

        Returns:
            Dict with keys as tuples (champion_name, enemy_name) and values as delta2 floats
        """
        try:
            cursor = self.db.connection.cursor()

            # Load all valid matchups in one query
            query = """
                SELECT c1.name, c2.name, m.delta2, m.games
                FROM matchups m
                JOIN champions c1 ON m.champion = c1.id
                JOIN champions c2 ON m.enemy = c2.id
                WHERE m.pickrate >= ?
                AND m.games >= ?
            """
            params = [analysis_config.MIN_PICKRATE, analysis_config.MIN_MATCHUP_GAMES]
            if lane is not None:
                query += " AND m.lane = ?"
                params.append(lane)
            cursor.execute(query, tuple(params))

            # Agrégation multi-lane, clés en minuscules : même politique et donc
            # mêmes valeurs que get_matchup_delta2(). Avant B1, la dernière ligne
            # SQL écrasait les précédentes (10 699 valeurs jetées en silence).
            return aggregate_pairs(cursor.fetchall())

        except Exception as e:
            print(f"[ERROR] Failed to load bulk matchups: {e}")
            return {}
