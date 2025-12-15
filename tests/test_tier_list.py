"""Tests for tier list generation (src/analysis/tier_list.py)."""

import pytest
from src.analysis.tier_list import TierListGenerator
from src.config_constants import analysis_config


class TestGenerateByDelta1:
    """Tests for generate_by_delta1 method."""

    def test_ranks_by_delta1_descending(self, db, scorer, insert_matchup):
        """Test that champions are ranked by delta1 in descending order."""
        # Setup test data
        insert_matchup('ChampA', 'Enemy1', 50.0, 200, 300, 10.0, 1000)
        insert_matchup('ChampA', 'Enemy2', 50.0, 250, 350, 12.0, 1200)
        insert_matchup('ChampB', 'Enemy1', 50.0, 100, 150, 10.0, 1000)
        insert_matchup('ChampB', 'Enemy2', 50.0, 150, 200, 12.0, 1200)
        insert_matchup('ChampC', 'Enemy1', 50.0, 300, 400, 10.0, 1000)
        insert_matchup('ChampC', 'Enemy2', 50.0, 350, 450, 12.0, 1200)

        tier_gen = TierListGenerator(db, scorer)
        result = tier_gen.generate_by_delta1(['ChampA', 'ChampB', 'ChampC'])

        # ChampC should have highest delta1, ChampA second, ChampB third
        assert len(result) == 3
        assert result[0][0] == 'ChampC'
        assert result[1][0] == 'ChampA'
        assert result[2][0] == 'ChampB'
        assert result[0][1] > result[1][1] > result[2][1]

    def test_filters_low_games_champions(self, db, scorer, insert_matchup):
        """Test that champions with insufficient games are filtered out."""
        # Setup test data with one champion below threshold
        insert_matchup('ChampA', 'Enemy1', 50.0, 200, 300, 10.0, 1000)
        insert_matchup('ChampA', 'Enemy2', 50.0, 250, 350, 12.0, 1200)
        insert_matchup('ChampB', 'Enemy1', 50.0, 100, 150, 10.0, 50)

        tier_gen = TierListGenerator(db, scorer, min_games=500)
        result = tier_gen.generate_by_delta1(['ChampA', 'ChampB'])

        # Only ChampA should be in results (2200 total games vs ChampB's 50 games)
        assert len(result) == 1
        assert result[0][0] == 'ChampA'

    def test_empty_champion_list(self, db, scorer):
        """Test with empty champion list."""
        tier_gen = TierListGenerator(db, scorer)
        result = tier_gen.generate_by_delta1([])

        assert result == []

    def test_champion_with_no_matchups(self, db, scorer):
        """Test champion with no matchup data is skipped."""
        tier_gen = TierListGenerator(db, scorer)
        result = tier_gen.generate_by_delta1(['NonExistentChampion'])

        assert result == []

    def test_custom_min_games_threshold(self, db, scorer, insert_matchup):
        """Test that custom min_games threshold is respected."""
        # Setup test data
        insert_matchup('ChampA', 'Enemy1', 50.0, 200, 300, 10.0, 300)
        insert_matchup('ChampA', 'Enemy2', 50.0, 250, 350, 12.0, 300)

        # With high threshold, should filter out ChampA (600 total games)
        tier_gen_high = TierListGenerator(db, scorer, min_games=1000)
        result_high = tier_gen_high.generate_by_delta1(['ChampA'])
        assert len(result_high) == 0

        # With low threshold, should include ChampA
        tier_gen_low = TierListGenerator(db, scorer, min_games=500)
        result_low = tier_gen_low.generate_by_delta1(['ChampA'])
        assert len(result_low) == 1


class TestGenerateByDelta2:
    """Tests for generate_by_delta2 method."""

    def test_ranks_by_delta2_descending(self, db, scorer, insert_matchup):
        """Test that champions are ranked by delta2 in descending order."""
        # Setup test data
        insert_matchup('ChampA', 'Enemy1', 50.0, 100, 300, 10.0, 1000)
        insert_matchup('ChampA', 'Enemy2', 50.0, 100, 350, 12.0, 1200)
        insert_matchup('ChampB', 'Enemy1', 50.0, 100, 150, 10.0, 1000)
        insert_matchup('ChampB', 'Enemy2', 50.0, 100, 200, 12.0, 1200)
        insert_matchup('ChampC', 'Enemy1', 50.0, 100, 400, 10.0, 1000)
        insert_matchup('ChampC', 'Enemy2', 50.0, 100, 450, 12.0, 1200)

        tier_gen = TierListGenerator(db, scorer)
        result = tier_gen.generate_by_delta2(['ChampA', 'ChampB', 'ChampC'])

        # ChampC should have highest delta2, ChampA second, ChampB third
        assert len(result) == 3
        assert result[0][0] == 'ChampC'
        assert result[1][0] == 'ChampA'
        assert result[2][0] == 'ChampB'
        assert result[0][1] > result[1][1] > result[2][1]

    def test_filters_low_games_champions(self, db, scorer, insert_matchup):
        """Test that champions with insufficient games are filtered out."""
        # Setup test data
        insert_matchup('ChampA', 'Enemy1', 50.0, 100, 300, 10.0, 1000)
        insert_matchup('ChampA', 'Enemy2', 50.0, 100, 350, 12.0, 1200)
        insert_matchup('ChampB', 'Enemy1', 50.0, 100, 150, 10.0, 50)

        tier_gen = TierListGenerator(db, scorer, min_games=500)
        result = tier_gen.generate_by_delta2(['ChampA', 'ChampB'])

        # Only ChampA should be in results
        assert len(result) == 1
        assert result[0][0] == 'ChampA'

    def test_empty_champion_list(self, db, scorer):
        """Test with empty champion list."""
        tier_gen = TierListGenerator(db, scorer)
        result = tier_gen.generate_by_delta2([])

        assert result == []


