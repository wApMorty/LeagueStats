"""Regression tests for synergies feature (Tâche #16).

Tests to ensure synergy system works correctly and prevents regressions.

Author: Tech Lead (Claude Sonnet 4.5)
Created: 2026-01-16
Sprint: 2 - Tâche #16 (Support des Synergies)
"""

import pytest
from src.db import Database
from src.models import Synergy
from src.analysis.scoring import ChampionScorer
from src.config_constants import synergy_config


@pytest.fixture
def temp_synergy_db(tmp_path):
    """Create temporary database with synergies test data."""
    db_path = tmp_path / "test_synergies.db"
    db = Database(str(db_path))
    db.connect()

    # Create schema manually (simpler for testing)
    cursor = db.connection.cursor()

    # Create champions table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS champions (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE
        )
        """
    )

    # Create synergies table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS synergies (
            id INTEGER PRIMARY KEY,
            champion INTEGER NOT NULL,
            ally INTEGER NOT NULL,
            winrate FLOAT NOT NULL,
            delta1 FLOAT NOT NULL,
            delta2 FLOAT NOT NULL,
            pickrate FLOAT NOT NULL,
            games INTEGER NOT NULL,
            FOREIGN KEY (champion) REFERENCES champions(id) ON DELETE CASCADE,
            FOREIGN KEY (ally) REFERENCES champions(id) ON DELETE CASCADE
        )
        """
    )
    db.connection.commit()

    # Insert test champions
    cursor.execute("INSERT INTO champions (id, name) VALUES (1, 'Yasuo')")
    cursor.execute("INSERT INTO champions (id, name) VALUES (2, 'Malphite')")
    cursor.execute("INSERT INTO champions (id, name) VALUES (3, 'Diana')")
    db.connection.commit()

    # Insert test synergies (Yasuo with Malphite and Diana)
    cursor.execute(
        """
        INSERT INTO synergies (champion, ally, winrate, delta1, delta2, pickrate, games)
        VALUES (1, 2, 55.0, 180.0, 220.0, 15.0, 1200)
        """
    )  # Yasuo + Malphite
    cursor.execute(
        """
        INSERT INTO synergies (champion, ally, winrate, delta1, delta2, pickrate, games)
        VALUES (1, 3, 53.5, 160.0, 190.0, 12.0, 1000)
        """
    )  # Yasuo + Diana
    db.connection.commit()

    yield db

    db.connection.close()


def test_synergy_dataclass_structure():
    """Regression: Synergy dataclass must mirror Matchup structure."""
    synergy = Synergy("Malphite", 55.0, 180.0, 220.0, 15.0, 1200)

    # Verify all fields exist
    assert hasattr(synergy, "ally_name")
    assert hasattr(synergy, "winrate")
    assert hasattr(synergy, "delta1")
    assert hasattr(synergy, "delta2")
    assert hasattr(synergy, "pickrate")
    assert hasattr(synergy, "games")

    # Verify field values
    assert synergy.ally_name == "Malphite"
    assert synergy.winrate == 55.0
    assert synergy.delta1 == 180.0
    assert synergy.delta2 == 220.0
    assert synergy.pickrate == 15.0
    assert synergy.games == 1200


def test_synergy_dataclass_validation():
    """Regression: Synergy dataclass must validate data integrity."""
    # Valid synergy
    valid = Synergy("Malphite", 55.0, 180.0, 220.0, 15.0, 1200)
    assert valid.ally_name == "Malphite"

    # Invalid winrate (must be 0-100)
    with pytest.raises(ValueError, match="Invalid winrate"):
        Synergy("Malphite", 150.0, 180.0, 220.0, 15.0, 1200)

    # Invalid pickrate (must be 0-100)
    with pytest.raises(ValueError, match="Invalid pickrate"):
        Synergy("Malphite", 55.0, 180.0, 220.0, 150.0, 1200)

    # Invalid games (must be non-negative)
    with pytest.raises(ValueError, match="Invalid games"):
        Synergy("Malphite", 55.0, 180.0, 220.0, 15.0, -100)


