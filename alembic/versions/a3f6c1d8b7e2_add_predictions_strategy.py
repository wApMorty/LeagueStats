"""add predictions.strategy

Revision ID: a3f6c1d8b7e2
Revises: e5b7d2a14c93
Create Date: 2026-10-30

SPEC-46 tâche 226 — stratégie active au moment de la prédiction, pour comparer les stratégies à
l'usage. `predicted_probability` reste celle du modèle calibré. Les lignes existantes restent NULL.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f6c1d8b7e2"
down_revision: Union[str, Sequence[str], None] = "e5b7d2a14c93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add predictions.strategy (NULL for existing rows)."""
    op.execute("ALTER TABLE predictions ADD COLUMN strategy TEXT")


def downgrade() -> None:
    """Drop predictions.strategy."""
    op.execute("ALTER TABLE predictions DROP COLUMN strategy")
