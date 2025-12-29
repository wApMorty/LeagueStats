"""
Tests for data models (src/models.py).

Ensures 100% coverage of dataclass models with validation, factory methods,
and serialization. Tests immutability, boundary conditions, and error handling.

Author: @pj35
Created: 2025-12-28
Sprint: 2 - Tâche #14 (SQLAlchemy ORM Migration - Phase 1)
Coverage Target: 100%
"""

import pytest
from src.models import Matchup, MatchupDraft, ChampionScore


# ============================================================================
# Matchup Tests
# ============================================================================


class TestMatchup:
    """Test suite for Matchup dataclass."""

    def test_create_valid_matchup(self):
        """Test creating a valid Matchup instance."""
        matchup = Matchup(
            enemy_name="Zed", winrate=52.5, delta1=150.0, delta2=200.0, pickrate=12.5, games=1000
        )

        assert matchup.enemy_name == "Zed"
        assert matchup.winrate == 52.5
        assert matchup.delta1 == 150.0
        assert matchup.delta2 == 200.0
        assert matchup.pickrate == 12.5
        assert matchup.games == 1000

    def test_matchup_immutable(self):
        """Test that Matchup is immutable (frozen=True)."""
        matchup = Matchup("Yasuo", 48.0, 100.0, 150.0, 10.0, 500)

        with pytest.raises(AttributeError):
            matchup.winrate = 50.0  # Should raise FrozenInstanceError

    def test_matchup_negative_deltas(self):
        """Test that negative deltas are allowed (valid performance metrics)."""
        matchup = Matchup("LeBlanc", 45.0, -50.0, -100.0, 5.0, 200)

        assert matchup.delta1 == -50.0
        assert matchup.delta2 == -100.0

    def test_matchup_boundary_winrate(self):
        """Test boundary values for winrate (0.0 and 100.0)."""
        min_wr = Matchup("Champ1", 0.0, 0.0, 0.0, 0.0, 0)
        max_wr = Matchup("Champ2", 100.0, 0.0, 0.0, 100.0, 1000)

        assert min_wr.winrate == 0.0
        assert max_wr.winrate == 100.0

    def test_matchup_invalid_winrate_negative(self):
        """Test that negative winrate raises ValueError."""
        with pytest.raises(ValueError, match="Invalid winrate: must be 0-100"):
            Matchup("Champ", -1.0, 0.0, 0.0, 0.0, 0)

    def test_matchup_invalid_winrate_above_100(self):
        """Test that winrate > 100 raises ValueError."""
        with pytest.raises(ValueError, match="Invalid winrate: must be 0-100"):
            Matchup("Champ", 101.0, 0.0, 0.0, 0.0, 0)

    def test_matchup_invalid_pickrate_negative(self):
        """Test that negative pickrate raises ValueError."""
        with pytest.raises(ValueError, match="Invalid pickrate: must be 0-100"):
            Matchup("Champ", 50.0, 0.0, 0.0, -1.0, 0)

    def test_matchup_invalid_pickrate_above_100(self):
        """Test that pickrate > 100 raises ValueError."""
        with pytest.raises(ValueError, match="Invalid pickrate: must be 0-100"):
            Matchup("Champ", 50.0, 0.0, 0.0, 101.0, 0)

    def test_matchup_invalid_enemy_name_empty(self):
        """Test that empty enemy_name raises ValueError."""
        with pytest.raises(ValueError, match="Invalid enemy_name: must be non-empty string"):
            Matchup("", 50.0, 0.0, 0.0, 0.0, 0)

    def test_matchup_invalid_enemy_name_whitespace(self):
        """Test that whitespace-only enemy_name raises ValueError."""
        with pytest.raises(ValueError, match="Invalid enemy_name: must be non-empty string"):
            Matchup("   ", 50.0, 0.0, 0.0, 0.0, 0)

    def test_matchup_invalid_games_negative(self):
        """Test that negative games raises ValueError."""
        with pytest.raises(ValueError, match="Invalid games: must be non-negative integer"):
            Matchup("Champ", 50.0, 0.0, 0.0, 0.0, -1)

    def test_matchup_invalid_games_non_integer(self):
        """Test that non-integer games raises ValueError."""
        with pytest.raises(ValueError, match="Invalid games: must be non-negative integer"):
            Matchup("Champ", 50.0, 0.0, 0.0, 0.0, 100.5)

    def test_matchup_invalid_delta1_non_numeric(self):
        """Test that non-numeric delta1 raises ValueError."""
        with pytest.raises(ValueError, match="Invalid delta1: must be numeric"):
            Matchup("Champ", 50.0, "invalid", 0.0, 0.0, 0)

    def test_matchup_invalid_delta2_non_numeric(self):
        """Test that non-numeric delta2 raises ValueError."""
        with pytest.raises(ValueError, match="Invalid delta2: must be numeric"):
            Matchup("Champ", 50.0, 0.0, "invalid", 0.0, 0)

    def test_matchup_from_tuple_valid(self):
        """Test creating Matchup from valid 6-element tuple."""
        data = ("Zed", 52.5, 150.0, 200.0, 12.5, 1000)
        matchup = Matchup.from_tuple(data)

        assert matchup.enemy_name == "Zed"
        assert matchup.winrate == 52.5
        assert matchup.delta1 == 150.0
        assert matchup.delta2 == 200.0
        assert matchup.pickrate == 12.5
        assert matchup.games == 1000

    def test_matchup_from_tuple_invalid_length_short(self):
        """Test that from_tuple raises ValueError for short tuple."""
        data = ("Zed", 52.5, 150.0)  # Only 3 elements

        with pytest.raises(ValueError, match="Expected 6-element tuple"):
            Matchup.from_tuple(data)

    def test_matchup_from_tuple_invalid_length_long(self):
        """Test that from_tuple raises ValueError for long tuple."""
        data = ("Zed", 52.5, 150.0, 200.0, 12.5, 1000, 999)  # 7 elements

        with pytest.raises(ValueError, match="Expected 6-element tuple"):
            Matchup.from_tuple(data)

    def test_matchup_to_dict(self):
        """Test serialization to dictionary."""
        matchup = Matchup("Zed", 52.5, 150.0, 200.0, 12.5, 1000)
        result = matchup.to_dict()

        assert isinstance(result, dict)
        assert result == {
            "enemy_name": "Zed",
            "winrate": 52.5,
            "delta1": 150.0,
            "delta2": 200.0,
            "pickrate": 12.5,
            "games": 1000,
        }


