"""add coaching_goals.reference

Revision ID: e5b7d2a14c93
Revises: c8f3a1d95e26
Create Date: 2026-10-11

SPEC-29 tâche 133 — référence d'un axe de travail : `norm` (norme des autres joueurs du
poste, comportement d'origine) ou `objective` (objectif OneTricks du champion joué,
jugé partie par partie). Les axes déjà en base restent `norm`.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5b7d2a14c93"
down_revision: Union[str, Sequence[str], None] = "c8f3a1d95e26"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add coaching_goals.reference (default 'norm')."""
    op.execute("ALTER TABLE coaching_goals ADD COLUMN reference TEXT NOT NULL DEFAULT 'norm'")


def downgrade() -> None:
    """Drop coaching_goals.reference (axes d'objectif relus comme des axes de norme)."""
    op.execute("ALTER TABLE coaching_goals DROP COLUMN reference")
