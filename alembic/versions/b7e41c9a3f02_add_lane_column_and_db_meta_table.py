"""add_lane_column_and_db_meta_table

Revision ID: b7e41c9a3f02
Revises: cc46f5edf9b2
Create Date: 2026-06-12

Horizon 1 (ROADMAP_2026.md §3 H1.1) — Fondation de la Tâche #15 :

1. Colonne ``lane`` (TEXT, nullable) sur ``matchups`` et ``synergies``.
   Avant cette migration, les scrapes multi-lane inséraient des lignes
   dupliquées indistinguables, agrégées à la volée par pondération games
   (cf. AUDIT_2026_06.md §note). La colonne permet de tagger chaque ligne
   avec sa lane LoLalytics : top, jungle, middle, bottom, support.
   NULL = donnée legacy (lane par défaut, inconnue).

2. Index composites pour les requêtes lane-aware (préparation du scoring
   lane-aware de l'Horizon 3).

3. Table ``db_meta`` (clé/valeur) pour le monitoring de fraîcheur des
   données : ``last_update_utc``, volumétrie du dernier scrape, etc.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7e41c9a3f02"
down_revision: Union[str, Sequence[str], None] = "cc46f5edf9b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add lane column, lane-aware indexes and db_meta table."""
    # 1. Lane column (nullable: legacy rows keep NULL = default lane)
    op.add_column("matchups", sa.Column("lane", sa.Text(), nullable=True))
    op.add_column("synergies", sa.Column("lane", sa.Text(), nullable=True))

    # 2. Composite indexes for lane-aware queries
    op.create_index(
        "idx_matchups_champion_lane_pickrate", "matchups", ["champion", "lane", "pickrate"]
    )
    op.create_index("idx_matchups_enemy_lane_pickrate", "matchups", ["enemy", "lane", "pickrate"])
    op.create_index(
        "idx_synergies_champion_lane_pickrate", "synergies", ["champion", "lane", "pickrate"]
    )
    op.create_index("idx_synergies_ally_lane_pickrate", "synergies", ["ally", "lane", "pickrate"])

    # 3. db_meta key/value table (data freshness monitoring)
    op.create_table(
        "db_meta",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    """Remove db_meta table, lane indexes and lane column.

    WARNING: dropping the lane column loses the lane granularity of all
    multi-lane scraped rows (they become indistinguishable duplicates again).
    """
    op.drop_table("db_meta")

    op.drop_index("idx_synergies_ally_lane_pickrate", table_name="synergies")
    op.drop_index("idx_synergies_champion_lane_pickrate", table_name="synergies")
    op.drop_index("idx_matchups_enemy_lane_pickrate", table_name="matchups")
    op.drop_index("idx_matchups_champion_lane_pickrate", table_name="matchups")

    # SQLite needs batch mode to drop a column (table rebuild)
    with op.batch_alter_table("synergies") as batch_op:
        batch_op.drop_column("lane")
    with op.batch_alter_table("matchups") as batch_op:
        batch_op.drop_column("lane")
