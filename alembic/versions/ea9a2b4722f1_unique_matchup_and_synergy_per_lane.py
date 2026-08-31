"""unique matchup and synergy per lane

Revision ID: ea9a2b4722f1
Revises: ab14babf365b
Create Date: 2026-09-01 00:17:55.555320

SPEC-03, item B8 — Sans contrainte d'unicité, `scripts/repair_data.py` et le
pipeline principal peuvent écrire des doublons `(champion, enemy, lane)` avec
des valeurs contradictoires (mesuré : 1 263 doublons matchups, 783 synergies ;
ex. Annie vs Lux en support : delta2 = -9.25/67 parties ET +4.61/72 parties).

Étapes :
1. `lane IS NULL` -> `'default'`. SQLite ne considère jamais NULL = NULL, donc
   un index unique laisserait passer un nombre illimité de lignes non taguées
   (repli de `src/multilane.py` en cas d'échec de la découverte de lane). On
   choisit l'option sûre décrite dans SPEC-03 §B8 : interdire NULL plutôt que
   le tolérer hors contrainte.
2. Dédoublonnage : pour chaque triplet, on garde la ligne au plus grand
   `games` (la mieux estimée), puis le plus grand `id` en cas d'égalité.
3. Index UNIQUE sur `(champion, enemy, lane)` / `(champion, ally, lane)`.

Le dédoublonnage n'est pas réversible : `downgrade()` retire seulement les
index uniques, il ne restaure pas les lignes supprimées ni les NULL d'origine.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ea9a2b4722f1"
down_revision: Union[str, Sequence[str], None] = "ab14babf365b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Backfill lane, dedupe, then enforce uniqueness per lane."""
    # 1. NULL lane -> 'default' (voir docstring du module).
    op.execute("UPDATE matchups SET lane = 'default' WHERE lane IS NULL")
    op.execute("UPDATE synergies SET lane = 'default' WHERE lane IS NULL")

    # 2. Dédoublonnage : conserver la ligne au plus grand `games` par triplet.
    op.execute("""
        DELETE FROM matchups WHERE id NOT IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY champion, enemy, lane ORDER BY games DESC, id DESC
                ) AS rn FROM matchups
            ) WHERE rn = 1
        )
    """)
    op.execute("""
        DELETE FROM synergies WHERE id NOT IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY champion, ally, lane ORDER BY games DESC, id DESC
                ) AS rn FROM synergies
            ) WHERE rn = 1
        )
    """)

    # 3. Contrainte d'unicité.
    op.create_index(
        "idx_matchups_unique", "matchups", ["champion", "enemy", "lane"], unique=True
    )
    op.create_index(
        "idx_synergies_unique", "synergies", ["champion", "ally", "lane"], unique=True
    )


def downgrade() -> None:
    """Drop the unique indexes.

    Le dédoublonnage et le backfill NULL -> 'default' de upgrade() ne sont
    pas annulés : les lignes supprimées sont perdues et les lanes 'default'
    restent en base (les distinguer à nouveau des NULL d'origine n'est plus
    possible).
    """
    op.drop_index("idx_synergies_unique", table_name="synergies")
    op.drop_index("idx_matchups_unique", table_name="matchups")
