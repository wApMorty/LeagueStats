"""
Functional tests for Tier List generation.

Tests the complete tier list functionality accessible from UI menu option 4.
Validates non-regression and correct S/A/B/C classification.
"""

import pytest


class TestTierListGeneration:
    """Test tier list generation features."""

    def test_generate_blind_pick_tier_list(self, assistant, sample_champions):
        """Test blind pick tier list generation."""
        # Arrange
        champion_pool = sample_champions[:5]  # Use first 5 champions

        # Act
        tier_list = assistant.generate_tier_list(champion_pool, analysis_type="blind_pick")

        # Assert
        assert tier_list is not None, "Tier list should not be None"
        assert isinstance(tier_list, list), "Tier list should be a list"

        # Check that we have results (champions with scores in DB)
        champions_with_scores = [
            c for c in champion_pool if c in ["Aatrox", "Ahri", "Jinx", "Thresh", "Lee Sin"]
        ]
        assert len(tier_list) == len(
            champions_with_scores
        ), f"Should have {len(champions_with_scores)} entries"

        # Validate structure of each entry
        for entry in tier_list:
            assert "champion" in entry, "Entry should have 'champion' field"
            assert "tier" in entry, "Entry should have 'tier' field"
            assert "score" in entry, "Entry should have 'score' field"
            assert "metrics" in entry, "Entry should have 'metrics' field"

            # Validate tier classification
            assert entry["tier"] in ["S", "A", "B", "C"], f"Invalid tier: {entry['tier']}"

            # Validate score range
            assert 0 <= entry["score"] <= 100, f"Score should be 0-100: {entry['score']}"

            # Validate metrics
            metrics = entry["metrics"]
            assert "final_score" in metrics
            assert "avg_performance_norm" in metrics
            assert "stability" in metrics
            assert "coverage_norm" in metrics

    def test_generate_counter_pick_tier_list(self, assistant, sample_champions):
        """Test counter pick tier list generation."""
        # Arrange
        champion_pool = sample_champions[:5]

        # Act
        tier_list = assistant.generate_tier_list(champion_pool, analysis_type="counter_pick")

        # Assert
        assert tier_list is not None
        assert isinstance(tier_list, list)

        for entry in tier_list:
            assert entry["tier"] in ["S", "A", "B", "C"]
            assert 0 <= entry["score"] <= 100

            # Validate counter pick specific metrics
            metrics = entry["metrics"]
            assert "peak_impact_norm" in metrics
            assert "volatility_norm" in metrics
            assert "target_ratio_norm" in metrics

    def test_tier_list_sorted_descending(self, assistant, sample_champions):
        """Test that tier list is sorted by score (descending)."""
        # Arrange
        champion_pool = sample_champions[:5]

        # Act
        tier_list = assistant.generate_tier_list(champion_pool, analysis_type="blind_pick")

        # Assert
        if len(tier_list) > 1:
            scores = [entry["score"] for entry in tier_list]
            assert scores == sorted(scores, reverse=True), "Tier list should be sorted descending"

    def test_tier_classification_thresholds(self, assistant, sample_champions):
        """Test that tier classification follows expected thresholds."""
        # Arrange
        champion_pool = sample_champions[:5]

        # Act
        tier_list = assistant.generate_tier_list(champion_pool, analysis_type="blind_pick")

        # Assert
        # Thresholds from src/config.py TierListConfig:
        # S-Tier: >= 75.0, A-Tier: >= 50.0, B-Tier: >= 25.0, C-Tier: < 25.0
        for entry in tier_list:
            score = entry["score"]
            tier = entry["tier"]

            # Verify tier matches score ranges from config
            if tier == "S":
                assert score >= 75.0, f"S tier should have score >= 75.0: {score}"
            elif tier == "A":
                assert 50.0 <= score < 75.0, f"A tier should have 50.0 <= score < 75.0: {score}"
            elif tier == "B":
                assert 25.0 <= score < 50.0, f"B tier should have 25.0 <= score < 50.0: {score}"
            elif tier == "C":
                assert score < 25.0, f"C tier should have score < 25.0: {score}"

    def test_empty_pool_returns_empty_list(self, assistant):
        """Test that empty champion pool returns empty list."""
        # Act
        tier_list = assistant.generate_tier_list([], analysis_type="blind_pick")

        # Assert
        assert tier_list == [], "Empty pool should return empty list"

    def test_champion_without_scores_skipped(self, assistant):
        """Test that champions without scores in DB are skipped."""
        # Arrange
        # 'Vayne' and 'Leona' don't have scores in test DB
        champion_pool = ["Vayne", "Leona", "NonExistent"]

        # Act
        tier_list = assistant.generate_tier_list(champion_pool, analysis_type="blind_pick")

        # Assert
        assert tier_list == [], "Champions without scores should be skipped"

    def test_invalid_analysis_type_raises_error(self, assistant, sample_champions):
        """Test that invalid analysis type raises ValueError."""
        # Arrange
        champion_pool = sample_champions[:3]

        # Act & Assert
        with pytest.raises(ValueError, match="Unknown analysis type"):
            assistant.generate_tier_list(champion_pool, analysis_type="invalid_type")

    def test_tier_list_consistency_between_calls(self, assistant, sample_champions):
        """Test that multiple calls with same input produce consistent results."""
        # Arrange
        champion_pool = sample_champions[:5]

        # Act
        tier_list_1 = assistant.generate_tier_list(champion_pool, analysis_type="blind_pick")
        tier_list_2 = assistant.generate_tier_list(champion_pool, analysis_type="blind_pick")

        # Assert
        assert len(tier_list_1) == len(tier_list_2), "Results should have same length"

        for entry1, entry2 in zip(tier_list_1, tier_list_2):
            assert entry1["champion"] == entry2["champion"], "Champion order should be consistent"
            assert abs(entry1["score"] - entry2["score"]) < 0.01, "Scores should be identical"
            assert entry1["tier"] == entry2["tier"], "Tiers should be identical"


