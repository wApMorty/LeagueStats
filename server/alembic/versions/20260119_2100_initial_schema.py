"""Initial schema: champions, matchups, synergies tables

Revision ID: 20260119_2100
Revises:
Create Date: 2026-01-19 21:00:00

This migration creates the initial database schema for LeagueStats Coach API:
- champions table (172 champions)
- matchups table (36,000+ champion vs enemy matchups)
- synergies table (30,000+ champion+ally synergies)

Includes indexes for performance:
- champions.name (unique index)
- champions.lolalytics_id (unique index)
- matchups (champion_id, enemy_id) composite unique index
- matchups.delta2 (index for tier list sorting)
- synergies (champion_id, ally_id) composite unique index
- synergies.delta2 (index for synergy sorting)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260119_2100'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial schema (champions, matchups, synergies)."""

    # Create champions table
    op.create_table(
        'champions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('lolalytics_id', sa.String(length=50), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('lolalytics_id')
    )
    op.create_index('ix_champions_name', 'champions', ['name'], unique=True)

    # Create matchups table
    op.create_table(
        'matchups',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('champion_id', sa.Integer(), nullable=False),
        sa.Column('enemy_id', sa.Integer(), nullable=False),
        sa.Column('winrate', sa.Float(), nullable=False),
        sa.Column('delta2', sa.Float(), nullable=False),
        sa.Column('games', sa.Integer(), nullable=False),
        sa.Column('pickrate', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['champion_id'], ['champions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['enemy_id'], ['champions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_matchups_champion_id', 'matchups', ['champion_id'], unique=False)
    op.create_index('ix_matchups_enemy_id', 'matchups', ['enemy_id'], unique=False)
    op.create_index('ix_matchups_delta2', 'matchups', ['delta2'], unique=False)
    op.create_index('ix_matchups_champion_enemy', 'matchups', ['champion_id', 'enemy_id'], unique=True)

    # Create synergies table
    op.create_table(
        'synergies',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('champion_id', sa.Integer(), nullable=False),
        sa.Column('ally_id', sa.Integer(), nullable=False),
        sa.Column('winrate', sa.Float(), nullable=False),
        sa.Column('delta2', sa.Float(), nullable=False),
        sa.Column('games', sa.Integer(), nullable=False),
        sa.Column('pickrate', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['champion_id'], ['champions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['ally_id'], ['champions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_synergies_champion_id', 'synergies', ['champion_id'], unique=False)
    op.create_index('ix_synergies_ally_id', 'synergies', ['ally_id'], unique=False)
    op.create_index('ix_synergies_delta2', 'synergies', ['delta2'], unique=False)
    op.create_index('ix_synergies_champion_ally', 'synergies', ['champion_id', 'ally_id'], unique=True)


def downgrade() -> None:
    """Drop all tables (champions, matchups, synergies)."""
    op.drop_table('synergies')
    op.drop_table('matchups')
    op.drop_table('champions')
