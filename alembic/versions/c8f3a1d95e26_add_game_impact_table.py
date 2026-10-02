"""add game_impact table

Revision ID: c8f3a1d95e26
Revises: a4d2e9c7b813
Create Date: 2026-10-02

SPEC-20 phase 3 — impact de chaque événement d'une partie du joueur sur la win chance,
attribué aux joueurs (`delta_p` orienté du point de vue de l'équipe du participant).
Chaque ligne garde le `model_version` qui l'a produite : les impacts déjà calculés ne
sont jamais recalculés avec un modèle plus récent.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c8f3a1d95e26"
down_revision: Union[str, Sequence[str], None] = "a4d2e9c7b813"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create game_impact."""
    op.execute("""
        CREATE TABLE game_impact (
            game_id INTEGER NOT NULL,
            participant_id INTEGER NOT NULL,
            event_time_ms INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            delta_p REAL NOT NULL,
            model_version TEXT NOT NULL
        )
        """)
    op.execute("CREATE INDEX idx_game_impact_game ON game_impact(game_id)")


def downgrade() -> None:
    """Drop game_impact (recomputable from game_records and a trained model)."""
    op.execute("DROP INDEX IF EXISTS idx_game_impact_game")
    op.execute("DROP TABLE IF EXISTS game_impact")
