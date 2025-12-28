"""Test backward compatibility for dataclass migration.

These tests ensure that the as_dataclass parameter maintains backward
compatibility with legacy code using tuple indexing.
"""

import pytest
from src.db import Database
from src.models import Matchup, MatchupDraft


class TestBackwardCompatibility:
    """Test that as_dataclass parameter maintains backward compatibility."""

    def test_get_matchups_returns_tuples_when_disabled(self, db, insert_matchup):
        """Test as_dataclass=False returns tuples for backward compatibility.

        Prevents regression where legacy code using m[0], m[3] would break.
        """
        insert_matchup("Jinx", "Caitlyn", 52.0, 100, 150, 10.0, 1000)

        # Old way - should return tuples
        matchups = db.get_champion_matchups_by_name("Jinx", as_dataclass=False)

        assert isinstance(matchups, list)
        assert len(matchups) > 0

        m = matchups[0]
        assert isinstance(m, tuple)  # Must be tuple, not Matchup
        assert m[0] == "Caitlyn"  # enemy_name
        assert m[1] == 52.0  # winrate
        assert m[3] == 150  # delta2

    def test_get_matchups_returns_dataclasses_by_default(self, db, insert_matchup):
        """Test as_dataclass=True (default) returns Matchup objects.

        Verifies new code gets type-safe dataclasses by default.
        """
        insert_matchup("Jinx", "Caitlyn", 52.0, 100, 150, 10.0, 1000)

        # New way - should return dataclasses
        matchups = db.get_champion_matchups_by_name("Jinx")  # Default as_dataclass=True

        assert len(matchups) > 0
        m = matchups[0]

        assert isinstance(m, Matchup)
        assert m.enemy_name == "Caitlyn"
        assert m.winrate == 52.0
        assert m.delta2 == 150

    def test_draft_matchups_backward_compatibility(self, db, insert_matchup):
        """Test get_champion_matchups_for_draft as_dataclass parameter."""
        insert_matchup("Yasuo", "Yone", 48.0, -50, -100, 12.0, 800)

        # Tuple mode
        tuples = db.get_champion_matchups_for_draft("Yasuo", as_dataclass=False)
        assert isinstance(tuples[0], tuple)
        assert len(tuples[0]) == 4  # enemy_name, delta2, pickrate, games

        # Dataclass mode
        dataclasses = db.get_champion_matchups_for_draft("Yasuo", as_dataclass=True)
        assert isinstance(dataclasses[0], MatchupDraft)

    def test_tuple_mode_allows_index_access(self, db, insert_matchup):
        """Test that tuple mode allows legacy m[0], m[3], m[5] indexing."""
        insert_matchup("Olaf", "Darius", 45.0, -150, -200, 15.0, 2000)

        matchups = db.get_champion_matchups_by_name("Olaf", as_dataclass=False)
        m = matchups[0]

        # Legacy code patterns should work
        enemy = m[0]
        winrate = m[1]
        delta1 = m[2]
        delta2 = m[3]
        pickrate = m[4]
        games = m[5]

        assert enemy == "Darius"
        assert winrate == 45.0
        assert delta1 == -150
        assert delta2 == -200
        assert pickrate == 15.0
        assert games == 2000

    def test_dataclass_mode_allows_attribute_access(self, db, insert_matchup):
        """Test that dataclass mode provides readable attribute access."""
        insert_matchup("Lux", "Zed", 42.0, -180, -250, 8.0, 1500)

        matchups = db.get_champion_matchups_by_name("Lux", as_dataclass=True)
        m = matchups[0]

        # New code patterns should work
        assert m.enemy_name == "Zed"
        assert m.winrate == 42.0
        assert m.delta1 == -180
        assert m.delta2 == -250
        assert m.pickrate == 8.0
        assert m.games == 1500


class TestDatabaseToDataclassIntegration:
    """Test integration between database and dataclass models."""

    def test_multiple_matchups_all_dataclass_instances(self, db, insert_matchup):
        """Test that fetching multiple matchups returns consistent dataclass instances."""
        insert_matchup("Jinx", "Caitlyn", 52.0, 100, 150, 10.0, 1000)
        insert_matchup("Jinx", "Ezreal", 48.0, -50, -100, 8.0, 1200)
        insert_matchup("Jinx", "Jhin", 50.0, 0, 50, 10.0, 1000)

        matchups = db.get_champion_matchups_by_name("Jinx")

        assert len(matchups) == 3
        assert all(isinstance(m, Matchup) for m in matchups)

        # Verify each matchup has correct attributes
        enemies = {m.enemy_name for m in matchups}
        assert enemies == {"Caitlyn", "Ezreal", "Jhin"}

    def test_draft_matchups_conversion_preserves_data(self, db, insert_matchup):
        """Test that MatchupDraft.to_matchup() preserves critical data."""
        insert_matchup("Yasuo", "Yone", 48.0, -50, -100, 12.0, 800)

        draft_matchups = db.get_champion_matchups_for_draft("Yasuo")
        draft = draft_matchups[0]

        # Convert to full matchup
        full = draft.to_matchup()

        # Critical fields must match
        assert full.enemy_name == draft.enemy_name
        assert full.delta2 == draft.delta2
        assert full.pickrate == draft.pickrate
        assert full.games == draft.games

        # Dummy fields should be set
        assert full.winrate == 50.0  # Default neutral
        assert full.delta1 == 0.0  # Default neutral
