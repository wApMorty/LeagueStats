"""pool_ban_recommendations table repository (dérivée/cache par pool).

Extracted from src/db.py (dette de code, TODO.md P4) : déplacement verbatim,
aucun changement de comportement. Sans rapport avec
``src/analysis/ban_recommendations.py`` (BanRecommender, logique métier de
calcul des menaces) — ce module ne fait que du CRUD SQL sur la table.
"""

from sqlite3 import Error
from typing import List


class PoolBansRepository:
    """CRUD sur la table ``pool_ban_recommendations``."""

    def __init__(self, db) -> None:
        self.db = db

    def init_pool_ban_recommendations_table(self) -> None:
        """Create or reset pool_ban_recommendations table for pre-calculated bans."""
        self.db.execute_query("DROP TABLE IF EXISTS pool_ban_recommendations")
        self.db.execute_query("""CREATE TABLE pool_ban_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pool_name TEXT NOT NULL,
            enemy_champion TEXT NOT NULL,
            threat_score REAL NOT NULL,
            best_response_delta2 REAL NOT NULL,
            best_response_champion TEXT NOT NULL,
            matchups_count INTEGER NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(pool_name, enemy_champion)
        )""")

        # Create indexes for fast lookups
        cursor = self.db.connection.cursor()
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_pool_bans_pool ON pool_ban_recommendations(pool_name)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_pool_bans_threat ON pool_ban_recommendations(pool_name, threat_score DESC)"
        )
        self.db.connection.commit()
        print("[INFO] Created pool_ban_recommendations table with indexes")

    def save_pool_ban_recommendations(self, pool_name: str, ban_data: List[tuple]) -> int:
        """
        Save pre-calculated ban recommendations for a champion pool.

        Args:
            pool_name: Name of the champion pool
            ban_data: List of tuples (enemy_champion, threat_score, best_response_delta2,
                                      best_response_champion, matchups_count)

        Returns:
            Number of ban recommendations saved
        """
        if not ban_data:
            return 0

        try:
            cursor = self.db.connection.cursor()

            # Delete existing recommendations for this pool
            cursor.execute("DELETE FROM pool_ban_recommendations WHERE pool_name = ?", (pool_name,))

            # Insert new recommendations
            cursor.executemany(
                """
                INSERT INTO pool_ban_recommendations
                (pool_name, enemy_champion, threat_score, best_response_delta2,
                 best_response_champion, matchups_count)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                [
                    (pool_name, enemy, threat, delta2, response, count)
                    for enemy, threat, delta2, response, count in ban_data
                ],
            )

            self.db.connection.commit()
            return len(ban_data)

        except Exception as e:
            print(f"[ERROR] Failed to save ban recommendations for {pool_name}: {e}")
            try:
                self.db.connection.rollback()
            except:
                pass
            return 0

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
        cursor = self.db.connection.cursor()
        try:
            cursor.execute(
                """
                SELECT enemy_champion, threat_score, best_response_delta2,
                       best_response_champion, matchups_count
                FROM pool_ban_recommendations
                WHERE pool_name = ?
                ORDER BY threat_score DESC
                LIMIT ?
                """,
                (pool_name, limit),
            )

            return cursor.fetchall()

        except Error as e:
            print(f"[ERROR] Failed to get ban recommendations for {pool_name}: {e}")
            return []

    def pool_has_ban_recommendations(self, pool_name: str) -> bool:
        """Check if a pool has pre-calculated ban recommendations."""
        cursor = self.db.connection.cursor()
        try:
            cursor.execute(
                """
                SELECT COUNT(*) FROM pool_ban_recommendations
                WHERE pool_name = ?
                """,
                (pool_name,),
            )
            count = cursor.fetchone()[0]
            return count > 0
        except Error:
            return False

    def clear_pool_ban_recommendations(self, pool_name: str = None) -> int:
        """
        Clear ban recommendations for a pool or all pools.

        Args:
            pool_name: Pool name to clear, or None to clear all

        Returns:
            Number of recommendations deleted
        """
        cursor = self.db.connection.cursor()
        try:
            if pool_name:
                cursor.execute(
                    "DELETE FROM pool_ban_recommendations WHERE pool_name = ?", (pool_name,)
                )
            else:
                cursor.execute("DELETE FROM pool_ban_recommendations")

            deleted = cursor.rowcount
            self.db.connection.commit()
            return deleted

        except Error as e:
            print(f"[ERROR] Failed to clear ban recommendations: {e}")
            return 0