# ============================================================================
# MatchupDraft Tests
# ============================================================================


class TestMatchupDraft:
    """Test suite for MatchupDraft dataclass."""

    def test_create_valid_matchup_draft(self):
        """Test creating a valid MatchupDraft instance."""
        draft = MatchupDraft(enemy_name="Yasuo", delta2=-50.0, pickrate=12.5, games=500)

        assert draft.enemy_name == "Yasuo"
        assert draft.delta2 == -50.0
        assert draft.pickrate == 12.5
        assert draft.games == 500

    def test_matchup_draft_immutable(self):
        """Test that MatchupDraft is immutable (frozen=True)."""
        draft = MatchupDraft("Yasuo", -50.0, 12.5, 500)

        with pytest.raises(AttributeError):
            draft.delta2 = 0.0

    def test_matchup_draft_negative_delta(self):
        """Test that negative delta2 is allowed."""
        draft = MatchupDraft("LeBlanc", -100.0, 5.0, 200)

        assert draft.delta2 == -100.0

    def test_matchup_draft_boundary_pickrate(self):
        """Test boundary values for pickrate (0.0 and 100.0)."""
        min_pr = MatchupDraft("Champ1", 0.0, 0.0, 0)
        max_pr = MatchupDraft("Champ2", 0.0, 100.0, 1000)

        assert min_pr.pickrate == 0.0
        assert max_pr.pickrate == 100.0

    def test_matchup_draft_invalid_pickrate_negative(self):
        """Test that negative pickrate raises ValueError."""
        with pytest.raises(ValueError, match="Invalid pickrate: must be 0-100"):
            MatchupDraft("Champ", 0.0, -1.0, 0)

    def test_matchup_draft_invalid_pickrate_above_100(self):
        """Test that pickrate > 100 raises ValueError."""
        with pytest.raises(ValueError, match="Invalid pickrate: must be 0-100"):
            MatchupDraft("Champ", 0.0, 101.0, 0)

    def test_matchup_draft_invalid_enemy_name_empty(self):
        """Test that empty enemy_name raises ValueError."""
        with pytest.raises(ValueError, match="Invalid enemy_name: must be non-empty string"):
            MatchupDraft("", 0.0, 0.0, 0)

    def test_matchup_draft_invalid_enemy_name_whitespace(self):
        """Test that whitespace-only enemy_name raises ValueError."""
        with pytest.raises(ValueError, match="Invalid enemy_name: must be non-empty string"):
            MatchupDraft("   ", 0.0, 0.0, 0)

    def test_matchup_draft_invalid_games_negative(self):
        """Test that negative games raises ValueError."""
        with pytest.raises(ValueError, match="Invalid games: must be non-negative integer"):
            MatchupDraft("Champ", 0.0, 0.0, -1)

    def test_matchup_draft_invalid_games_non_integer(self):
        """Test that non-integer games raises ValueError."""
        with pytest.raises(ValueError, match="Invalid games: must be non-negative integer"):
            MatchupDraft("Champ", 0.0, 0.0, 100.5)

    def test_matchup_draft_invalid_delta2_non_numeric(self):
        """Test that non-numeric delta2 raises ValueError."""
        with pytest.raises(ValueError, match="Invalid delta2: must be numeric"):
            MatchupDraft("Champ", "invalid", 0.0, 0)

    def test_matchup_draft_from_tuple_valid(self):
        """Test creating MatchupDraft from valid 4-element tuple."""
        data = ("Yasuo", -50.0, 12.5, 500)
        draft = MatchupDraft.from_tuple(data)

        assert draft.enemy_name == "Yasuo"
        assert draft.delta2 == -50.0
        assert draft.pickrate == 12.5
        assert draft.games == 500

    def test_matchup_draft_from_tuple_invalid_length_short(self):
        """Test that from_tuple raises ValueError for short tuple."""
        data = ("Yasuo", -50.0)  # Only 2 elements

        with pytest.raises(ValueError, match="Expected 4-element tuple"):
            MatchupDraft.from_tuple(data)

    def test_matchup_draft_from_tuple_invalid_length_long(self):
        """Test that from_tuple raises ValueError for long tuple."""
        data = ("Yasuo", -50.0, 12.5, 500, 999)  # 5 elements

        with pytest.raises(ValueError, match="Expected 4-element tuple"):
            MatchupDraft.from_tuple(data)

    def test_matchup_draft_to_dict(self):
        """Test serialization to dictionary."""
        draft = MatchupDraft("Yasuo", -50.0, 12.5, 500)
        result = draft.to_dict()

        assert isinstance(result, dict)
        assert result == {"enemy_name": "Yasuo", "delta2": -50.0, "pickrate": 12.5, "games": 500}

    def test_matchup_draft_to_matchup(self):
        """Test conversion to full Matchup with default values."""
        draft = MatchupDraft("Yasuo", -50.0, 12.5, 500)
        matchup = draft.to_matchup()

        assert isinstance(matchup, Matchup)
        assert matchup.enemy_name == "Yasuo"
        assert matchup.winrate == 50.0  # Default
        assert matchup.delta1 == 0.0  # Default
        assert matchup.delta2 == -50.0  # From draft
        assert matchup.pickrate == 12.5  # From draft
        assert matchup.games == 500  # From draft

    def test_matchup_draft_to_matchup_custom_values(self):
        """Test conversion to Matchup with custom winrate and delta1."""
        draft = MatchupDraft("Yasuo", -50.0, 12.5, 500)
        matchup = draft.to_matchup(winrate=55.5, delta1=100.0)

        assert matchup.winrate == 55.5
        assert matchup.delta1 == 100.0
        assert matchup.delta2 == -50.0


