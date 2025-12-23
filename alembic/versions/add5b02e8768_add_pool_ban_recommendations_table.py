"""add_pool_ban_recommendations_table

Revision ID: add5b02e8768
Revises: 2124c2bc4262
Create Date: 2025-12-22 22:29:25.926415

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add5b02e8768'
down_revision: Union[str, Sequence[str], None] = '2124c2bc4262'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add pool_ban_recommendations table for pre-calculated ban recommendations."""
    # Create pool_ban_recommendations table
    op.create_table(
        'pool_ban_recommendations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pool_name', sa.Text(), nullable=False),
        sa.Column('enemy_champion', sa.Text(), nullable=False),
        sa.Column('threat_score', sa.Float(), nullable=False),
        sa.Column('best_response_delta2', sa.Float(), nullable=False),
        sa.Column('best_response_champion', sa.Text(), nullable=False),
        sa.Column('matchups_count', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pool_name', 'enemy_champion', name='uq_pool_enemy')
    )

    # Create indexes for fast lookups
    op.create_index('idx_pool_bans_pool', 'pool_ban_recommendations', ['pool_name'])
    op.create_index('idx_pool_bans_threat', 'pool_ban_recommendations', ['pool_name', 'threat_score'])


def downgrade() -> None:
    """Remove pool_ban_recommendations table."""
    # Drop indexes first
    op.drop_index('idx_pool_bans_threat', table_name='pool_ban_recommendations')
    op.drop_index('idx_pool_bans_pool', table_name='pool_ban_recommendations')

    # Drop table
    op.drop_table('pool_ban_recommendations')
