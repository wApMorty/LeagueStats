"""champion_scores table repository (dérivée/cache, recalculée par le pipeline).

Extracted from src/db.py (dette de code, TODO.md P4) : déplacement verbatim,
aucun changement de comportement.
"""

from sqlite3 import Error
from typing import Dict, List, Optional

from ..config_constants import analysis_config


class ChampionScoresRepository:
    """CRUD et requêtes sur la table ``champion_scores``."""

    def __init__(self, db) -> None:
        self.db = db

    def init_champion_scores_table(self) -> None:
        """Create or reset champion_scores table for tier list calculations.

        One row per (champion, lane): lane=analysis_config.ALL_LANES_KEY holds
        the toutes-lanes aggregate (previous behavior, used as fallback for
        multi-lane/custom pools), plus one row per scraped lane so tier lists
        can be scoped to the lane actually played.
        """
        self.db.execute_query("DROP TABLE IF EXISTS champion_scores")
        self.db.execute_query("""CREATE TABLE champion_scores (
            id INTEGER NOT NULL,
            lane TEXT NOT NULL DEFAULT 'all',
            avg_delta2 REAL,
            variance REAL,
            coverage REAL,
            peak_impact REAL,
            volatility REAL,
            target_ratio REAL,
            PRIMARY KEY (id, lane),
            FOREIGN KEY (id) REFERENCES champions(id) ON DELETE CASCADE
        )""")

    def save_champion_scores(
        self,
        champion_id: int,
        avg_delta2: float,
        variance: float,
        coverage: float,
        peak_impact: float,
        volatility: float,
        target_ratio: float,
        lane: str = analysis_config.ALL_LANES_KEY,
    ) -> None:
        """Save or update champion scores in the database.

        lane: analysis_config.ALL_LANES_KEY (default) for the toutes-lanes
              aggregate, or one of scraping_config.LANES for a lane-scoped score.
        """
        cursor = self.db.connection.cursor()
        try:
            cursor.execute(
                """
                INSERT OR REPLACE INTO champion_scores
                (id, lane, avg_delta2, variance, coverage, peak_impact, volatility, target_ratio)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    champion_id,
                    lane,
                    avg_delta2,
                    variance,
                    coverage,
                    peak_impact,
                    volatility,
                    target_ratio,
                ),
            )
            self.db.connection.commit()
        except Error as e:
            print(f"Error saving champion scores for ID {champion_id} (lane={lane}): {e}")

    def get_champion_scores(
        self, champion_id: int, lane: str = analysis_config.ALL_LANES_KEY
    ) -> Optional[Dict[str, float]]:
        """Get champion scores by champion ID, scoped to a lane (default: all lanes)."""
        cursor = self.db.connection.cursor()
        try:
            cursor.execute(
                """
                SELECT avg_delta2, variance, coverage, peak_impact, volatility, target_ratio
                FROM champion_scores WHERE id = ? AND lane = ?
            """,
                (champion_id, lane),
            )
            result = cursor.fetchone()

            if result:
                return {
                    "avg_delta2": result[0],
                    "variance": result[1],
                    "coverage": result[2],
                    "peak_impact": result[3],
                    "volatility": result[4],
                    "target_ratio": result[5],
                }
            return None
        except Error as e:
            print(f"Error getting champion scores for ID {champion_id} (lane={lane}): {e}")
            return None

    def get_champion_scores_by_name(
        self, champion_name: str, lane: str = analysis_config.ALL_LANES_KEY
    ) -> Optional[Dict[str, float]]:
        """Get champion scores by champion name, scoped to a lane (default: all lanes)."""
        champion_id = self.db.get_champion_id(champion_name)
        if champion_id is None:
            return None
        return self.get_champion_scores(champion_id, lane=lane)

    def get_all_champion_scores(self, lane: str = analysis_config.ALL_LANES_KEY) -> List[tuple]:
        """Get all champion scores with champion names, scoped to a lane (default: all lanes)."""
        cursor = self.db.connection.cursor()
        try:
            cursor.execute(
                """
                SELECT c.name, cs.avg_delta2, cs.variance, cs.coverage,
                       cs.peak_impact, cs.volatility, cs.target_ratio
                FROM champion_scores cs
                JOIN champions c ON cs.id = c.id
                WHERE cs.lane = ?
                ORDER BY c.name
            """,
                (lane,),
            )
            return cursor.fetchall()
        except Error as e:
            print(f"Error getting all champion scores: {e}")
            return []

    def champion_scores_table_exists(self) -> bool:
        """Check if champion_scores table exists and has data."""
        cursor = self.db.connection.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM champion_scores")
            count = cursor.fetchone()[0]
            return count > 0
        except Error:
            return False
