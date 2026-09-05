"""db_meta table repository (monitoring de fraîcheur des données).

Extracted from src/db.py (dette de code, TODO.md P4) : déplacement verbatim,
aucun changement de comportement. Table créée par migration b7e41c9a3f02.
"""

from sqlite3 import Error
from typing import Optional


class MetaRepository:
    """CRUD sur la table ``db_meta``."""

    def __init__(self, db) -> None:
        self.db = db

    def set_meta(self, key: str, value: str) -> None:
        """Store a key/value pair in db_meta (created by migration b7e41c9a3f02).

        Used by scripts/update_all.py to record pipeline metadata such as
        last_update_utc and scrape volumetry.
        """
        cursor = self.db.connection.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO db_meta (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                               updated_at = CURRENT_TIMESTAMP
                """,
                (key, str(value)),
            )
            self.db.connection.commit()
        except Error as e:
            print(f"[ERROR] Failed to set db_meta '{key}': {e}")

    def get_meta(self, key: str) -> Optional[str]:
        """Read a value from db_meta. Returns None if the key (or table) is missing.

        Missing table is tolerated so the app keeps working on a database
        that predates migration b7e41c9a3f02 (freshness check falls back
        to the db file mtime in that case).
        """
        cursor = self.db.connection.cursor()
        try:
            cursor.execute("SELECT value FROM db_meta WHERE key = ?", (key,))
            result = cursor.fetchone()
            return result[0] if result else None
        except Error:
            return None
