"""Suivi dans le temps et axes de travail (SPEC-19 tâches 36 à 38).

Historiques synthétiques en mémoire pour les calculs purs, base temporaire
pour les axes, le bilan et les commandes du Live Coach.
"""

from types import SimpleNamespace

import pytest

from src.coaching import goals, progression, report
from src.coaching.findings import GameAnalysis
from src.config_constants import coaching_config
from src.draft.commands import CommandListener
from src.repositories.coaching import CoachingRepository


def _history(metric, values, z=None, norm_mean=1.0, norm_n=20):
    """Lignes du joueur, de la plus récente à la plus ancienne."""
    return [
        {
            "game_id": index,
            "metric": metric,
            "value": value,
            "z_norm": z,
            "norm_mean": norm_mean,
            "norm_n": norm_n,
        }
        for index, value in enumerate(values)
    ]


def _store_history(db, metric, values, z, role="top"):
    """Parties analysées du joueur : game_records et lignes de game_metrics."""
    repo = CoachingRepository(db)
    rows = []
    for index, value in enumerate(values, 1):  # la dernière est la plus récente
        db.insert_game_record(
            game_id=index,
            queue_id=420,
            game_creation_utc=f"2026-09-01 00:00:{index:02d}",
            duration_s=1800,
            player_participant_id=1,
            raw_game="{}",
            raw_timeline=None,
            raw_eog=None,
        )
        rows.append(
            (index, 1, metric, 1, role, 2, value, 1.0, 0.5, 20, z)
            + (None, None, None, None, coaching_config.GRID_VERSION)
        )
    repo.insert_metrics(rows)
    return repo


def _analysis(game_id, value, metric="deaths_before_14", role="top"):
    return GameAnalysis(
        game_id=game_id,
        queue_id=420,
        duration_s=1800,
        win=True,
        role=role,
        champion_id=2,
        opponent_champion_id=240,
        values={metric: value},
    )


class TestPatterns:
    def test_recurring_negative_z_is_a_pattern(self):
        history = _history("deaths_before_14", [3] * 10, z=-1.5)
        (pattern,) = progression.patterns(history, "top")
        assert (pattern.metric, pattern.polarity, pattern.count) == (
            "deaths_before_14",
            "negative",
            10,
        )
        assert pattern.p_value < coaching_config.RECURRENCE_ALPHA

    def test_usual_scatter_is_not_a_pattern(self):
        zs = [-1.2, 0.3, 0.1, -0.4, 0.8, -0.2, 0.5, 1.1, -0.6, 0.0]
        history = [
            dict(row, z_norm=z) for row, z in zip(_history("deaths_before_14", [1] * 10), zs)
        ]
        assert progression.patterns(history, "top") == []

    def test_no_pattern_on_a_norm_below_the_sample_threshold(self):
        history = _history("deaths_before_14", [3] * 10, z=-1.5, norm_n=5)
        assert progression.patterns(history, "top") == []


class TestTrendsAndLp:
    def test_fewer_deaths_recently_is_progress(self):
        recent, older = [1, 0, 1, 0, 1], [3, 4, 3, 4, 3]
        (trend,) = progression.trends(_history("deaths_before_14", recent + older), "top")
        assert trend.verdict == "progrès"
        assert (trend.before, trend.after) == (pytest.approx(3.4), pytest.approx(0.6))

    def test_no_verdict_below_the_minimum_sample(self):
        assert progression.trends(_history("deaths_before_14", [1, 3, 1, 3]), "top") == []

    def test_continuous_rank_scale(self):
        assert progression.lp_scale("DIAMOND", "II", 38) == 6 * 400 + 2 * 100 + 38
        assert progression.lp_scale("MASTER", "I", 120) == 7 * 400 + 120

    def test_lp_change_per_queue(self):
        snapshots = [
            ("2026-09-28 10:00:00", "RANKED_SOLO_5x5", "DIAMOND", "III", 90),
            ("2026-09-29 10:00:00", "RANKED_SOLO_5x5", "DIAMOND", "II", 38),
        ]
        first, last, delta = progression.lp_changes(snapshots)["RANKED_SOLO_5x5"]
        assert delta == 48 and last[3] == 38


