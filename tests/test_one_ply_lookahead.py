"""Tests for src/analysis/one_ply_lookahead.py (SPEC-11 étage b, "1 ply glouton").

worst_case_term() is a pure function (no DB access, everything comes from
`available_matchups` already loaded by the caller) -- exercised via a real
ChampionScorer(Mock()) since filter_valid_matchups touches no DB.

The property under test throughout is monotonicity: a first version of this
module simulated "add the enemy's worst plausible pick to the known team and
re-score", which turned out to be NON-monotone on this codebase's blind-pick
dilution formula -- removing an outlier from the "unknown" pool can raise the
average of what's left enough to make the final score *better*, the opposite
of a worst-case guarantee (discovered empirically while writing this file's
first draft, not assumed). The additive term implemented instead is provably
monotone: min/mean of a subset is always <= the mean of the full set, so
adding it can only degrade or leave the score unchanged.
"""

from unittest.mock import Mock

import pytest

from src.analysis.one_ply_lookahead import worst_case_term
from src.config_constants import analysis_config
from src.models import Matchup

MATCHUPS = [
    Matchup(enemy_name="Garen", winrate=55.0, delta1=0.0, delta2=5.0, pickrate=10.0, games=1000),
    Matchup(enemy_name="Zed", winrate=30.0, delta1=0.0, delta2=-20.0, pickrate=10.0, games=1000),
    Matchup(enemy_name="Yasuo", winrate=40.0, delta1=0.0, delta2=-10.0, pickrate=10.0, games=1000),
    Matchup(enemy_name="LeeSin", winrate=60.0, delta1=0.0, delta2=8.0, pickrate=10.0, games=1000),
    # Worst raw delta2 in the fixture, but pickrate below MIN_PICKRATE --
    # must be excluded by filter_valid_matchups despite being the "worst".
    Matchup(
        enemy_name="Malphite", winrate=45.0, delta1=0.0, delta2=-30.0, pickrate=0.1, games=1000
    ),
]


@pytest.fixture
def mock_scorer():
    """No DB access needed: worst_case_term() only touches
    filter_valid_matchups (pure). The real, db-backed `scorer` fixture from
    conftest.py is reserved for TestScoreAgainstTeamMonotonicity below,
    which needs a working SPEC-11 gate."""
    from src.analysis.scoring import ChampionScorer

    return ChampionScorer(Mock(), verbose=False)


class TestWorstCaseTerm:
    def test_averages_the_top_k_worst_plausible_deltas(self, mock_scorer):
        # Sorted plausible (Malphite excluded by pickrate): Zed(-20), Yasuo(-10), Garen(5), LeeSin(8)
        delta2, weight = worst_case_term(mock_scorer, MATCHUPS, top_k=2)

        assert delta2 == pytest.approx((-20.0 + -10.0) / 2)
        assert weight == analysis_config.LOOKAHEAD_WEIGHT

    def test_top_k_one_is_the_single_worst(self, mock_scorer):
        delta2, _weight = worst_case_term(mock_scorer, MATCHUPS, top_k=1)
        assert delta2 == pytest.approx(-20.0)

    def test_ignores_matchups_below_min_pickrate(self, mock_scorer):
        """Malphite's -30 is the worst raw delta2 in the fixture but must
        never surface here -- filter_valid_matchups excludes it first."""
        delta2, _weight = worst_case_term(mock_scorer, MATCHUPS, top_k=1)
        assert delta2 != pytest.approx(-30.0)

    def test_top_k_larger_than_the_pool_uses_every_plausible_candidate(self, mock_scorer):
        delta2, _weight = worst_case_term(mock_scorer, MATCHUPS, top_k=100)
        assert delta2 == pytest.approx((-20.0 - 10.0 + 5.0 + 8.0) / 4)

    def test_no_plausible_candidate_returns_zero_weight(self, mock_scorer):
        below_threshold = [
            Matchup(
                enemy_name="Teemo", winrate=50, delta1=0, delta2=-99.0, pickrate=0.1, games=1000
            )
        ]
        delta2, weight = worst_case_term(mock_scorer, below_threshold, top_k=3)
        assert (delta2, weight) == (0.0, 0.0)

    def test_the_term_is_never_better_than_the_pool_average(self, mock_scorer):
        """The property that makes this monotone: the worst-K average can
        never exceed (be better than) the plain average of the same pool --
        the whole reason it's safe to only ever ADD this term."""
        worst_delta2, _weight = worst_case_term(mock_scorer, MATCHUPS, top_k=2)
        plain_avg = mock_scorer.avg_delta2(MATCHUPS)
        assert worst_delta2 <= plain_avg


class TestScoreAgainstTeamMonotonicity:
    """Integration: once the SPEC-11 gate is on, score_against_team() must
    never rate a candidate better than it would with the gate off, for the
    exact same inputs -- this is the invariant the additive design
    guarantees and the earlier "resimulate with team extended" approach
    violated."""

    def test_gated_score_is_never_better_than_the_ungated_score(self, db, scorer, insert_matchup):
        for _ in range(analysis_config.MIN_ROWS_FOR_CALIBRATION):
            pid = db.insert_prediction([1], [2], None, 0.5, analysis_config.MODEL_VERSION)
            db.update_prediction_outcome(pid, 1)

        insert_matchup("Ahri", "Garen", 55.0, 300, 5.0, 10.0, 1000)
        matchups = db.get_champion_matchups_by_name("Ahri")

        from src.analysis.scoring import ChampionScorer

        ungated_scorer = ChampionScorer(db, verbose=False)
        ungated_scorer._lane_restante_enabled = False  # force the pre-SPEC-11 path
        ungated = ungated_scorer.score_against_team(matchups, ["Garen"], champion_name="Ahri")

        gated = scorer.score_against_team(matchups, ["Garen"], champion_name="Ahri")

        assert gated <= ungated
