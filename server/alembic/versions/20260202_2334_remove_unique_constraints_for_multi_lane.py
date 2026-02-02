"""Remove unique constraints for multi-lane matchups

Revision ID: 20260202_2334
Revises: 20260119_2100
Create Date: 2026-02-02 23:34:00

This migration removes unique constraints from matchups and synergies tables
to support multi-lane data (same matchup in Top, Jungle, Mid, Support lanes).

Background:
- SQLite local database contains ~39,875 matchups and ~31,622 synergies
- These include legitimate multi-lane entries (not duplicates)
- Example: Yorick vs Aatrox in Top, Jungle, Mid, Support = 4 separate rows
- Previous unique constraints were incorrectly preventing these valid entries

Changes:
- DROP unique index ix_matchups_champion_enemy
- CREATE non-unique index ix_matchups_champion_enemy (for query performance)
- DROP unique index ix_synergies_champion_ally
- CREATE non-unique index ix_synergies_champion_ally (for query performance)

Future work:
- Add lane column to matchups/synergies tables
- Restore unique constraint as UNIQUE(champion_id, enemy_id, lane)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260202_2334'
down_revision: Union[str, None] = '20260119_2100'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove unique constraints to support multi-lane matchups/synergies."""

    # Drop and recreate matchups index as non-unique
    op.drop_index('ix_matchups_champion_enemy', table_name='matchups')
    op.create_index(
        'ix_matchups_champion_enemy',
        'matchups',
        ['champion_id', 'enemy_id'],
        unique=False
    )

    # Drop and recreate synergies index as non-unique
    op.drop_index('ix_synergies_champion_ally', table_name='synergies')
    op.create_index(
        'ix_synergies_champion_ally',
        'synergies',
        ['champion_id', 'ally_id'],
        unique=False
    )


def downgrade() -> None:
    """Restore unique constraints (will fail if duplicate multi-lane data exists)."""

    # WARNING: This downgrade will FAIL if multi-lane duplicates exist in the database
    # You must manually clean up duplicates before running this downgrade

    # Drop and recreate matchups index as unique
    op.drop_index('ix_matchups_champion_enemy', table_name='matchups')
    op.create_index(
        'ix_matchups_champion_enemy',
        'matchups',
        ['champion_id', 'enemy_id'],
        unique=True
    )

    # Drop and recreate synergies index as unique
    op.drop_index('ix_synergies_champion_ally', table_name='synergies')
    op.create_index(
        'ix_synergies_champion_ally',
        'synergies',
        ['champion_id', 'ally_id'],
        unique=True
    )
