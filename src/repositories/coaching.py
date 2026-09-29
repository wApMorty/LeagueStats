"""Analyse du coach de gameplay (SPEC-19 phases 2 à 4, migration a4d2e9c7b813).

game_metrics, game_findings, coaching_goals, goal_verdicts, et lectures de
game_records et rank_snapshots. Hors de la façade `Database` (déjà longue) :
les modules de src/coaching/ instancient ce repository sur la base ouverte.
Sans try/except, comme game_records.py : les appelants sont best-effort.
"""

from typing import Dict, List, Optional, Sequence


class CoachingRepository:
    """Lectures et écritures de l'analyse des parties capturées."""

    def __init__(self, db) -> None:
        self.db = db

    def _rows(self, sql: str, params: Sequence = ()) -> list:
        cursor = self.db.connection.cursor()
        cursor.execute(sql, tuple(params))
        return cursor.fetchall()

    def _write(self, sql: str, rows: Sequence[Sequence]) -> None:
        self.db.connection.cursor().executemany(sql, rows)
        self.db.connection.commit()

    # ---------- parties à analyser ----------

    def unanalyzed_games(self) -> List[dict]:
        """Parties capturées sans aucune ligne de métriques, de la plus ancienne à la plus récente."""
        rows = self._rows("""
            SELECT game_id, queue_id, game_creation_utc, duration_s, player_participant_id,
                   raw_game, raw_timeline, raw_eog
            FROM game_records
            WHERE game_id NOT IN (SELECT DISTINCT game_id FROM game_metrics)
            ORDER BY game_creation_utc
            """)
        keys = ("game_id", "queue_id", "created", "duration_s", "player_pid", "game", "timeline")
        return [dict(zip(keys + ("eog",), row)) for row in rows]

    def has_stale_analysis(self, grid_version: int) -> bool:
        return bool(
            self._rows(
                "SELECT 1 FROM game_metrics WHERE is_player = 1 AND grid_version != ? LIMIT 1",
                (grid_version,),
            )
        )

    def clear_analysis(self) -> None:
        """Vide les tables recalculables ; les axes et leurs verdicts restent."""
        cursor = self.db.connection.cursor()
        cursor.execute("DELETE FROM game_findings")
        cursor.execute("DELETE FROM game_metrics")
        self.db.connection.commit()

    # ---------- références ----------

    def norm_values(self, role: str, metric: str, before_utc: str, window: int) -> List[float]:
        """Valeurs des autres joueurs du poste, sur les `window` parties précédentes."""
        rows = self._rows(
            """
            SELECT m.value FROM game_metrics m
            WHERE m.is_player = 0 AND m.role = ? AND m.metric = ?
              AND m.game_id IN (
                  SELECT game_id FROM game_records WHERE game_creation_utc < ?
                  ORDER BY game_creation_utc DESC LIMIT ?)
            """,
            (role, metric, before_utc, window),
        )
        return [row[0] for row in rows]

    def predicted_probability(self, game_id: int) -> Optional[float]:
        rows = self._rows(
            "SELECT predicted_probability FROM predictions WHERE game_id = ?", (game_id,)
        )
        return rows[0][0] if rows else None

    # ---------- écritures de l'analyse ----------

    def insert_metrics(self, rows: Sequence[Sequence]) -> None:
        """Lignes (game_id, participant_id, metric, is_player, role, champion_id, value,
        norm_mean, norm_sd, norm_n, z_norm, objective_value, objective_sd,
        objective_source, z_objective, grid_version)."""
        self._write(
            "INSERT OR REPLACE INTO game_metrics VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

    def insert_findings(self, rows: Sequence[Sequence]) -> None:
        """Lignes (game_id, metric, polarity, z, reference, rank)."""
        self._write("INSERT OR REPLACE INTO game_findings VALUES (?, ?, ?, ?, ?, ?)", rows)

    # ---------- historique du joueur ----------

    def player_history(self, role: Optional[str] = None, limit: int = 1000) -> List[dict]:
        """Lignes du joueur, de la plus récente à la plus ancienne partie."""
        keys = (
            "game_id",
            "created",
            "role",
            "champion_id",
            "metric",
            "value",
            "norm_mean",
            "norm_n",
            "z_norm",
            "objective_value",
            "z_objective",
        )
        rows = self._rows(
            """
            SELECT m.game_id, g.game_creation_utc, m.role, m.champion_id, m.metric, m.value,
                   m.norm_mean, m.norm_n, m.z_norm, m.objective_value, m.z_objective
            FROM game_metrics m JOIN game_records g ON g.game_id = m.game_id
            WHERE m.is_player = 1 AND (? IS NULL OR m.role = ?)
              AND m.game_id IN (
                  SELECT DISTINCT m2.game_id FROM game_metrics m2
                  JOIN game_records g2 ON g2.game_id = m2.game_id
                  WHERE m2.is_player = 1 AND (? IS NULL OR m2.role = ?)
                  ORDER BY g2.game_creation_utc DESC LIMIT ?)
            ORDER BY g.game_creation_utc DESC
            """,
            (role, role, role, role, limit),
        )
        return [dict(zip(keys, row)) for row in rows]

    def player_roles(self) -> Dict[str, int]:
        """Nombre de parties analysées par poste du joueur."""
        rows = self._rows(
            "SELECT role, COUNT(DISTINCT game_id) FROM game_metrics "
            "WHERE is_player = 1 AND role IS NOT NULL GROUP BY role"
        )
        return dict(rows)

    def rank_snapshots(self) -> List[tuple]:
        """(captured_utc, queue, tier, division, lp), de la plus ancienne à la plus récente."""
        return self._rows(
            "SELECT captured_utc, queue, tier, division, lp FROM rank_snapshots ORDER BY id"
        )

    # ---------- axes de travail ----------

    def goals(self, status: Optional[str] = "active") -> List[dict]:
        keys = ("id", "metric", "role", "target", "origin", "status", "started", "acquired")
        rows = self._rows(
            "SELECT id, metric, role, target, origin, status, started_utc, acquired_utc "
            "FROM coaching_goals WHERE (? IS NULL OR status = ?) ORDER BY id",
            (status, status),
        )
        return [dict(zip(keys, row)) for row in rows]

    def insert_goal(self, metric: str, role: str, target: float, origin: str) -> None:
        self._write(
            "INSERT INTO coaching_goals (metric, role, target, origin, status, started_utc) "
            "VALUES (?, ?, ?, ?, 'active', datetime('now'))",
            [(metric, role, target, origin)],
        )

    def set_goal_status(self, goal_id: int, status: str) -> None:
        self._write(
            "UPDATE coaching_goals SET status = ?, "
            "acquired_utc = CASE WHEN ? = 'acquired' THEN datetime('now') END WHERE id = ?",
            [(status, status, goal_id)],
        )

    def insert_verdict(self, goal_id: int, game_id: int, value: float, held: bool) -> None:
        self._write(
            "INSERT OR IGNORE INTO goal_verdicts VALUES (?, ?, ?, ?)",
            [(goal_id, game_id, value, int(held))],
        )

    def verdicts(self, goal_id: int, limit: int) -> List[bool]:
        """Verdicts de l'axe, du plus récent au plus ancien."""
        rows = self._rows(
            """
            SELECT v.held FROM goal_verdicts v JOIN game_records g ON g.game_id = v.game_id
            WHERE v.goal_id = ? ORDER BY g.game_creation_utc DESC LIMIT ?
            """,
            (goal_id, limit),
        )
        return [bool(row[0]) for row in rows]
