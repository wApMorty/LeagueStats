"""add_nocase_index_on_champions_name

Revision ID: ab14babf365b
Revises: b7e41c9a3f02
Create Date: 2026-08-31

SPEC-06 C4 — Les lectures de matchups filtrent sur ``c1.name = ? COLLATE
NOCASE``. Appliqué à la colonne comparée, ``COLLATE NOCASE`` interdit
l'usage de ``idx_champions_name`` : SQLite attaquait la requête par
``matchups`` (SCAN via idx_matchups_pickrate) au lieu de partir du
champion.

Mesure sur la base de production (26 604 matchups, 173 champions),
200 appels de ``get_matchup_delta2`` :

* avant : 1 336 ms (6,68 ms/appel)
* après :    23 ms (0,11 ms/appel) — ~55x

L'index ``COLLATE NOCASE`` conserve le comportement insensible à la casse
sans toucher aux requêtes existantes.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ab14babf365b"
down_revision: Union[str, Sequence[str], None] = "b7e41c9a3f02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the case-insensitive index on champions.name."""
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_champions_name_nocase " "ON champions(name COLLATE NOCASE)"
    )


def downgrade() -> None:
    """Drop the case-insensitive index (queries fall back to a scan)."""
    op.execute("DROP INDEX IF EXISTS idx_champions_name_nocase")
