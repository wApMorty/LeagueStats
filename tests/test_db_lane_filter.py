"""Tests pour le filtrage par lane des accesseurs de lecture (SPEC-03, item B2).

Chaque accesseur de `src/db.py` accepte désormais un paramètre `lane` optionnel :
- `lane=None` : agrégation toutes lanes confondues (comportement post-B1, inchangé).
- `lane="top"` (ou autre) : ne retient que les lignes de cette lane avant agrégation.
- Une lane inexistante pour la paire demandée renvoie une liste vide / None,
  jamais une exception.

Créé : 2026-08-31 — SPEC-03 / B2
"""

import pytest

from src.analysis.scoring import ChampionScorer
from src.db import Database


@pytest.fixture
def lane_db(tmp_path):
    """Base avec schéma de production (via les méthodes d'init de Database)."""
    db_path = tmp_path / "lane_filter_test.db"
    database = Database(str(db_path))
    database.connect()

    cursor = database.connection.cursor()
    cursor.execute("""CREATE TABLE champions (
            id INTEGER PRIMARY KEY,
            key TEXT,
            name TEXT NOT NULL,
            title TEXT
        )""")
    for champ_id, name in [
        (1, "Pantheon"),
        (2, "Yasuo"),
        (3, "Darius"),
        (4, "Leona"),
    ]:
        cursor.execute("INSERT INTO champions (id, name) VALUES (?, ?)", (champ_id, name))
    database.connection.commit()

    database.init_matchups_table()
    database.init_synergies_table()

    # Matchups : Pantheon vs Yasuo existe sur top ET support, avec des valeurs
    # opposées — si le filtrage lane échoue et retombe sur l'agrégation
    # complète, ces tests le détectent immédiatement.
    database.add_matchups_batch([("Pantheon", "Yasuo", 55.0, 20.0, 30.0, 3.0, 1000)], lane="top")
    database.add_matchups_batch(
        [("Pantheon", "Yasuo", 45.0, -10.0, -8.0, 1.0, 500)], lane="support"
    )
    database.add_matchups_batch([("Pantheon", "Darius", 52.0, 5.0, 5.0, 2.0, 800)], lane="top")
    # Perspective inverse, pour get_reverse_matchups_for_draft et le calcul
    # bidirectionnel : Yasuo (picker) vs Pantheon, sur deux lanes distinctes.
    database.add_matchups_batch([("Yasuo", "Pantheon", 50.0, 2.0, 3.0, 4.0, 1200)], lane="top")
    database.add_matchups_batch(
        [("Yasuo", "Pantheon", 60.0, 30.0, 40.0, 4.0, 1200)], lane="support"
    )

    # Synergies : Pantheon + Leona, top vs support, valeurs opposées.
    database.add_synergies_batch([("Pantheon", "Leona", 58.0, 10.0, -5.0, 1.0, 300)], lane="top")
    database.add_synergies_batch(
        [("Pantheon", "Leona", 62.0, 25.0, 15.0, 2.0, 600)], lane="support"
    )

    yield database
    database.close()


class TestGetChampionMatchupsByNameLane:
    def test_lane_filters_to_matching_rows_only(self, lane_db):
        top = lane_db.get_champion_matchups_by_name("Pantheon", lane="top")
        by_enemy = {m.enemy_name: m for m in top}
        assert set(by_enemy) == {"Yasuo", "Darius"}
        assert by_enemy["Yasuo"].delta2 == pytest.approx(30.0)

    def test_lane_with_single_matching_enemy(self, lane_db):
        support = lane_db.get_champion_matchups_by_name("Pantheon", lane="support")
        assert {m.enemy_name for m in support} == {"Yasuo"}
        assert support[0].delta2 == pytest.approx(-8.0)

    def test_nonexistent_lane_returns_empty_list(self, lane_db):
        assert lane_db.get_champion_matchups_by_name("Pantheon", lane="jungle") == []

    def test_lane_none_keeps_full_aggregation(self, lane_db):
        all_lanes = lane_db.get_champion_matchups_by_name("Pantheon")
        by_enemy = {m.enemy_name: m for m in all_lanes}
        expected = (30.0 * 1000 + (-8.0) * 500) / 1500
        assert by_enemy["Yasuo"].delta2 == pytest.approx(expected)


class TestGetChampionMatchupsForDraftLane:
    def test_lane_filters(self, lane_db):
        top = lane_db.get_champion_matchups_for_draft("Pantheon", lane="top")
        assert {m.enemy_name for m in top} == {"Yasuo", "Darius"}

    def test_nonexistent_lane_returns_empty_list(self, lane_db):
        assert lane_db.get_champion_matchups_for_draft("Pantheon", lane="jungle") == []


class TestGetReverseMatchupsForDraftLane:
    def test_lane_filters_to_picker_lane(self, lane_db):
        """Filtre sur la lane du picker (Yasuo), cf. SPEC-03 §3/B2."""
        top = lane_db.get_reverse_matchups_for_draft("Pantheon", lane="top")
        assert len(top) == 1
        assert top[0].enemy_name == "Yasuo"
        assert top[0].delta2 == pytest.approx(3.0)

        support = lane_db.get_reverse_matchups_for_draft("Pantheon", lane="support")
        assert support[0].delta2 == pytest.approx(40.0)

    def test_nonexistent_lane_returns_empty_list(self, lane_db):
        assert lane_db.get_reverse_matchups_for_draft("Pantheon", lane="jungle") == []


