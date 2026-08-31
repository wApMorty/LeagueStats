"""Tests de la politique unique d'agrégation multi-lane (SPEC-03, item B1).

Le module `src/analysis/aggregation.py` est le seul endroit du projet où l'on
décide comment fusionner plusieurs lignes de lane pour un même couple de
champions. Ces tests figent les trois règles :

- delta2 / winrate / delta1 : moyenne pondérée par `games`
- games : somme
- pickrate : somme

Créé : 2026-08-31 — SPEC-03 / B1
"""

import pytest

from src.analysis.aggregation import (
    MAX_PERCENT,
    AggregatedRow,
    aggregate_full_rows,
    aggregate_pairs,
    aggregate_rows,
    weighted_delta2,
)


class TestWeightedDelta2:
    """`weighted_delta2` : la brique de base, sur des lignes (delta2, games)."""

    def test_weighted_average_by_games(self):
        rows = [(10.0, 100), (0.0, 300)]
        # (10*100 + 0*300) / 400 = 2.5
        assert weighted_delta2(rows) == pytest.approx(2.5)

    def test_single_row_returns_its_value(self):
        assert weighted_delta2([(-4.25, 800)]) == pytest.approx(-4.25)

    def test_empty_returns_none(self):
        assert weighted_delta2([]) is None

    def test_all_games_zero_falls_back_to_simple_mean(self):
        """Pondération impossible : moyenne simple plutôt que perte de données."""
        assert weighted_delta2([(4.0, 0), (6.0, 0)]) == pytest.approx(5.0)

    def test_negative_deltas_are_preserved(self):
        rows = [(-10.0, 200), (2.0, 600)]
        # (-2000 + 1200) / 800 = -1.0
        assert weighted_delta2(rows) == pytest.approx(-1.0)


class TestAggregateRows:
    """`aggregate_rows` : lignes draft (peer_name, delta2, pickrate, games)."""

    def test_multi_lane_pair_is_aggregated(self):
        rows = [
            ("Zed", 10.0, 3.0, 100),
            ("Zed", 0.0, 2.0, 300),
        ]
        result = aggregate_rows(rows)

        assert list(result) == ["zed"]
        entry = result["zed"]
        assert entry.peer_name == "Zed"
        assert entry.delta2 == pytest.approx(2.5)  # pondéré par games
        assert entry.pickrate == pytest.approx(5.0)  # sommé
        assert entry.games == 400  # sommé
        assert entry.winrate is None and entry.delta1 is None

    def test_distinct_peers_are_kept_separate_in_first_seen_order(self):
        rows = [
            ("Zed", 1.0, 1.0, 10),
            ("Ahri", 2.0, 1.0, 10),
            ("Zed", 3.0, 1.0, 10),
        ]
        assert list(aggregate_rows(rows)) == ["zed", "ahri"]

    def test_keys_are_lowercase_and_display_name_is_first_seen(self):
        result = aggregate_rows([("MissFortune", 1.0, 1.0, 10), ("missfortune", 3.0, 1.0, 10)])

        assert list(result) == ["missfortune"]
        assert result["missfortune"].peer_name == "MissFortune"
        assert result["missfortune"].delta2 == pytest.approx(2.0)

    def test_single_row_is_unchanged(self):
        result = aggregate_rows([("Zed", 7.5, 4.2, 900)])

        assert result["zed"] == AggregatedRow("Zed", 7.5, 4.2, 900, None, None)

    def test_games_zero_uses_simple_mean(self):
        result = aggregate_rows([("Zed", 4.0, 1.0, 0), ("Zed", 6.0, 1.0, 0)])

        assert result["zed"].delta2 == pytest.approx(5.0)
        assert result["zed"].games == 0

    def test_empty_input(self):
        assert aggregate_rows([]) == {}

    def test_pickrate_sum_is_capped_at_100(self):
        """Les dataclasses de src/models.py valident pickrate dans [0, 100]."""
        rows = [("Zed", 1.0, 60.0, 100), ("Zed", 1.0, 55.0, 100)]

        assert aggregate_rows(rows)["zed"].pickrate == MAX_PERCENT


class TestAggregateFullRows:
    """`aggregate_full_rows` : lignes 6 colonnes (avec winrate et delta1)."""

    def test_all_metrics_are_games_weighted(self):
        rows = [
            ("Zed", 60.0, 100.0, 10.0, 3.0, 100),
            ("Zed", 50.0, 0.0, 0.0, 2.0, 300),
        ]
        entry = aggregate_full_rows(rows)["zed"]

        assert entry.winrate == pytest.approx(52.5)  # (60*100 + 50*300) / 400
        assert entry.delta1 == pytest.approx(25.0)  # (100*100 + 0*300) / 400
        assert entry.delta2 == pytest.approx(2.5)
        assert entry.pickrate == pytest.approx(5.0)
        assert entry.games == 400

    def test_single_row_is_unchanged(self):
        entry = aggregate_full_rows([("Zed", 52.0, 80.0, 150.0, 4.0, 1200)])["zed"]

        assert (entry.winrate, entry.delta1, entry.delta2) == (52.0, 80.0, 150.0)

    def test_empty_input(self):
        assert aggregate_full_rows([]) == {}


class TestAggregatePairs:
    """`aggregate_pairs` : caches bulk (name_a, name_b, delta2, games)."""

    def test_pair_key_is_lowercase_and_value_is_weighted(self):
        rows = [
            ("Annie", "Lux", 10.0, 100),
            ("Annie", "Lux", 0.0, 300),
            ("Annie", "Zed", 5.0, 200),
        ]
        result = aggregate_pairs(rows)

        assert result[("annie", "lux")] == pytest.approx(2.5)
        assert result[("annie", "zed")] == pytest.approx(5.0)

    def test_direction_matters(self):
        """(A, B) et (B, A) sont deux entrées distinctes."""
        result = aggregate_pairs([("Annie", "Lux", 3.0, 100), ("Lux", "Annie", -3.0, 100)])

        assert result[("annie", "lux")] == pytest.approx(3.0)
        assert result[("lux", "annie")] == pytest.approx(-3.0)

    def test_empty_input(self):
        assert aggregate_pairs([]) == {}