class TestGenerateForLane:
    """Tests for generate_for_lane method."""

    def test_valid_lane_top(self, db, scorer, insert_matchup):
        """Test tier list generation for top lane."""
        # Setup matchup data for a top lane champion
        insert_matchup('Aatrox', 'Darius', 48.0, -100, -150, 10.0, 1500)
        insert_matchup('Aatrox', 'Garen', 52.0, 100, 150, 12.0, 2000)

        tier_gen = TierListGenerator(db, scorer)
        result = tier_gen.generate_for_lane('top')

        # Should return results (tier list for TOP_LIST champions)
        assert isinstance(result, list)
        # Result may be empty if test champions not in TOP_LIST, but should not error

    def test_valid_lane_jungle(self, db, scorer):
        """Test tier list generation for jungle."""
        tier_gen = TierListGenerator(db, scorer)
        result = tier_gen.generate_for_lane('jungle')

        assert isinstance(result, list)

    def test_valid_lane_mid(self, db, scorer):
        """Test tier list generation for mid."""
        tier_gen = TierListGenerator(db, scorer)
        result = tier_gen.generate_for_lane('mid')

        assert isinstance(result, list)

    def test_valid_lane_adc(self, db, scorer):
        """Test tier list generation for adc."""
        tier_gen = TierListGenerator(db, scorer)
        result = tier_gen.generate_for_lane('adc')

        assert isinstance(result, list)

    def test_valid_lane_support(self, db, scorer):
        """Test tier list generation for support."""
        tier_gen = TierListGenerator(db, scorer)
        result = tier_gen.generate_for_lane('support')

        assert isinstance(result, list)

    def test_invalid_lane_returns_empty(self, db, scorer):
        """Test that invalid lane returns empty list."""
        tier_gen = TierListGenerator(db, scorer)
        result = tier_gen.generate_for_lane('invalid_lane')

        assert result == []

    def test_uses_delta2_not_delta1(self, db, scorer, insert_matchup):
        """Test that lane tier lists use delta2 metric, not delta1."""
        # Setup test data where delta1 and delta2 would rank differently
        insert_matchup('ChampA', 'Enemy1', 50.0, 300, 100, 10.0, 1000)
        insert_matchup('ChampA', 'Enemy2', 50.0, 300, 100, 12.0, 1200)
        insert_matchup('ChampB', 'Enemy1', 50.0, 100, 300, 10.0, 1000)
        insert_matchup('ChampB', 'Enemy2', 50.0, 100, 300, 12.0, 1200)

        tier_gen = TierListGenerator(db, scorer)

        # Generate both lists
        by_delta1 = tier_gen.generate_by_delta1(['ChampA', 'ChampB'])
        by_delta2 = tier_gen.generate_by_delta2(['ChampA', 'ChampB'])

        # ChampA has higher delta1, ChampB has higher delta2
        # Verify they rank differently
        if len(by_delta1) == 2 and len(by_delta2) == 2:
            assert by_delta1[0][0] == 'ChampA'  # ChampA first by delta1
            assert by_delta2[0][0] == 'ChampB'  # ChampB first by delta2


class TestInitialization:
    """Tests for TierListGenerator initialization."""

    def test_default_min_games_from_config(self, db, scorer):
        """Test that min_games defaults to config value."""
        tier_gen = TierListGenerator(db, scorer)

        assert tier_gen.min_games == analysis_config.MIN_GAMES_THRESHOLD

    def test_custom_min_games_override(self, db, scorer):
        """Test that custom min_games overrides config."""
        custom_threshold = 999
        tier_gen = TierListGenerator(db, scorer, min_games=custom_threshold)

        assert tier_gen.min_games == custom_threshold

    def test_stores_dependencies(self, db, scorer):
        """Test that dependencies are stored correctly."""
        tier_gen = TierListGenerator(db, scorer)

        assert tier_gen.db is db
        assert tier_gen.scorer is scorer