# ============================================================================
# ChampionScore Tests
# ============================================================================


class TestChampionScore:
    """Test suite for ChampionScore dataclass."""

    def test_create_valid_champion_score(self):
        """Test creating a valid ChampionScore instance."""
        champ = ChampionScore(name="Jinx", score=875.5)

        assert champ.name == "Jinx"
        assert champ.score == 875.5

    def test_champion_score_immutable(self):
        """Test that ChampionScore is immutable (frozen=True)."""
        champ = ChampionScore("Jinx", 875.5)

        with pytest.raises(AttributeError):
            champ.score = 900.0

    def test_champion_score_negative_score(self):
        """Test that negative scores are allowed."""
        champ = ChampionScore("Yuumi", -250.0)

        assert champ.score == -250.0

    def test_champion_score_zero_score(self):
        """Test that zero score is allowed."""
        champ = ChampionScore("Neutral", 0.0)

        assert champ.score == 0.0

    def test_champion_score_integer_score(self):
        """Test that integer scores are accepted."""
        champ = ChampionScore("Jinx", 875)

        assert champ.score == 875

    def test_champion_score_invalid_name_empty(self):
        """Test that empty name raises ValueError."""
        with pytest.raises(ValueError, match="Invalid name: must be non-empty string"):
            ChampionScore("", 875.5)

    def test_champion_score_invalid_name_whitespace(self):
        """Test that whitespace-only name raises ValueError."""
        with pytest.raises(ValueError, match="Invalid name: must be non-empty string"):
            ChampionScore("   ", 875.5)

    def test_champion_score_invalid_score_non_numeric(self):
        """Test that non-numeric score raises ValueError."""
        with pytest.raises(ValueError, match="Invalid score: must be numeric"):
            ChampionScore("Jinx", "invalid")

    def test_champion_score_from_tuple_valid(self):
        """Test creating ChampionScore from valid 2-element tuple."""
        data = ("Jinx", 875.5)
        champ = ChampionScore.from_tuple(data)

        assert champ.name == "Jinx"
        assert champ.score == 875.5

    def test_champion_score_from_tuple_invalid_length_short(self):
        """Test that from_tuple raises ValueError for short tuple."""
        data = ("Jinx",)  # Only 1 element

        with pytest.raises(ValueError, match="Expected 2-element tuple"):
            ChampionScore.from_tuple(data)

    def test_champion_score_from_tuple_invalid_length_long(self):
        """Test that from_tuple raises ValueError for long tuple."""
        data = ("Jinx", 875.5, 999)  # 3 elements

        with pytest.raises(ValueError, match="Expected 2-element tuple"):
            ChampionScore.from_tuple(data)

    def test_champion_score_to_dict(self):
        """Test serialization to dictionary."""
        champ = ChampionScore("Jinx", 875.5)
        result = champ.to_dict()

        assert isinstance(result, dict)
        assert result == {"name": "Jinx", "score": 875.5}


