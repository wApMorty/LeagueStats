"""add predictions table

Revision ID: 2551bbcc9eb8
Revises: 9ed81a3f7fc2
Create Date: 2026-09-01 01:58:32.540568

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2551bbcc9eb8'
down_revision: Union[str, Sequence[str], None] = '9ed81a3f7fc2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add predictions table (SPEC-05 B7): logs (predicted probability, outcome)
    so the log-odds model's k_m/k_s coefficients can be calibrated against real
    results — see scripts/calibrate_model.py."""
    op.create_table(
        'predictions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_utc', sa.Text(), nullable=False),
        sa.Column('ally_champions', sa.Text(), nullable=False),
        sa.Column('enemy_champions', sa.Text(), nullable=False),
        sa.Column('ally_lanes', sa.Text(), nullable=True),
        sa.Column('predicted_probability', sa.Float(), nullable=False),
        sa.Column('model_version', sa.Text(), nullable=False),
        sa.Column('outcome', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_predictions_model_version', 'predictions', ['model_version'])


def downgrade() -> None:
    """Remove predictions table."""
    op.drop_index('idx_predictions_model_version', table_name='predictions')
    op.drop_table('predictions')
