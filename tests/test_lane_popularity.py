"""Tests de MatchupsRepository.get_lane_popularity (SPEC-17 §4.1)."""


def test_champions_ranked_by_total_games_on_the_lane(db, insert_matchup):
    # Strong gagne tous ses duels mais sur peu de games : il vient après Popular.
    insert_matchup("Popular", "Garen", 50.0, 0, 0, 10.0, 5000, lane="top")
    insert_matchup("Popular", "Darius", 50.0, 0, 0, 10.0, 4000, lane="top")
    insert_matchup("Strong", "Garen", 60.0, 0, 900, 0.5, 300, lane="top")
    insert_matchup("Average", "Garen", 50.0, 0, 0, 5.0, 6000, lane="top")

    assert db.get_lane_popularity("top") == ["Popular", "Average", "Strong"]


def test_other_lanes_do_not_count(db, insert_matchup):
    insert_matchup("Ahri", "Zed", 50.0, 0, 0, 10.0, 9000, lane="middle")
    insert_matchup("Garen", "Darius", 50.0, 0, 0, 10.0, 100, lane="top")

    assert db.get_lane_popularity("top") == ["Garen"]
    assert db.get_lane_popularity("jungle") == []
