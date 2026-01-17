"""add_synergies_table

Revision ID: cc46f5edf9b2
Revises: add5b02e8768
Create Date: 2026-01-16 15:59:29.921105

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cc46f5edf9b2'
down_revision: Union[str, Sequence[str], None] = 'add5b02e8768'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add synergies table for champion synergy data.

    This table stores synergy data between champions and their allies,
    with identical structure to matchups table (but semantic difference:
    synergies are WITH allies, matchups are AGAINST enemies).

    Schema mirrors matchups table:
    - champion: Champion being analyzed
    - ally: Allied champion (replaces 'enemy' in matchups)
    - winrate: Win rate when playing with this ally
    - pickrate: Pick rate of this ally combination
    - delta1/delta2: Performance metrics
    - games: Number of games in sample
    """
    # Create synergies table (structure identical to matchups)
    op.create_table(
        'synergies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('champion', sa.Integer(), nullable=False),
        sa.Column('ally', sa.Integer(), nullable=False),
        sa.Column('winrate', sa.Float(), nullable=False),
        sa.Column('pickrate', sa.Float(), nullable=False),
        sa.Column('delta1', sa.Float(), nullable=False),
        sa.Column('delta2', sa.Float(), nullable=False),
        sa.Column('games', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['champion'], ['champions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['ally'], ['champions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for performance (pattern identical to matchups)
    op.create_index('idx_synergies_champion', 'synergies', ['champion'])
    op.create_index('idx_synergies_ally', 'synergies', ['ally'])
    op.create_index('idx_synergies_pickrate', 'synergies', ['pickrate'])
    op.create_index('idx_synergies_champion_pickrate', 'synergies', ['champion', 'pickrate'])
    op.create_index('idx_synergies_ally_pickrate', 'synergies', ['ally', 'pickrate'])


def downgrade() -> None:
    """Remove synergies table and its indexes.

    WARNING: This will delete all synergy data. Ensure backup exists
    before downgrading if data preservation is required.
    """
    # Drop indexes first (required before dropping table)
    op.drop_index('idx_synergies_ally_pickrate', table_name='synergies')
    op.drop_index('idx_synergies_champion_pickrate', table_name='synergies')
    op.drop_index('idx_synergies_pickrate', table_name='synergies')
    op.drop_index('idx_synergies_ally', table_name='synergies')
    op.drop_index('idx_synergies_champion', table_name='synergies')

    # Drop synergies table
    op.drop_table('synergies')
