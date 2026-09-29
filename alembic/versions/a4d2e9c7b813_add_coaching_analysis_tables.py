"""add coaching analysis tables

Revision ID: a4d2e9c7b813
Revises: 5c19a7e2d4b1
Create Date: 2026-09-29

SPEC-19 phases 2 à 4 — coach de gameplay : métriques par participant
(`game_metrics`, format long), constats affichés en fin de partie
(`game_findings`), axes de travail (`coaching_goals`) et leurs verdicts
partie par partie (`goal_verdicts`).

Tout se recalcule depuis `game_records` (le brut) : `game_metrics` et
`game_findings` sont vidées et reconstruites quand `grid_version` change.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a4d2e9c7b813"
down_revision: Union[str, Sequence[str], None] = "5c19a7e2d4b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create game_metrics, game_findings, coaching_goals and goal_verdicts."""
    op.execute("""
        CREATE TABLE game_metrics (
            game_id INTEGER NOT NULL,
            participant_id INTEGER NOT NULL,
            metric TEXT NOT NULL,
            is_player INTEGER NOT NULL DEFAULT 0,
            role TEXT,
            champion_id INTEGER,
            value REAL NOT NULL,
            norm_mean REAL,
            norm_sd REAL,
            norm_n INTEGER,
            z_norm REAL,
            objective_value REAL,
            objective_sd REAL,
            objective_source TEXT,
            z_objective REAL,
            grid_version INTEGER,
            PRIMARY KEY (game_id, participant_id, metric)
        )
        """)
    op.execute("CREATE INDEX idx_game_metrics_role_metric ON game_metrics(role, metric)")
    op.execute("""
        CREATE TABLE game_findings (
            game_id INTEGER NOT NULL,
            metric TEXT NOT NULL,
            polarity TEXT NOT NULL,
            z REAL NOT NULL,
            reference TEXT NOT NULL,
            rank INTEGER NOT NULL,
            PRIMARY KEY (game_id, metric)
        )
        """)
    op.execute("""
        CREATE TABLE coaching_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric TEXT NOT NULL,
            role TEXT NOT NULL,
            target REAL NOT NULL,
            origin TEXT NOT NULL,
            status TEXT NOT NULL,
            started_utc TEXT NOT NULL,
            acquired_utc TEXT
        )
        """)
    op.execute("""
        CREATE TABLE goal_verdicts (
            goal_id INTEGER NOT NULL,
            game_id INTEGER NOT NULL,
            value REAL NOT NULL,
            held INTEGER NOT NULL,
            PRIMARY KEY (goal_id, game_id)
        )
        """)


def downgrade() -> None:
    """Drop the four tables (recomputable from game_records, except the goals
    and their verdicts)."""
    op.execute("DROP TABLE IF EXISTS goal_verdicts")
    op.execute("DROP TABLE IF EXISTS coaching_goals")
    op.execute("DROP TABLE IF EXISTS game_findings")
    op.execute("DROP INDEX IF EXISTS idx_game_metrics_role_metric")
    op.execute("DROP TABLE IF EXISTS game_metrics")
