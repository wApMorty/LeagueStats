"""Tests de src/analysis/strategy.py (SPEC-46, tâche 223).

Le point qui compte : à poids 1, `WeightedEvaluator` reproduit `GameEvaluator` bit à bit,
pour que la stratégie « Complet » garde le classement d'avant SPEC-46.
"""

from unittest.mock import Mock

import pytest

from src.analysis.game_eval import GameEvaluator
from src.analysis.strategy import (
    SYSTEM_STRATEGIES,
    Strategy,
    WeightedEvaluator,
    all_strategies,
    find_strategy,
    parse_strategies,
    strategy_from_dict,
    strategy_of,
    strategy_to_dict,
)
from src.config_constants import draft_config


class FakeDB:
    """Tables factices pour `GameEvaluator`, toutes lanes confondues sauf la force."""

    def __init__(self, matchups=None, synergies=None, winrates=None):
        self.matchups = matchups or {}
        self.synergies = synergies or {}
        self.winrates = winrates or {}

    def get_all_matchups_bulk(self, lane=None, with_games=False):
        return self.matchups

    def get_all_synergies_bulk(self, lane=None, with_games=False):
        return self.synergies

    def get_lane_winrates(self, lane):
        return self.winrates.get(lane, {})

    def get_meta(self, key):
        return None


@pytest.fixture
def base():
    return GameEvaluator(
        FakeDB(
            matchups={
                ("jax", "garen"): (6.0, 10_000),
                ("garen", "jax"): (-2.0, 10_000),
                ("jax", "amumu"): (3.0, 10_000),
                ("nautilus", "garen"): (-4.0, 10_000),
            },
            synergies={
                ("jax", "nautilus"): (4.0, 10_000),
                ("garen", "amumu"): (2.0, 10_000),
            },
            winrates={
                "top": {"jax": (53.0, 5_000), "garen": (51.0, 5_000)},
                None: {"jax": (53.0, 5_000), "garen": (51.0, 5_000)},
            },
        )
    )


ALLIES = [("Jax", "top"), ("Nautilus", "support")]
ENEMIES = [("Garen", "top"), ("Amumu", "jungle"), ("Nautilus", None)]


def _strategy(**weights):
    return Strategy("Test", **weights)


class TestWeightedEvaluator:
    def test_parts_sum_to_contribution(self, base):
        weighted = WeightedEvaluator(base, _strategy(force=0.5, duel=2.0, other=0.3, synergy=1.5))
        for champion in ALLIES:
            parts = weighted.parts(champion, ALLIES[:1], ENEMIES)
            assert sum(parts.values()) == pytest.approx(
                weighted.contribution(champion, ALLIES[:1], ENEMIES)
            )

    def test_zero_weight_removes_the_term(self, base):
        no_duel = WeightedEvaluator(base, _strategy(duel=0.0))
        parts = no_duel.parts(("Jax", "top"), (), ENEMIES)
        assert parts["duel"] == 0.0
        assert parts["other"] != 0.0

        no_force = WeightedEvaluator(base, _strategy(force=0.0))
        assert no_force.parts(("Jax", "top"), (), ENEMIES)["force"] == 0.0

        no_synergy = WeightedEvaluator(base, _strategy(synergy=0.0))
        assert no_synergy.parts(("Jax", "top"), ALLIES, ENEMIES)["synergy"] == 0.0

    def test_same_lane_is_duel_other_lane_is_other(self, base):
        weighted = WeightedEvaluator(base, _strategy())
        parts = weighted.parts(("Jax", "top"), (), [("Garen", "top"), ("Amumu", "jungle")])
        assert parts["duel"] == pytest.approx(base.matchup_logit(("Jax", "top"), ("Garen", "top")))
        assert parts["other"] == pytest.approx(
            base.matchup_logit(("Jax", "top"), ("Amumu", "jungle"))
        )

    def test_unknown_lane_counts_as_other(self, base):
        weighted = WeightedEvaluator(base, _strategy(duel=0.0, other=1.0))
        parts = weighted.parts(("Jax", None), (), [("Garen", None)])
        assert parts["duel"] == 0.0
        assert parts["other"] == pytest.approx(base.matchup_logit(("Jax", None), ("Garen", None)))

    def test_team_logit_is_antisymmetric(self, base):
        weighted = WeightedEvaluator(base, _strategy(force=0.5, duel=2.0, other=0.3, synergy=1.5))
        assert weighted.team_logit(ALLIES, ENEMIES) == pytest.approx(
            -weighted.team_logit(ENEMIES, ALLIES)
        )

    def test_contribution_order_does_not_matter(self, base):
        weighted = WeightedEvaluator(base, _strategy(force=0.5, duel=2.0, other=0.3, synergy=1.5))
        picks = [("Jax", "top"), ("Nautilus", "support"), ("Garen", "jungle")]
        total = 0.0
        for index, champion in enumerate(picks):
            total += weighted.contribution(champion, picks[:index], ())
        assert total == pytest.approx(weighted.team_logit(picks, ()))

    def test_unit_weights_match_game_evaluator_exactly(self, base):
        complet = next(s for s in SYSTEM_STRATEGIES if s.name == "Complet")
        weighted = WeightedEvaluator(base, complet)
        for champion in ALLIES:
            assert weighted.contribution(champion, ALLIES[:1], ENEMIES) == (
                base.contribution(champion, ALLIES[:1], ENEMIES)
            )
        assert weighted.team_logit(ALLIES, ENEMIES) == base.team_logit(ALLIES, ENEMIES)
        assert weighted.probability(1.3) == base.probability(1.3)