def test_db_synergy_methods_exist(temp_synergy_db):
    """Regression: Database must have all required synergy methods."""
    db = temp_synergy_db

    # Verify methods exist
    assert hasattr(db, "add_synergy")
    assert hasattr(db, "get_champion_synergies_by_name")
    assert hasattr(db, "add_synergies_batch")
    assert hasattr(db, "clear_synergies_for_champion")
    assert hasattr(db, "get_synergy_delta2")
    assert hasattr(db, "get_all_synergies_bulk")


def test_db_get_champion_synergies(temp_synergy_db):
    """Regression: get_champion_synergies_by_name must return Synergy objects."""
    db = temp_synergy_db

    synergies = db.get_champion_synergies_by_name("Yasuo", as_dataclass=True)

    # Verify return type
    assert isinstance(synergies, list)
    assert len(synergies) == 2  # Yasuo has 2 synergies (Malphite, Diana)
    assert all(isinstance(s, Synergy) for s in synergies)

    # Verify data
    malphite_synergy = next(s for s in synergies if s.ally_name == "Malphite")
    assert malphite_synergy.winrate == 55.0
    assert malphite_synergy.delta2 == 220.0
    assert malphite_synergy.games == 1200


def test_synergy_scoring_calculation(temp_synergy_db):
    """Regression: ChampionScorer must calculate synergy bonus correctly."""
    db = temp_synergy_db
    scorer = ChampionScorer(db, verbose=False)

    # Calculate synergy bonus for Yasuo with Malphite
    bonus = scorer.calculate_synergy_bonus("Yasuo", ["Malphite"])

    # Expected: delta2 of Yasuo+Malphite synergy = 220.0
    assert bonus == pytest.approx(220.0, abs=0.1)


def test_synergy_bonus_with_multiple_allies(temp_synergy_db):
    """Regression: Synergy bonus must aggregate multiple allies correctly."""
    db = temp_synergy_db
    scorer = ChampionScorer(db, verbose=False)

    # Calculate synergy bonus for Yasuo with Malphite + Diana
    bonus = scorer.calculate_synergy_bonus("Yasuo", ["Malphite", "Diana"])

    # Expected: weighted average by pickrate
    # (220.0 * 15.0 + 190.0 * 12.0) / (15.0 + 12.0) = 206.67
    expected_bonus = (220.0 * 15.0 + 190.0 * 12.0) / (15.0 + 12.0)
    assert bonus == pytest.approx(expected_bonus, abs=0.1)


def test_final_score_with_synergies(temp_synergy_db):
    """Regression: Final score must combine matchup + synergy bonus."""
    db = temp_synergy_db
    scorer = ChampionScorer(db, verbose=False)

    matchup_score = 100.0
    final_score = scorer.calculate_final_score_with_synergies(matchup_score, "Yasuo", ["Malphite"])

    # Expected: 100.0 + (220.0 * 0.3) = 166.0
    expected_score = matchup_score + (220.0 * synergy_config.SYNERGY_BONUS_MULTIPLIER)
    assert final_score == pytest.approx(expected_score, abs=0.1)


def test_synergy_feature_toggle(temp_synergy_db):
    """Regression: Synergy feature must respect SYNERGIES_ENABLED toggle."""
    db = temp_synergy_db
    scorer = ChampionScorer(db, verbose=False)

    # Temporarily disable synergies
    original_enabled = synergy_config.SYNERGIES_ENABLED
    try:
        synergy_config.SYNERGIES_ENABLED = False

        bonus = scorer.calculate_synergy_bonus("Yasuo", ["Malphite"])
        assert bonus == 0.0  # Must return 0 when disabled

        final_score = scorer.calculate_final_score_with_synergies(100.0, "Yasuo", ["Malphite"])
        assert final_score == 100.0  # Must return matchup score unchanged

    finally:
        # Restore original value
        synergy_config.SYNERGIES_ENABLED = original_enabled


def test_synergy_backward_compatibility(temp_synergy_db):
    """Regression: Empty ally list must return 0 bonus (backward compatible)."""
    db = temp_synergy_db
    scorer = ChampionScorer(db, verbose=False)

    # No allies = no synergy bonus
    bonus = scorer.calculate_synergy_bonus("Yasuo", [])
    assert bonus == 0.0

    final_score = scorer.calculate_final_score_with_synergies(100.0, "Yasuo", [])
    assert final_score == 100.0  # Unchanged when no allies
