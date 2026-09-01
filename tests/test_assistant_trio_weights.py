"""Characterization tests for the adaptive-weight / scoring-profile machinery
of ``Assistant`` (SPEC TODO E10 safety net).

Scope:
- ``_calculate_adaptive_base_weights``
- ``_get_profile_modifiers``
- ``_calculate_contextual_total_score``
- ``_generate_sample_trios_for_weights``
- ``set_scoring_profile``

Special attention is given to the CACHE INVALIDATION ASYMMETRY between the two
ways of choosing a profile — see ``TestScoringProfileCacheAsymmetry``. Both
paths must survive the extraction refactor unchanged.
"""

from unittest.mock import Mock, patch

import pytest

from src.assistant import Assistant
from tests.test_assistant_trio_classic import DELTAS

EQUAL_WEIGHTS = {"coverage": 0.25, "balance": 0.25, "consistency": 0.25, "meta": 0.25}


@pytest.fixture
def mock_db():
    """Mock DB good enough for the pure-weight code paths."""
    db = Mock()
    db.get_champion_matchups_by_name = Mock(return_value=[])
    db.get_all_matchups_bulk = Mock(return_value={})
    db.get_all_champion_names = Mock(return_value={})
    return db


@pytest.fixture
def assistant(mock_db):
    return Assistant(db=mock_db, verbose=False)


@pytest.fixture
def db_assistant(db, insert_matchup):
    """Assistant on the deterministic 6-champion universe of the classic tests."""
    for (champion, enemy), delta2 in DELTAS.items():
        insert_matchup(
            champion,
            enemy,
            winrate=50.0 + delta2,
            delta1=delta2 * 10,
            delta2=delta2,
            pickrate=5.0,
            games=1000,
        )
    return Assistant(db=db, verbose=False)


class TestGetProfileModifiers:
    """``_get_profile_modifiers(profile)`` — the profile catalogue."""

    def test_safe_profile(self, assistant):
        assert assistant._get_profile_modifiers("safe") == {
            "consistency": 1.8,
            "balance": 1.2,
            "coverage": 0.7,
            "meta": 0.3,
        }

    def test_meta_profile(self, assistant):
        assert assistant._get_profile_modifiers("meta") == {
            "meta": 2.0,
            "consistency": 1.3,
            "coverage": 0.8,
            "balance": 0.6,
        }

    def test_aggressive_profile(self, assistant):
        assert assistant._get_profile_modifiers("aggressive") == {
            "coverage": 1.5,
            "balance": 1.3,
            "consistency": 0.8,
            "meta": 0.7,
        }

    def test_balanced_profile_is_all_ones(self, assistant):
        assert assistant._get_profile_modifiers("balanced") == {
            "coverage": 1.0,
            "balance": 1.0,
            "consistency": 1.0,
            "meta": 1.0,
        }

    def test_default_argument_is_balanced(self, assistant):
        assert assistant._get_profile_modifiers() == assistant._get_profile_modifiers("balanced")

    def test_unknown_profile_falls_back_to_balanced(self, assistant):
        """No exception: an unknown name silently degrades to "balanced"."""
        assert assistant._get_profile_modifiers(
            "does-not-exist"
        ) == assistant._get_profile_modifiers("balanced")


