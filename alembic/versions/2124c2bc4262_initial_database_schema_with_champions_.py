"""Initial database schema with champions, matchups, and champion_scores tables

Revision ID: 2124c2bc4262
Revises: 
Create Date: 2025-12-16 01:53:58.181939

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2124c2bc4262'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Create initial database tables."""
    # Create champions table
    op.create_table(
        'champions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(), nullable=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Create index on champions.name for faster lookups
    op.create_index('idx_champions_name', 'champions', ['name'])

    # Create matchups table
    op.create_table(
        'matchups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('champion', sa.Integer(), nullable=False),
        sa.Column('enemy', sa.Integer(), nullable=False),
        sa.Column('winrate', sa.Float(), nullable=False),
        sa.Column('delta1', sa.Float(), nullable=False),
        sa.Column('delta2', sa.Float(), nullable=False),
        sa.Column('pickrate', sa.Float(), nullable=False),
        sa.Column('games', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['champion'], ['champions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['enemy'], ['champions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create performance indexes on matchups table
    op.create_index('idx_matchups_champion', 'matchups', ['champion'])
    op.create_index('idx_matchups_enemy', 'matchups', ['enemy'])
    op.create_index('idx_matchups_pickrate', 'matchups', ['pickrate'])
    op.create_index('idx_matchups_champion_pickrate', 'matchups', ['champion', 'pickrate'])
    op.create_index('idx_matchups_enemy_pickrate', 'matchups', ['enemy', 'pickrate'])

    # Create champion_scores table
    op.create_table(
        'champion_scores',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('avg_delta2', sa.Float(), nullable=True),
        sa.Column('variance', sa.Float(), nullable=True),
        sa.Column('coverage', sa.Float(), nullable=True),
        sa.Column('peak_impact', sa.Float(), nullable=True),
        sa.Column('volatility', sa.Float(), nullable=True),
        sa.Column('target_ratio', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['id'], ['champions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema: Drop all tables."""
    # Drop tables in reverse order (respect foreign keys)
    op.drop_table('champion_scores')

    # Drop matchups indexes explicitly for clarity
    op.drop_index('idx_matchups_enemy_pickrate', table_name='matchups')
    op.drop_index('idx_matchups_champion_pickrate', table_name='matchups')
    op.drop_index('idx_matchups_pickrate', table_name='matchups')
    op.drop_index('idx_matchups_enemy', table_name='matchups')
    op.drop_index('idx_matchups_champion', table_name='matchups')
    op.drop_table('matchups')

    # Drop champions index explicitly for clarity
    op.drop_index('idx_champions_name', table_name='champions')
    op.drop_table('champions')