class TestGoals:
    def test_player_goal_targets_the_latest_norm(self, db):
        repo = _store_history(db, "deaths_before_14", [2, 2, 2], z=-0.5)

        message = goals.set_goal(repo, "deaths_before_14", "top")

        assert "Nouvel axe" in message
        (goal,) = repo.goals()
        assert (goal["metric"], goal["target"], goal["origin"]) == (
            "deaths_before_14",
            1.0,
            "player",
        )

    def test_unknown_metric_is_refused(self, db):
        assert "Métrique inconnue" in goals.set_goal(CoachingRepository(db), "kda", "top")

    def test_a_third_goal_drops_the_oldest(self, db):
        repo = _store_history(db, "deaths_before_14", [2], z=0.0)
        repo.insert_metrics(
            [
                (1, 1, metric, 1, "top", 2, value, value, 1.0, 20, 0.0, None, None, None, None, 1)
                for metric, value in (("cs_10", 60.0), ("solo_deaths", 1.0))
            ]
        )
        for metric in ("deaths_before_14", "cs_10", "solo_deaths"):
            goals.set_goal(repo, metric, "top")

        assert [g["metric"] for g in repo.goals()] == ["cs_10", "solo_deaths"]

    def test_verdicts_until_the_goal_is_acquired(self, db):
        repo = _store_history(db, "deaths_before_14", [2] * 6, z=-0.5)
        goals.set_goal(repo, "deaths_before_14", "top")  # cible ≤ 1

        lines = []
        for game_id, deaths in enumerate([0, 1, 3, 0, 1], 1):
            lines = goals.judge(repo, _analysis(game_id, deaths))

        assert "tenu (4/5" in lines[0]
        assert lines[-1] == "[OK] Axe acquis : Morts avant 14 min !"
        assert repo.goals() == []

    def test_goal_of_another_role_is_not_judged(self, db):
        repo = _store_history(db, "deaths_before_14", [2], z=0.0)
        goals.set_goal(repo, "deaths_before_14", "top")
        assert goals.judge(repo, _analysis(1, 0, role="jungle")) == []

    def test_negative_pattern_is_proposed_as_a_goal(self, db):
        repo = _store_history(db, "deaths_before_14", [3] * 10, z=-1.5)

        assert "Nouvel axe" in goals.propose(repo, "top")
        assert goals.propose(repo, "top") is None  # déjà actif, pas d'autre schéma

    def test_draft_reminder_lists_active_goals(self, db):
        repo = _store_history(db, "deaths_before_14", [2], z=0.0)
        goals.set_goal(repo, "deaths_before_14", "top")

        (line,) = goals.draft_reminder(db)

        assert line.startswith("[AXE] Axe de travail « Morts avant 14 min » (top, cible ≤ 1)")


class TestReview:
    def test_review_without_games(self, db):
        assert report.review(db) == ["[INFO] Bilan : aucune partie analysée pour l'instant"]

    def test_review_sections(self, db):
        _store_history(db, "deaths_before_14", [3] * 10, z=-1.5)

        text = "\n".join(report.review(db))

        assert "10 parties analysées, poste principal : top" in text
        assert "faiblesse Morts avant 14 min : 10/10 parties" in text
        assert "Nouvel axe de travail" in text


class TestLiveCoachCommands:
    def _listener(self, db):
        return CommandListener(SimpleNamespace(assistant=SimpleNamespace(db=db)))

    def test_bilan_command_prints_the_review(self, db, capsys):
        self._listener(db).handle_coaching_command("bilan")
        assert "aucune partie analysée" in capsys.readouterr().out

    def test_axe_command_sets_a_goal_on_the_main_role(self, db, capsys):
        _store_history(db, "deaths_before_14", [2], z=0.0)

        self._listener(db).handle_coaching_command("axe deaths_before_14")

        assert "Nouvel axe" in capsys.readouterr().out