class TestCalculateAdaptiveBaseWeights:
    """``_calculate_adaptive_base_weights(sample_trios)``."""

    def test_empty_sample_returns_equal_weights(self, assistant):
        assert assistant._calculate_adaptive_base_weights([]) == EQUAL_WEIGHTS

    def test_fewer_than_three_trios_returns_equal_weights(self, assistant):
        """The guard is ``len(sample_trios) < 3``, not the trio size."""
        trios = [("A", "B", "C"), ("D", "E", "F")]

        assert assistant._calculate_adaptive_base_weights(trios) == EQUAL_WEIGHTS

    def test_trios_without_db_data_fall_back_to_equal_weights(self, db_assistant):
        """No trio yields 3 matchup lists -> every variance defaults to 1.0,
        which normalizes back to 0.25 each."""
        trios = [("Nobody1", "Nobody2", "Nobody3")] * 4

        assert db_assistant._calculate_adaptive_base_weights(trios) == EQUAL_WEIGHTS

    def test_variance_analysis_on_real_data(self, db_assistant):
        """Pinned output of the variance analysis over the fixture universe.

        Weight per metric = variance(metric) / sum(variances). "balance" scores
        the same 100.0 on every one of these trios, so its variance — and thus
        its weight — is exactly 0.
        """
        trios = [
            ("Aatrox", "Darius", "Garen"),
            ("Teemo", "Malphite", "Sett"),
            ("Aatrox", "Teemo", "Sett"),
            ("Darius", "Garen", "Malphite"),
        ]

        weights = db_assistant._calculate_adaptive_base_weights(trios)

        assert weights["coverage"] == pytest.approx(0.3744887, abs=1e-6)
        assert weights["balance"] == 0.0
        assert weights["consistency"] == pytest.approx(0.2510225, abs=1e-6)
        assert weights["meta"] == pytest.approx(0.3744887, abs=1e-6)
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_is_deterministic_for_a_given_sample(self, db_assistant):
        """No randomness inside: same trios -> byte-identical weights."""
        trios = [
            ("Aatrox", "Darius", "Garen"),
            ("Teemo", "Malphite", "Sett"),
            ("Aatrox", "Teemo", "Sett"),
        ]

        assert db_assistant._calculate_adaptive_base_weights(
            trios
        ) == db_assistant._calculate_adaptive_base_weights(trios)

    def test_malformed_trios_are_skipped_not_raised(self, assistant):
        """A non-iterable "trio" is swallowed by the inner except -> equal weights."""
        assert assistant._calculate_adaptive_base_weights([1, 2, 3, 4]) == EQUAL_WEIGHTS


class TestCalculateContextualTotalScore:
    """``_calculate_contextual_total_score(scores, profile)``."""

    SCORES = {
        "coverage_score": 100.0,
        "balance_score": 100.0,
        "consistency_score": 100.0,
        "meta_score": 100.0,
    }

    def test_balanced_profile_keeps_the_base_weights(self, assistant):
        assistant._cached_base_weights = dict(EQUAL_WEIGHTS)

        total, weights = assistant._calculate_contextual_total_score(self.SCORES, "balanced")

        assert total == pytest.approx(100.0)
        assert weights == pytest.approx(EQUAL_WEIGHTS)

    def test_safe_profile_weights_are_base_times_modifier_renormalized(self, assistant):
        """0.25 * (0.7, 1.2, 1.8, 0.3) = (0.175, 0.30, 0.45, 0.075), sum 1.0."""
        assistant._cached_base_weights = dict(EQUAL_WEIGHTS)

        _, weights = assistant._calculate_contextual_total_score(self.SCORES, "safe")

        assert weights["coverage"] == pytest.approx(0.175)
        assert weights["balance"] == pytest.approx(0.30)
        assert weights["consistency"] == pytest.approx(0.45)
        assert weights["meta"] == pytest.approx(0.075)
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_meta_profile_weights(self, assistant):
        """0.25 * (0.8, 0.6, 1.3, 2.0) = (0.2, 0.15, 0.325, 0.5), sum 1.175."""
        assistant._cached_base_weights = dict(EQUAL_WEIGHTS)

        _, weights = assistant._calculate_contextual_total_score(self.SCORES, "meta")

        assert weights["coverage"] == pytest.approx(0.2 / 1.175)
        assert weights["balance"] == pytest.approx(0.15 / 1.175)
        assert weights["consistency"] == pytest.approx(0.325 / 1.175)
        assert weights["meta"] == pytest.approx(0.5 / 1.175)

    def test_aggressive_profile_weights(self, assistant):
        """0.25 * (1.5, 1.3, 0.8, 0.7) = (0.375, 0.325, 0.2, 0.175), sum 1.075."""
        assistant._cached_base_weights = dict(EQUAL_WEIGHTS)

        _, weights = assistant._calculate_contextual_total_score(self.SCORES, "aggressive")

        assert weights["coverage"] == pytest.approx(0.375 / 1.075)
        assert weights["balance"] == pytest.approx(0.325 / 1.075)
        assert weights["consistency"] == pytest.approx(0.2 / 1.075)
        assert weights["meta"] == pytest.approx(0.175 / 1.075)

    def test_total_score_is_the_weighted_sum(self, assistant):
        assistant._cached_base_weights = dict(EQUAL_WEIGHTS)
        scores = {
            "coverage_score": 80.0,
            "balance_score": 40.0,
            "consistency_score": 60.0,
            "meta_score": 20.0,
        }

        total, weights = assistant._calculate_contextual_total_score(scores, "safe")

        expected = 80 * 0.175 + 40 * 0.30 + 60 * 0.45 + 20 * 0.075
        assert total == pytest.approx(expected)

    def test_base_weights_are_computed_and_cached_on_first_call(self, assistant):
        """Missing cache -> sample trios are generated and the result memoized."""
        assert not hasattr(assistant, "_cached_base_weights")

        assistant._calculate_contextual_total_score(self.SCORES, "balanced")

        assert assistant._cached_base_weights == EQUAL_WEIGHTS

    def test_cached_weights_are_reused_not_recomputed(self, assistant):
        """A second call must not regenerate sample trios."""
        assistant._cached_base_weights = dict(EQUAL_WEIGHTS)

        with patch.object(assistant, "_generate_sample_trios_for_weights") as generate:
            assistant._calculate_contextual_total_score(self.SCORES, "balanced")

        generate.assert_not_called()

    def test_missing_score_key_falls_back_to_plain_average(self, assistant):
        """A KeyError inside is swallowed: total = mean(scores), equal weights."""
        assistant._cached_base_weights = dict(EQUAL_WEIGHTS)
        incomplete = {"coverage_score": 100.0, "balance_score": 0.0}

        total, weights = assistant._calculate_contextual_total_score(incomplete, "balanced")

        assert total == pytest.approx(50.0)
        assert weights == EQUAL_WEIGHTS


