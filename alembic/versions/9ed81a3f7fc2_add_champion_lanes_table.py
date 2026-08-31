"""add champion_lanes table

Revision ID: 9ed81a3f7fc2
Revises: ea9a2b4722f1
Create Date: 2026-09-01 00:50:06.551520

SPEC-04, item B4 §4.1 — la distribution de lanes d'un champion
(`src/lane_discovery.py:parse_lane_distribution()`) est déjà scrapée mais
jetée : seules les lanes au-dessus du seuil de scrape sont conservées. Cette
table persiste la distribution complète, qui sert de matrice de
vraisemblance à `src/role_inference.py` (l'algorithme d'affectation des
rôles a besoin de savoir à quel point un rôle est *improbable*, pas
seulement quels rôles sont joués).

Écrite par le pipeline de scraping (`src/multilane.py`) à chaque
découverte de lane. Si elle est vide (base pas encore re-scrapée depuis
cette migration), `Database.get_all_champion_lane_distributions()` se rabat
sur le volume de `matchups`.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "9ed81a3f7fc2"
down_revision: Union[str, Sequence[str], None] = "ea9a2b4722f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create champion_lanes (champion, lane) -> share%."""
    op.create_table(
        "champion_lanes",
        sa.Column("champion", sa.Integer(), nullable=False),
        sa.Column("lane", sa.Text(), nullable=False),
        sa.Column("share", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["champion"], ["champions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("champion", "lane"),
    )


def downgrade() -> None:
    """Drop champion_lanes."""
    op.drop_table("champion_lanes")