class TestStrategyFromDict:
    @staticmethod
    def _raw(**overrides):
        raw = {
            "name": "Ma stratégie",
            "force": 1.0,
            "duel": 2.0,
            "other": 0.0,
            "synergy": 0.5,
            "mastery": 3.0,
            "search": True,
        }
        raw.update(overrides)
        return raw

    def test_valid_entry_round_trips(self):
        strategy = strategy_from_dict(self._raw())
        assert strategy == Strategy(
            "Ma stratégie", 1.0, 2.0, 0.0, 0.5, 3.0, search=True, system=False
        )
        assert strategy_from_dict(strategy_to_dict(strategy)) == strategy

    @pytest.mark.parametrize(
        "overrides, message",
        [
            ({"name": None}, "texte"),
            ({"name": 42}, "texte"),
            ({"name": "   "}, "vide"),
            ({"name": "x" * (draft_config.STRATEGY_NAME_MAX + 1)}, "caractères"),
            ({"name": "counter"}, "base"),
            ({"name": "COMPLET"}, "base"),
            ({"force": None}, "absent"),
            ({"duel": True}, "nombre"),
            ({"other": "1"}, "nombre"),
            ({"synergy": float("nan")}, "fini"),
            ({"mastery": float("inf")}, "fini"),
            ({"mastery": -0.5}, "entre 0"),
            ({"force": draft_config.STRATEGY_WEIGHT_MAX + 0.5}, "entre 0"),
            ({"force": 0, "duel": 0, "other": 0, "synergy": 0, "mastery": 0}, "non nul"),
        ],
    )
    def test_each_refusal_raises_value_error(self, overrides, message):
        with pytest.raises(ValueError, match=message):
            strategy_from_dict(self._raw(**overrides))

    def test_bool_weight_is_refused_explicitly(self):
        with pytest.raises(ValueError):
            strategy_from_dict(self._raw(mastery=True))

    def test_weight_bounds_are_inclusive(self):
        strategy = strategy_from_dict(
            self._raw(force=0, duel=draft_config.STRATEGY_WEIGHT_MAX, other=0.0, synergy=0)
        )
        assert strategy.duel == draft_config.STRATEGY_WEIGHT_MAX

    def test_name_is_stripped(self):
        assert strategy_from_dict(self._raw(name="  Vite  ")).name == "Vite"


class TestParseStrategies:
    def test_non_list_gives_empty(self):
        assert parse_strategies(None) == []
        assert parse_strategies({"name": "Simple"}) == []

    def test_invalid_entry_is_dropped_and_healthy_ones_kept(self):
        raw = [
            {"name": "Bonne", "force": 1, "duel": 1, "other": 1, "synergy": 1, "mastery": 1},
            {"name": "Cassée", "force": "x"},
            "pas un dict",
            {"name": "Simple", "force": 1, "duel": 1, "other": 1, "synergy": 1, "mastery": 1},
        ]
        names = [strategy.name for strategy in parse_strategies(raw)]
        assert names == ["Bonne"]

    def test_duplicate_name_ignoring_case_is_dropped(self):
        entry = {"force": 1, "duel": 1, "other": 1, "synergy": 1, "mastery": 1}
        raw = [{**entry, "name": "Vite"}, {**entry, "name": "VITE", "duel": 2}]
        strategies = parse_strategies(raw)
        assert [s.name for s in strategies] == ["Vite"]
        assert strategies[0].duel == 1.0


class TestFindStrategy:
    def test_finds_system_and_custom_ignoring_case(self):
        custom = [Strategy("Vite", duel=2.0)]
        assert find_strategy("counter", custom).name == "Counter"
        assert find_strategy("VITE", custom) is custom[0]

    def test_unknown_or_missing_name_falls_back_to_default(self):
        default = draft_config.STRATEGY_DEFAULT
        assert find_strategy("inconnue", []).name == default
        assert find_strategy(None, []).name == default
        assert find_strategy("inconnue", []).system is True

    def test_all_strategies_lists_system_then_custom(self):
        custom = [Strategy("Vite")]
        names = [s.name for s in all_strategies(custom)]
        assert names == ["Simple", "Counter", "Méta", "Complet", "Vite"]

    def test_strategy_of_reads_monitor_attribute_or_defaults(self):
        monitor = Mock()
        monitor.strategy = Strategy("Vite")
        assert strategy_of(monitor) is monitor.strategy
        assert strategy_of(Mock()).name == draft_config.STRATEGY_DEFAULT


class TestSystemStrategies:
    def test_order_and_names(self):
        assert [s.name for s in SYSTEM_STRATEGIES] == ["Simple", "Counter", "Méta", "Complet"]
        assert all(s.system for s in SYSTEM_STRATEGIES)

    def test_only_complet_is_calibrated_and_searches(self):
        calibrated = [s.name for s in SYSTEM_STRATEGIES if s.is_calibrated]
        searching = [s.name for s in SYSTEM_STRATEGIES if s.search]
        assert calibrated == ["Complet"]
        assert searching == ["Complet"]