class TestGenerateSampleTriosForWeights:
    """``_generate_sample_trios_for_weights(sample_size)``."""

    def test_returns_empty_when_no_champion_has_enough_data(self, db_assistant):
        """The fixture universe shares no name with the constants role pools,
        so no champion clears the "> 10 matchups" bar."""
        assert db_assistant._generate_sample_trios_for_weights() == []

    def test_returns_sample_size_trios_when_data_is_available(self, assistant, mock_db):
        """13 sampled champions (3 top + 3 jungle + 3 mid + 2 adc + 2 support)
        -> C(13, 3) = 286 combinations, truncated to the requested sample."""
        mock_db.get_champion_matchups_by_name.return_value = [Mock()] * 11

        trios = assistant._generate_sample_trios_for_weights()

        assert len(trios) == 15
        assert all(len(trio) == 3 for trio in trios)
        assert all(isinstance(trio, tuple) for trio in trios)

    def test_sample_size_is_capped_by_available_combinations(self, assistant, mock_db):
        mock_db.get_champion_matchups_by_name.return_value = [Mock()] * 11

        trios = assistant._generate_sample_trios_for_weights(sample_size=1000)

        assert len(trios) == 286  # C(13, 3)

    def test_trios_have_no_duplicate_champion(self, assistant, mock_db):
        mock_db.get_champion_matchups_by_name.return_value = [Mock()] * 11

        trios = assistant._generate_sample_trios_for_weights(sample_size=50)

        assert all(len(set(trio)) == 3 for trio in trios)

    def test_exactly_ten_matchups_is_not_enough(self, assistant, mock_db):
        """The threshold is strict: ``len(matchups) > 10``."""
        mock_db.get_champion_matchups_by_name.return_value = [Mock()] * 10

        assert assistant._generate_sample_trios_for_weights() == []

    def test_db_failure_returns_empty_list(self, assistant, mock_db):
        mock_db.get_champion_matchups_by_name.side_effect = Exception("db down")

        assert assistant._generate_sample_trios_for_weights() == []


