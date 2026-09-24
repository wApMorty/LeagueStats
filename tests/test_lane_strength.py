"""SPEC-18 : la force d'un champion en blind pick est son winrate de lane rétréci.

``avg_delta2`` ne mesure rien à ce niveau : le delta2 de LoLalytics est un écart
à la moyenne du champion, et sa dispersion entre champions est du bruit pur.
Kassadin sortait 1er en top sur 606 parties.
"""

import pytest

from src.analysis.champion_scores import GlobalScoreCalculator
from src.analysis.shrink import shrunk_lane_winrates
from src.analysis.tier_list import TierListGenerator


class _FakeDb:
    def __init__(self, winrates):
        self._winrates = winrates

    def get_lane_winrates(self, lane):
        return self._winrates


class TestGetLaneWinrates:
    def test_weighted_by_games_and_scoped_to_lane(self, db, insert_matchup):
        insert_matchup("Garen", "Darius", 60.0, 0.0, 0.0, 10.0, 3000, lane="top")
        insert_matchup("Garen", "Teemo", 40.0, 0.0, 0.0, 10.0, 1000, lane="top")
        insert_matchup("Garen", "Ahri", 10.0, 0.0, 0.0, 10.0, 1000, lane="middle")

        winrate, games = db.get_lane_winrates("top")["Garen"]

        assert winrate == pytest.approx((60.0 * 3000 + 40.0 * 1000) / 4000)
        assert games == 4000

    def test_none_aggregates_every_lane(self, db, insert_matchup):
        insert_matchup("Garen", "Darius", 60.0, 0.0, 0.0, 10.0, 1000, lane="top")
        insert_matchup("Garen", "Ahri", 40.0, 0.0, 0.0, 10.0, 1000, lane="middle")

        assert db.get_lane_winrates(None)["Garen"] == (pytest.approx(50.0), 2000)


class TestShrunkLaneWinrates:
    def test_thin_sample_is_pulled_harder_toward_the_lane_mean(self):
        raw = {
            "Thin": (60.0, 100),
            "Thick": (60.0, 100_000),
            "Average": (52.0, 1_000_000),
        }

        shrunk = shrunk_lane_winrates(_FakeDb(raw), "top")

        assert shrunk["Thin"] < shrunk["Thick"] < 60.0
        assert shrunk["Thick"] == pytest.approx(60.0, abs=0.1)

    def test_shrinks_toward_lane_mean_not_fifty(self):
        """Les winrates LoLalytics sont à ~52,4 % en moyenne sur chaque lane :
        un champion sans échantillon doit valoir la moyenne, pas 50 %."""
        raw = {"Nobody": (70.0, 1), "Everyone": (53.0, 1_000_000)}

        shrunk = shrunk_lane_winrates(_FakeDb(raw), "top")

        assert shrunk["Nobody"] == pytest.approx(53.0, abs=0.1)

    def test_empty_lane_returns_empty(self):
        assert shrunk_lane_winrates(_FakeDb({}), "top") == {}


def test_tier_list_performance_ignores_avg_delta2_noise(db, scorer, insert_matchup):
    """Un delta2 spectaculaire sur un petit échantillon ne fait plus la
    performance : c'est le champion qui gagne, sur beaucoup de parties."""
    insert_matchup("Kassadin", "Darius", 52.0, 0.0, 8.0, 10.0, 300, lane="top")
    insert_matchup("Garen", "Darius", 55.0, 0.0, 0.0, 10.0, 20000, lane="top")
    insert_matchup("Teemo", "Darius", 49.0, 0.0, 0.0, 10.0, 20000, lane="top")
    db.init_champion_scores_table()
    GlobalScoreCalculator(db, scorer).calculate_all()

    tier_list = TierListGenerator(db, scorer).generate_tier_list(
        ["Kassadin", "Garen", "Teemo"], lane="top"
    )
    performance = {e["champion"]: e["metrics"]["avg_performance_norm"] for e in tier_list}

    assert performance["Garen"] > performance["Kassadin"] > performance["Teemo"]
