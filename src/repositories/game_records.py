"""game_records et rank_snapshots (SPEC-19 phase 1, migration 5c19a7e2d4b1).

Sans try/except ici : l'appelant (src/coaching/capture.py) est best-effort et
distingue une base non migrée d'une autre erreur.
"""

from typing import Optional, Set


class GameRecordsRepository:
    """Écritures de la capture brute des parties et des photos de classement."""

    def __init__(self, db) -> None:
        self.db = db

    def get_captured_game_ids(self) -> Set[int]:
        cursor = self.db.connection.cursor()
        cursor.execute("SELECT game_id FROM game_records")
        return {row[0] for row in cursor.fetchall()}

    def get_recent_games(self, limit: int) -> list:
        """(game_id, player_participant_id) des `limit` dernières parties, sans le brut."""
        cursor = self.db.connection.cursor()
        cursor.execute(
            "SELECT game_id, player_participant_id FROM game_records "
            "ORDER BY game_creation_utc DESC LIMIT ?",
            (limit,),
        )
        return cursor.fetchall()

    def get_raw_game(self, game_id: int) -> Optional[str]:
        cursor = self.db.connection.cursor()
        cursor.execute("SELECT raw_game FROM game_records WHERE game_id = ?", (game_id,))
        row = cursor.fetchone()
        return row[0] if row else None

    def insert_game_record(
        self,
        game_id: int,
        queue_id: int,
        game_creation_utc: str,
        duration_s: Optional[int],
        player_participant_id: Optional[int],
        raw_game: str,
        raw_timeline: Optional[str],
        raw_eog: Optional[str],
    ) -> bool:
        """Insère une partie capturée. False si elle l'était déjà."""
        cursor = self.db.connection.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO game_records
            (game_id, queue_id, game_creation_utc, duration_s, player_participant_id,
             raw_game, raw_timeline, raw_eog, captured_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                game_id,
                queue_id,
                game_creation_utc,
                duration_s,
                player_participant_id,
                raw_game,
                raw_timeline,
                raw_eog,
            ),
        )
        self.db.connection.commit()
        return cursor.rowcount > 0

    def insert_rank_snapshot(
        self,
        queue: str,
        tier: str,
        division: Optional[str],
        lp: int,
        wins: Optional[int],
        losses: Optional[int],
        lp_delta: Optional[int] = None,
        game_id: Optional[int] = None,
    ) -> bool:
        """Insère une photo de classement. False si la partie en a déjà une."""
        cursor = self.db.connection.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO rank_snapshots
            (captured_utc, queue, tier, division, lp, wins, losses, lp_delta, game_id)
            VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (queue, tier, division, lp, wins, losses, lp_delta, game_id),
        )
        self.db.connection.commit()
        return cursor.rowcount > 0
