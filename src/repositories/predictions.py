"""predictions table repository (SPEC-05 B7 — calibration du modèle log-odds).

Extracted from src/db.py (dette de code, TODO.md P4) : déplacement verbatim,
aucun changement de comportement. Table créée par
alembic/versions/2551bbcc9eb8_add_predictions_table.py.
"""

from typing import Dict, List, Optional


class PredictionsRepository:
    """CRUD sur la table ``predictions``."""

    def __init__(self, db) -> None:
        self.db = db

    def insert_prediction(
        self,
        ally_champions: List[int],
        enemy_champions: List[int],
        ally_lanes: Optional[Dict[int, str]],
        predicted_probability: float,
        model_version: str,
    ) -> Optional[int]:
        """Insert a prediction row (outcome NULL). Returns the new row id, or None on failure.

        Args:
            ally_champions: Riot champion IDs on our team.
            enemy_champions: Riot champion IDs on the enemy team.
            ally_lanes: Optional championId -> inferred lane (SPEC-04), stored
                as a CSV aligned with `ally_champions` (empty string per
                champion whose lane is unknown). None stores NULL.
            predicted_probability: Our team's predicted win probability, in [0, 1].
            model_version: analysis_config.MODEL_VERSION at prediction time.

        Returns:
            The new row's id, or None if the insert failed (caller logs and
            moves on — this must never block the draft, see DraftMonitor).
        """
        ally_csv = ",".join(str(champ_id) for champ_id in ally_champions)
        enemy_csv = ",".join(str(champ_id) for champ_id in enemy_champions)
        lanes_csv = (
            ",".join(ally_lanes.get(champ_id, "") for champ_id in ally_champions)
            if ally_lanes
            else None
        )

        try:
            cursor = self.db.connection.cursor()
            cursor.execute(
                """
                INSERT INTO predictions
                (created_utc, ally_champions, enemy_champions, ally_lanes,
                 predicted_probability, model_version, outcome)
                VALUES (datetime('now'), ?, ?, ?, ?, ?, NULL)
                """,
                (ally_csv, enemy_csv, lanes_csv, predicted_probability, model_version),
            )
            self.db.connection.commit()
            return cursor.lastrowid

        except Exception as e:
            print(f"[ERROR] Failed to insert prediction: {e}")
            try:
                self.db.connection.rollback()
            except Exception:
                pass
            return None

    def update_prediction_outcome(self, prediction_id: int, outcome: int) -> bool:
        """Set outcome (1=win, 0=loss) on an existing prediction row.

        Args:
            prediction_id: Row id returned by insert_prediction.
            outcome: 1 for a win, 0 for a loss.

        Returns:
            True if a row was updated, False otherwise (including on failure).
        """
        try:
            cursor = self.db.connection.cursor()
            cursor.execute(
                "UPDATE predictions SET outcome = ? WHERE id = ?",
                (outcome, prediction_id),
            )
            self.db.connection.commit()
            return cursor.rowcount > 0

        except Exception as e:
            print(f"[ERROR] Failed to update prediction outcome: {e}")
            try:
                self.db.connection.rollback()
            except Exception:
                pass
            return False

    def get_latest_prediction_id(self) -> Optional[int]:
        """Most recent prediction row without an outcome yet, for the manual 'outcome' command."""
        try:
            cursor = self.db.connection.cursor()
            cursor.execute(
                "SELECT id FROM predictions WHERE outcome IS NULL ORDER BY id DESC LIMIT 1"
            )
            row = cursor.fetchone()
            return row[0] if row else None

        except Exception as e:
            print(f"[ERROR] Failed to get latest prediction id: {e}")
            return None
