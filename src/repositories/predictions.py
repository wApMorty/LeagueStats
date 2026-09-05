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

    def update_prediction_outcome(
        self, prediction_id: int, outcome: int, game_id: Optional[int] = None
    ) -> bool:
        """Set outcome (1=win, 0=loss) on an existing prediction row.

        Args:
            prediction_id: Row id returned by insert_prediction.
            outcome: 1 for a win, 0 for a loss.
            game_id: LCU game id that produced this outcome (SPEC-08), or
                None for a manually-typed 'outcome win|loss' command. A
                partial unique index on predictions.game_id (migration
                13cbeb46785a) guarantees one game never labels two rows --
                a duplicate assignment raises sqlite3.IntegrityError, caught
                below and reported as a failed update, never a crash.

        Returns:
            True if a row was updated, False otherwise (including on failure).
        """
        try:
            cursor = self.db.connection.cursor()
            cursor.execute(
                "UPDATE predictions SET outcome = ?, game_id = ? WHERE id = ?",
                (outcome, game_id, prediction_id),
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

    def get_pending_predictions(self, limit: Optional[int] = None) -> List[Dict]:
        """Predictions without an outcome yet (SPEC-08), most recent first.

        Args:
            limit: Maximum number of rows to return. None = unbounded.

        Returns:
            A list of dicts: {"id", "created_utc" (raw 'YYYY-MM-DD HH:MM:SS'
            UTC string, as written by SQLite's datetime('now') --
            OutcomeTracker parses it), "ally_champions" and "enemy_champions"
            (decoded from CSV to List[int]), "predicted_probability"}. A row
            whose CSV fails to decode is skipped rather than raised.
        """
        try:
            cursor = self.db.connection.cursor()
            query = (
                "SELECT id, created_utc, ally_champions, enemy_champions, "
                "predicted_probability FROM predictions WHERE outcome IS NULL "
                "ORDER BY id DESC"
            )
            if limit is not None:
                cursor.execute(query + " LIMIT ?", (limit,))
            else:
                cursor.execute(query)
            rows = cursor.fetchall()
        except Exception as e:
            print(f"[ERROR] Failed to get pending predictions: {e}")
            return []

        pending: List[Dict] = []
        for pred_id, created_utc, ally_csv, enemy_csv, predicted_probability in rows:
            try:
                ally_champions = [int(c) for c in ally_csv.split(",") if c]
                enemy_champions = [int(c) for c in enemy_csv.split(",") if c]
            except (ValueError, AttributeError):
                continue
            pending.append(
                {
                    "id": pred_id,
                    "created_utc": created_utc,
                    "ally_champions": ally_champions,
                    "enemy_champions": enemy_champions,
                    "predicted_probability": predicted_probability,
                }
            )
        return pending

    def count_labelled_predictions(self) -> int:
        """Total number of predictions with a known outcome (SPEC-08 progress
        counter towards analysis_config.MIN_ROWS_FOR_CALIBRATION)."""
        try:
            cursor = self.db.connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM predictions WHERE outcome IS NOT NULL")
            row = cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            print(f"[ERROR] Failed to count labelled predictions: {e}")
            return 0
