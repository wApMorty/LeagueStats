"""add game_id to predictions

Revision ID: 13cbeb46785a
Revises: 3e87f22f2ec1
Create Date: 2026-09-05 23:23:15.975217

SPEC-08 — fermer la boucle de mesure : `predictions` avait 12 lignes et 0
outcome renseigné, le seul chemin d'écriture étant la commande manuelle
`outcome win|loss`, empruntée zéro fois sur 12 parties. `OutcomeTracker`
(src/draft/outcome_tracker.py) résout maintenant les prédictions en attente
depuis l'historique de matchs du LCU, ce qui exige un identifiant de partie
pour garantir l'idempotence (une relance du rattrapage ne doit jamais
labelliser deux fois la même prédiction, et une même partie ne doit jamais
labelliser deux prédictions différentes).

`game_id` reste NULL pour toute résolution manuelle (comportement de
`update_prediction_outcome` préservé, `game_id` optionnel) et pour les 12
prédictions historiques du 01/09 au 05/09 (hors de la fenêtre de 6h de
rapprochement, volontairement laissées à NULL -- SPEC-08 §2.8).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "13cbeb46785a"
down_revision: Union[str, Sequence[str], None] = "3e87f22f2ec1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add predictions.game_id and a partial unique index on it.

    The partial index (WHERE game_id IS NOT NULL) is what makes the
    idempotence guarantee enforceable at the database level: SQLite treats
    NULL != NULL, so an ordinary unique index would let an unlimited number
    of manually-resolved (game_id IS NULL) rows coexist, while still
    rejecting a second automatic resolution that reuses a game_id already
    attached to another prediction.
    """
    op.add_column("predictions", sa.Column("game_id", sa.Integer(), nullable=True))
    op.execute(
        "CREATE UNIQUE INDEX idx_predictions_game_id "
        "ON predictions(game_id) WHERE game_id IS NOT NULL"
    )


def downgrade() -> None:
    """Drop the index and the game_id column (data loss: which LCU game
    resolved a given prediction is not recoverable, only outcome survives)."""
    op.execute("DROP INDEX IF EXISTS idx_predictions_game_id")
    # SQLite needs batch mode to drop a column (table rebuild) -- see
    # b7e41c9a3f02_add_lane_column_and_db_meta_table.py for the same pattern.
    with op.batch_alter_table("predictions") as batch_op:
        batch_op.drop_column("game_id")