class TestSetScoringProfile:
    """``set_scoring_profile(profile)``."""

    @pytest.mark.parametrize("profile", ["safe", "meta", "aggressive", "balanced"])
    def test_valid_profile_is_stored(self, assistant, profile):
        assistant.set_scoring_profile(profile)

        assert assistant.scoring_profile == profile

    def test_invalid_profile_is_ignored_silently(self, assistant):
        """No exception, no attribute set — the call is simply a no-op."""
        assistant.set_scoring_profile("nonsense")

        assert not hasattr(assistant, "scoring_profile")

    def test_invalid_profile_does_not_clear_the_weight_cache(self, assistant):
        sentinel = dict(EQUAL_WEIGHTS)
        assistant._cached_base_weights = sentinel

        assistant.set_scoring_profile("nonsense")

        assert assistant._cached_base_weights is sentinel

    def test_invalid_profile_warns_only_in_verbose_mode(self, mock_db, capsys):
        Assistant(db=mock_db, verbose=False).set_scoring_profile("nonsense")
        assert capsys.readouterr().out == ""

        Assistant(db=mock_db, verbose=True).set_scoring_profile("nonsense")
        assert "[WARNING] Invalid profile 'nonsense'" in capsys.readouterr().out

    def test_no_cached_weights_yet_is_not_an_error(self, assistant):
        """The ``hasattr`` guard protects the ``delattr``."""
        assert not hasattr(assistant, "_cached_base_weights")

        assistant.set_scoring_profile("safe")  # must not raise

        assert not hasattr(assistant, "_cached_base_weights")


class TestScoringProfileCacheAsymmetry:
    """FROZEN ASYMMETRY — the two ways to pick a profile are NOT equivalent.

    ``set_scoring_profile()`` invalidates ``_cached_base_weights`` (hasattr +
    delattr), while passing ``profile=`` to ``find_optimal_trios_holistic()``
    only assigns ``self.scoring_profile`` and leaves the cache untouched.

    These are two distinct code paths. They are pinned separately here so the
    extraction refactor does not accidentally merge or align them.
    """

    POOL = ["Aatrox", "Ahri", "Jinx"]

    def test_set_scoring_profile_invalidates_the_cache(self, assistant):
        assistant._cached_base_weights = dict(EQUAL_WEIGHTS)

        assistant.set_scoring_profile("safe")

        assert not hasattr(assistant, "_cached_base_weights")

    def test_find_optimal_trios_holistic_does_not_invalidate_the_cache(self, assistant, mock_db):
        # Arrange: a recognizable cache entry
        sentinel = dict(EQUAL_WEIGHTS)
        assistant._cached_base_weights = sentinel

        # Act: choose a profile through the analysis entry point instead
        with patch.object(assistant, "_validate_champion_pool", return_value=(self.POOL, {})):
            assistant.find_optimal_trios_holistic(self.POOL, num_results=1, profile="safe")

        # Assert: the profile changed but the cached base weights survived
        assert assistant.scoring_profile == "safe"
        assert assistant._cached_base_weights is sentinel

    def test_find_optimal_trios_holistic_sets_the_profile_attribute(self, assistant):
        with patch.object(assistant, "_validate_champion_pool", return_value=(self.POOL, {})):
            assistant.find_optimal_trios_holistic(self.POOL, num_results=1, profile="aggressive")

        assert assistant.scoring_profile == "aggressive"

    def test_profile_from_holistic_survives_until_explicitly_changed(self, assistant):
        """The attribute is sticky: a later call without ``profile`` resets it
        to the default "balanced", since the argument has a default value."""
        with patch.object(assistant, "_validate_champion_pool", return_value=(self.POOL, {})):
            assistant.find_optimal_trios_holistic(self.POOL, num_results=1, profile="meta")
            assert assistant.scoring_profile == "meta"

            assistant.find_optimal_trios_holistic(self.POOL, num_results=1)

        assert assistant.scoring_profile == "balanced"
