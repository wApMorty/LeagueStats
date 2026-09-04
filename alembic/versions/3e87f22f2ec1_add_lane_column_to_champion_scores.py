"""add lane column to champion_scores

Revision ID: 3e87f22f2ec1
Revises: 2551bbcc9eb8
Create Date: 2026-09-04 12:53:31.178378

champion_scores stockait un score unique par champion, agrégeant toutes les
lanes du champion (ex. Yasuo top+mid+bottom mélangés). La tier list générée
depuis ces scores ignorait donc le filtre lane déjà disponible côté requêtes
matchups (cf. fix Live Coach #46), contrairement à l'intention affichée par
les pools "role"-scoped du sélecteur de pool.

champion_scores est une table dérivée/cache : elle est entièrement
recalculée par GlobalScoreCalculator.calculate_all() (déclenché par le
pipeline de parsing ou l'action manuelle "Recalculer les scores"), et
Database.init_champion_scores_table() la DROP + recrée déjà à chaque
recalcul. Cette migration suit donc le même principe : pas de préservation
de données, elles sont régénérées lane par lane au prochain recalcul.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3e87f22f2ec1'
down_revision: Union[str, Sequence[str], None] = '2551bbcc9eb8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rebuild champion_scores with a lane column and a composite (id, lane) PK.

    'all' = toutes lanes agrégées (comportement historique, conservé comme
    fallback pour les pools multi-lane/custom). Une ligne par lane scrapée
    (top/jungle/middle/bottom/support) est ajoutée au prochain recalcul.
    """
    op.drop_table("champion_scores")
    op.create_table(
        "champion_scores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lane", sa.Text(), nullable=False, server_default="all"),
        sa.Column("avg_delta2", sa.Float(), nullable=True),
        sa.Column("variance", sa.Float(), nullable=True),
        sa.Column("coverage", sa.Float(), nullable=True),
        sa.Column("peak_impact", sa.Float(), nullable=True),
        sa.Column("volatility", sa.Float(), nullable=True),
        sa.Column("target_ratio", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["id"], ["champions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", "lane"),
    )


def downgrade() -> None:
    """Revert to one all-lanes score per champion (data lost, same as upgrade)."""
    op.drop_table("champion_scores")
    op.create_table(
        "champion_scores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("avg_delta2", sa.Float(), nullable=True),
        sa.Column("variance", sa.Float(), nullable=True),
        sa.Column("coverage", sa.Float(), nullable=True),
        sa.Column("peak_impact", sa.Float(), nullable=True),
        sa.Column("volatility", sa.Float(), nullable=True),
        sa.Column("target_ratio", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["id"], ["champions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
