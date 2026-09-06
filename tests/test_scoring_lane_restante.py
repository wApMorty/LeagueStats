"""Integration tests: the SPEC-11 gate on ChampionScorer/score_against_team,
against a real database (never data/db.db -- the `db` fixture is temp_db).

Unlike tests/test_lane_restante.py (pure math on the blind_pick_contribution
formula), this file only checks the plumbing: does the gate actually stay
off below the threshold, does it flip on above it, does effective_model_
version() reflect that, and is the decision cached per ChampionScorer
instance rather than re-queried on every call.
"""

from src.analysis.scoring import ChampionScorer
from src.config_constants import analysis_config


def _label_n_predictions(db, n: int) -> None:
    for _ in range(n):
        prediction_id = db.insert_prediction([1], [2], None, 0.5, analysis_config.MODEL_VERSION)
        db.update_prediction_outcome(prediction_id, 1)


def _ensure_champion_lanes_table(db) -> None:
    """temp_db's shared schema (tests/conftest.py) doesn't include
    champion_lanes -- same pattern as tests/test_champion_lanes_table.py's
    own db_with_lanes fixture, duplicated here since it's file-local there."""
    db.connection.cursor().execute("""CREATE TABLE IF NOT EXISTS champion_lanes (
            champion INTEGER NOT NULL,
            lane TEXT NOT NULL,
            share REAL NOT NULL,
            PRIMARY KEY (champion, lane),
            FOREIGN KEY (champion) REFERENCES champions(id) ON DELETE CASCADE
        )""")
    db.connection.commit()


class TestGateStaysOffBelowThreshold:
    def test_effective_model_version_is_unsuffixed(self, db, scorer):
        _label_n_predictions(db, analysis_config.MIN_ROWS_FOR_CALIBRATION - 1)

        assert scorer.effective_model_version() == analysis_config.MODEL_VERSION

    def test_score_against_team_is_unaffected_by_player_lane(self, db, scorer, insert_matchup):
        """With the gate off, passing player_lane/enemy_lanes must produce
        the exact same score as not passing them at all -- SPEC-11 is a true
        no-op below the threshold, not just "close"."""
        insert_matchup("Aatrox", "Darius", 55.0, 300, 3.0, 10.0, 1000)
        matchups = db.get_champion_matchups_by_name("Aatrox")

        with_lane = scorer.score_against_team(
            matchups,
            ["Darius"],
            champion_name="Aatrox",
            player_lane="top",
            enemy_lanes={},
        )
        without_lane = scorer.score_against_team(matchups, ["Darius"], champion_name="Aatrox")

        assert with_lane == without_lane


class TestGateTurnsOnAtThreshold:
    def test_effective_model_version_is_suffixed(self, db, scorer):
        _label_n_predictions(db, analysis_config.MIN_ROWS_FOR_CALIBRATION)

        assert scorer.effective_model_version() == f"{analysis_config.MODEL_VERSION}+lane-restante"

    def test_score_against_team_changes_when_our_lane_is_still_open(
        self, db, scorer, insert_matchup
    ):
        """One known enemy (lane unknown to us) plus two candidate future
        picks with opposite matchups, one much more likely to land in our
        lane than the other (champion_lanes.share): with the gate on, the
        blind dilution must lean toward the plausible one instead of a flat
        average -- reproducing the scenario documented in SPEC-11 §1.

        Zed (+10 delta2) and Yasuo (-10 delta2) are built to cancel exactly
        under the old flat average (equal pickrate/games), and no matchup
        data is inserted for the known enemy "Garen" -- with the gate off,
        every contribution here is exactly 0.0 by construction, isolating
        whatever the lane-conditioned math adds once the gate is on.
        """
        _label_n_predictions(db, analysis_config.MIN_ROWS_FOR_CALIBRATION)
        _ensure_champion_lanes_table(db)
        insert_matchup("Ahri", "Zed", 50.0, 0, 10.0, 10.0, 1000)
        insert_matchup("Ahri", "Yasuo", 50.0, 0, -10.0, 10.0, 1000)

        cursor = db.connection.cursor()
        zed_id = cursor.execute("SELECT id FROM champions WHERE name = 'Zed'").fetchone()[0]
        yasuo_id = cursor.execute("SELECT id FROM champions WHERE name = 'Yasuo'").fetchone()[0]
        db.save_champion_lane_distribution(zed_id, {"top": 5.0, "middle": 80.0})
        db.save_champion_lane_distribution(yasuo_id, {"top": 70.0, "middle": 20.0})

        matchups = db.get_champion_matchups_by_name("Ahri")
        gated_score = scorer.score_against_team(
            matchups,
            ["Garen"],
            champion_name="Ahri",
            player_lane="top",
            enemy_lanes={},
        )

        assert gated_score != 0.0


class TestGateIsCachedPerInstance:
    def test_crossing_the_threshold_after_construction_does_not_flip_a_live_instance(
        self, db, scorer
    ):
        _label_n_predictions(db, analysis_config.MIN_ROWS_FOR_CALIBRATION - 1)
        assert scorer.effective_model_version() == analysis_config.MODEL_VERSION  # caches "off"

        _label_n_predictions(db, 5)  # now well past the threshold

        assert scorer.effective_model_version() == analysis_config.MODEL_VERSION  # still cached

    def test_a_new_instance_sees_the_up_to_date_count(self, db):
        _label_n_predictions(db, analysis_config.MIN_ROWS_FOR_CALIBRATION)

        assert (
            ChampionScorer(db, verbose=False).effective_model_version()
            == f"{analysis_config.MODEL_VERSION}+lane-restante"
        )