class TestTierListNonRegression:
    """Non-regression tests for tier list functionality."""

    def test_method_exists_on_assistant(self, assistant):
        """Regression test: Ensure generate_tier_list method exists on Assistant."""
        assert hasattr(
            assistant, "generate_tier_list"
        ), "Assistant must have generate_tier_list method"

    def test_method_callable(self, assistant):
        """Regression test: Ensure method is callable."""
        assert callable(assistant.generate_tier_list), "generate_tier_list must be callable"

    def test_delegation_to_tier_list_generator(self, assistant):
        """Regression test: Ensure Assistant delegates to TierListGenerator."""
        assert hasattr(assistant, "tier_list_gen"), "Assistant must have tier_list_gen attribute"
        assert hasattr(
            assistant.tier_list_gen, "generate_tier_list"
        ), "TierListGenerator must have generate_tier_list method"

    def test_backward_compatibility_with_ui(self, assistant):
        """Regression test: Ensure method signature matches UI expectations."""
        # UI calls: assistant.generate_tier_list(champion_pool, analysis_type)
        champion_pool = ["Aatrox", "Ahri"]

        # Should work with positional args
        result1 = assistant.generate_tier_list(champion_pool, "blind_pick")
        assert result1 is not None

        # Should work with keyword args
        result2 = assistant.generate_tier_list(
            champion_pool=champion_pool, analysis_type="counter_pick"
        )
        assert result2 is not None

    def test_returns_expected_structure(self, assistant):
        """Regression test: Ensure return value structure matches UI expectations."""
        # Arrange
        champion_pool = ["Aatrox", "Ahri", "Jinx"]

        # Act
        tier_list = assistant.generate_tier_list(champion_pool, "blind_pick")

        # Assert - UI expects List[dict] with specific keys
        assert isinstance(tier_list, list), "Must return list"

        if tier_list:  # If we have results
            entry = tier_list[0]
            required_keys = ["champion", "tier", "score", "metrics"]
            for key in required_keys:
                assert key in entry, f"Missing required key: {key}"
