"""add game_records and rank_snapshots

Revision ID: 5c19a7e2d4b1
Revises: 13cbeb46785a
Create Date: 2026-09-29

SPEC-19 phase 1 — coach de gameplay : capture brute des parties SoloQ/Flex et
photos de classement. Le brut est la source de vérité : les métriques
(`game_metrics`) et les constats (`game_findings`) en seront recalculés, et
leurs tables arrivent avec les phases 2 et 3, une fois la grille arrêtée par
l'exploration.

`raw_eog` (écran de fin de partie) n'est connu qu'en direct : c'est la seule
source fiable du poste de chaque joueur (`detectedTeamPosition`), le détail de
la partie annonçant deux « JUNGLE » par équipe (spike du 2026-09-28).
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "5c19a7e2d4b1"
down_revision: Union[str, Sequence[str], None] = "13cbeb46785a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create game_records and rank_snapshots."""
    op.execute("""
        CREATE TABLE game_records (
            game_id INTEGER PRIMARY KEY,
            queue_id INTEGER NOT NULL,
            game_creation_utc TEXT NOT NULL,
            duration_s INTEGER,
            player_participant_id INTEGER,
            raw_game TEXT NOT NULL,
            raw_timeline TEXT,
            raw_eog TEXT,
            captured_utc TEXT NOT NULL
        )
        """)
    op.execute("""
        CREATE TABLE rank_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            captured_utc TEXT NOT NULL,
            queue TEXT NOT NULL,
            tier TEXT NOT NULL,
            division TEXT,
            lp INTEGER NOT NULL,
            wins INTEGER,
            losses INTEGER,
            lp_delta INTEGER,
            game_id INTEGER
        )
        """)
    # Une photo par partie au plus ; les photos de démarrage (game_id NULL)
    # restent libres, SQLite tenant NULL != NULL.
    op.execute(
        "CREATE UNIQUE INDEX idx_rank_snapshots_game_id "
        "ON rank_snapshots(game_id) WHERE game_id IS NOT NULL"
    )


def downgrade() -> None:
    """Drop both tables (data loss: the raw games cannot be refetched beyond
    the LCU's 20-game history)."""
    op.execute("DROP INDEX IF EXISTS idx_rank_snapshots_game_id")
    op.execute("DROP TABLE IF EXISTS rank_snapshots")
    op.execute("DROP TABLE IF EXISTS game_records")