# ============================================================================
# Integration Tests (Multiple Models)
# ============================================================================


class TestModelsIntegration:
    """Integration tests for multiple model types."""

    def test_all_models_immutable(self):
        """Test that all models are properly frozen."""
        matchup = Matchup("Zed", 52.5, 150.0, 200.0, 12.5, 1000)
        draft = MatchupDraft("Yasuo", -50.0, 12.5, 500)
        champ = ChampionScore("Jinx", 875.5)

        with pytest.raises(AttributeError):
            matchup.winrate = 60.0

        with pytest.raises(AttributeError):
            draft.games = 1000

        with pytest.raises(AttributeError):
            champ.score = 900.0

    def test_all_models_serialization(self):
        """Test that all models can serialize to dict."""
        matchup = Matchup("Zed", 52.5, 150.0, 200.0, 12.5, 1000)
        draft = MatchupDraft("Yasuo", -50.0, 12.5, 500)
        champ = ChampionScore("Jinx", 875.5)

        assert isinstance(matchup.to_dict(), dict)
        assert isinstance(draft.to_dict(), dict)
        assert isinstance(champ.to_dict(), dict)

    def test_all_models_from_tuple_factory(self):
        """Test that all models support from_tuple factory method."""
        matchup_data = ("Zed", 52.5, 150.0, 200.0, 12.5, 1000)
        draft_data = ("Yasuo", -50.0, 12.5, 500)
        champ_data = ("Jinx", 875.5)

        matchup = Matchup.from_tuple(matchup_data)
        draft = MatchupDraft.from_tuple(draft_data)
        champ = ChampionScore.from_tuple(champ_data)

        assert matchup.enemy_name == "Zed"
        assert draft.enemy_name == "Yasuo"
        assert champ.name == "Jinx"