class TestGetChampionSynergiesByNameLane:
    def test_lane_filters(self, lane_db):
        top = lane_db.get_champion_synergies_by_name("Pantheon", lane="top")
        assert len(top) == 1
        assert top[0].ally_name == "Leona"
        assert top[0].delta2 == pytest.approx(-5.0)

        support = lane_db.get_champion_synergies_by_name("Pantheon", lane="support")
        assert support[0].delta2 == pytest.approx(15.0)

    def test_nonexistent_lane_returns_empty_list(self, lane_db):
        assert lane_db.get_champion_synergies_by_name("Pantheon", lane="jungle") == []

    def test_lane_none_keeps_full_aggregation(self, lane_db):
        all_lanes = lane_db.get_champion_synergies_by_name("Pantheon")
        expected = (-5.0 * 300 + 15.0 * 600) / 900
        assert all_lanes[0].delta2 == pytest.approx(expected)


class TestGetMatchupDelta2Lane:
    def test_lane_filters(self, lane_db):
        assert lane_db.get_matchup_delta2("Pantheon", "Yasuo", lane="top") == pytest.approx(30.0)
        assert lane_db.get_matchup_delta2("Pantheon", "Yasuo", lane="support") == pytest.approx(
            -8.0
        )

    def test_nonexistent_lane_returns_none(self, lane_db):
        assert lane_db.get_matchup_delta2("Pantheon", "Yasuo", lane="jungle") is None

    def test_lane_none_matches_bulk_and_full_aggregation(self, lane_db):
        expected = (30.0 * 1000 + (-8.0) * 500) / 1500
        assert lane_db.get_matchup_delta2("Pantheon", "Yasuo") == pytest.approx(expected)


class TestGetAllMatchupsBulkLane:
    def test_lane_filters_before_aggregation(self, lane_db):
        top_bulk = lane_db.get_all_matchups_bulk(lane="top")
        assert top_bulk[("pantheon", "yasuo")] == pytest.approx(30.0)
        assert ("pantheon", "yasuo") in top_bulk

        support_bulk = lane_db.get_all_matchups_bulk(lane="support")
        assert support_bulk[("pantheon", "yasuo")] == pytest.approx(-8.0)
        # Darius n'a pas de ligne support : absent du bulk filtré.
        assert ("pantheon", "darius") not in support_bulk

    def test_nonexistent_lane_returns_empty_dict(self, lane_db):
        assert lane_db.get_all_matchups_bulk(lane="jungle") == {}

    def test_lane_none_matches_unitaire(self, lane_db):
        bulk = lane_db.get_all_matchups_bulk()
        unitaire = lane_db.get_matchup_delta2("Pantheon", "Yasuo")
        assert bulk[("pantheon", "yasuo")] == pytest.approx(unitaire)


class TestGetSynergyDelta2Lane:
    def test_lane_filters(self, lane_db):
        assert lane_db.get_synergy_delta2("Pantheon", "Leona", lane="top") == pytest.approx(-5.0)
        assert lane_db.get_synergy_delta2("Pantheon", "Leona", lane="support") == pytest.approx(
            15.0
        )

    def test_nonexistent_lane_returns_none(self, lane_db):
        assert lane_db.get_synergy_delta2("Pantheon", "Leona", lane="jungle") is None


class TestGetAllSynergiesBulkLane:
    def test_lane_filters_before_aggregation(self, lane_db):
        top_bulk = lane_db.get_all_synergies_bulk(lane="top")
        assert top_bulk[("pantheon", "leona")] == pytest.approx(-5.0)

        support_bulk = lane_db.get_all_synergies_bulk(lane="support")
        assert support_bulk[("pantheon", "leona")] == pytest.approx(15.0)

    def test_nonexistent_lane_returns_empty_dict(self, lane_db):
        assert lane_db.get_all_synergies_bulk(lane="jungle") == {}


class TestCalculateSynergyBonusLane:
    """`ChampionScorer.calculate_synergy_bonus` propage `lane` jusqu'à
    `get_champion_synergies_by_name` (SPEC-03 §3/B2)."""

    def test_lane_changes_bonus(self, lane_db):
        scorer = ChampionScorer(lane_db, verbose=False)

        bonus_top = scorer.calculate_synergy_bonus("Pantheon", ["Leona"], lane="top")
        bonus_support = scorer.calculate_synergy_bonus("Pantheon", ["Leona"], lane="support")

        assert bonus_top == pytest.approx(-5.0)
        assert bonus_support == pytest.approx(15.0)

    def test_lane_none_keeps_full_aggregation(self, lane_db):
        scorer = ChampionScorer(lane_db, verbose=False)

        bonus = scorer.calculate_synergy_bonus("Pantheon", ["Leona"])
        expected = (-5.0 * 300 + 15.0 * 600) / 900
        assert bonus == pytest.approx(expected)
