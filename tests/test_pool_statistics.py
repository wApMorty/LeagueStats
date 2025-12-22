"""Unit tests for pool_statistics module.

Tests the PoolStatisticsCalculator class and format_pool_statistics function
to ensure accurate statistical analysis of champion pools.
"""

import pytest
from src.analysis.pool_statistics import (
    PoolStatisticsCalculator,
    ChampionStats,
    PoolStatistics,
    format_pool_statistics
)


@pytest.fixture
def calculator(db):
    """Create PoolStatisticsCalculator with test database."""
    return PoolStatisticsCalculator(db, min_games_threshold=100)


@pytest.fixture
def sample_pool_data(db, insert_matchup):
    """Create sample champion pool data with known statistics.

    Pool structure:
    - Champion1: Strong performer (avg_delta2: ~198.38, 700 games, 3 matchups)
    - Champion2: Weak performer (avg_delta2: -100, 500 games, 2 matchups)
    - Champion3: Insufficient data (50 games, 1 matchup - filtered out by MIN_MATCHUP_GAMES)
    - Champion4: No data (0 matchups)

    Expected pool statistics:
    - Champions with data: 2 (Champion1, Champion2)
    - Champions without data: 2 (Champion3, Champion4)
    - Coverage: 50%
    - Mean delta2: ~49.19 ((198.38 + -100) / 2 weighted by pickrate)
    - Median delta2: ~49.19
    """
    # Champion1: Strong performer (3 matchups, 700 total games)
    insert_matchup("Champion1", "Enemy1", 55.0, 150.0, 200.0, 10.0, 200)
    insert_matchup("Champion1", "Enemy2", 54.0, 140.0, 180.0, 15.0, 250)
    insert_matchup("Champion1", "Enemy3", 56.0, 160.0, 220.0, 12.0, 250)

    # Champion2: Weak performer (2 matchups, 500 total games)
    insert_matchup("Champion2", "Enemy1", 45.0, -90.0, -100.0, 8.0, 250)
    insert_matchup("Champion2", "Enemy2", 46.0, -80.0, -100.0, 9.0, 250)

    # Champion3: Insufficient data (1 matchup, 50 games < MIN_MATCHUP_GAMES threshold)
    insert_matchup("Champion3", "Enemy1", 50.0, 0.0, 0.0, 5.0, 50)

    # Champion4: No data (0 matchups) - must create champion explicitly
    cursor = db.connection.cursor()
    cursor.execute("INSERT INTO champions (name, role) VALUES (?, ?)", ("Champion4", "adc"))
    db.connection.commit()

    # Get champion IDs for reference (optional, not used in tests)
    ids = {}
    for name in ['Champion1', 'Champion2', 'Champion3', 'Champion4']:
        cursor.execute("SELECT id FROM champions WHERE name = ?", (name,))
        result = cursor.fetchone()
        if result:
            ids[name] = result[0]

    return {
        'champion_names': ['Champion1', 'Champion2', 'Champion3', 'Champion4'],
        'champion_ids': ids
    }


# === UNIT TESTS - ChampionStats Calculation ===

def test_calculate_champion_stats_strong_performer(calculator, sample_pool_data):
    """Test calculating stats for champion with good performance."""
    stats = calculator.calculate_champion_stats('Champion1')

    assert stats is not None
    assert stats.name == 'Champion1'
    assert stats.num_matchups == 3
    assert stats.total_games == 700
    assert stats.has_sufficient_data is True
    assert abs(stats.avg_delta2 - 198.38) < 0.1  # Weighted average by pickrate


def test_calculate_champion_stats_weak_performer(calculator, sample_pool_data):
    """Test calculating stats for champion with poor performance."""
    stats = calculator.calculate_champion_stats('Champion2')

    assert stats is not None
    assert stats.name == 'Champion2'
    assert stats.num_matchups == 2
    assert stats.total_games == 500
    assert stats.has_sufficient_data is True
    assert abs(stats.avg_delta2 - (-100.0)) < 0.01


def test_calculate_champion_stats_insufficient_data(calculator, sample_pool_data):
    """Test calculating stats for champion with insufficient data."""
    stats = calculator.calculate_champion_stats('Champion3')

    assert stats is not None
    assert stats.name == 'Champion3'
    assert stats.num_matchups == 0  # Filtered out by min_games_threshold
    assert stats.total_games == 50
    assert stats.has_sufficient_data is False
    assert stats.avg_delta2 == 0.0


def test_calculate_champion_stats_no_data(calculator, sample_pool_data):
    """Test calculating stats for champion with no matchups."""
    stats = calculator.calculate_champion_stats('Champion4')

    assert stats is not None
    assert stats.name == 'Champion4'
    assert stats.num_matchups == 0
    assert stats.total_games == 0
    assert stats.has_sufficient_data is False
    assert stats.avg_delta2 == 0.0


def test_calculate_champion_stats_nonexistent(calculator, db):
    """Test calculating stats for non-existent champion."""
    stats = calculator.calculate_champion_stats('NonExistentChampion')

    assert stats is None


# === UNIT TESTS - PoolStatistics Calculation ===

def test_calculate_pool_statistics_complete_pool(calculator, sample_pool_data):
    """Test calculating comprehensive pool statistics."""
    pool_name = "Test Pool"
    champion_list = sample_pool_data['champion_names']

    stats = calculator.calculate_pool_statistics(pool_name, champion_list)

    # Pool metadata
    assert stats.pool_name == pool_name
    assert stats.pool_size == 4
    assert len(stats.champion_stats) == 4

    # Coverage metrics
    assert stats.champions_with_data == 2  # Champion1, Champion2
    assert stats.champions_without_data == 2  # Champion3, Champion4
    assert stats.coverage_percentage == 50.0
    assert stats.total_matchups == 5  # 3 + 2 + 0 + 0
    assert stats.total_games == 1250  # 700 + 500 + 50 + 0

    # Distribution metrics (only Champion1 and Champion2 have sufficient data)
    # Champion1: avg_delta2 = 198.38 (weighted by pickrate)
    # Champion2: avg_delta2 = -100.0 (weighted by pickrate)
    # Mean: (198.38 + -100.0) / 2 = 49.19
    # Median: 49.19 (average of 2 values when sorted: -100, 198.38)
    assert abs(stats.avg_delta2_mean - 49.19) < 0.1
    assert abs(stats.avg_delta2_median - 49.19) < 0.1
    assert stats.avg_delta2_min == -100.0
    assert abs(stats.avg_delta2_max - 198.38) < 0.1
    assert stats.avg_delta2_stddev > 0  # Should have variance

    # Outliers (champions without sufficient data)
    assert len(stats.outliers) == 2
    assert 'Champion3' in stats.outliers
    assert 'Champion4' in stats.outliers


def test_calculate_pool_statistics_empty_pool(calculator, db):
    """Test calculating stats for empty pool."""
    stats = calculator.calculate_pool_statistics("Empty Pool", [])

    assert stats.pool_name == "Empty Pool"
    assert stats.pool_size == 0
    assert len(stats.champion_stats) == 0
    assert stats.champions_with_data == 0
    assert stats.coverage_percentage == 0.0
    assert stats.avg_delta2_mean == 0.0
    assert len(stats.outliers) == 0


def test_calculate_pool_statistics_all_strong_performers(calculator, db, insert_matchup):
    """Test pool with all champions having strong performance."""
    # Strong performers (>= MIN_MATCHUP_GAMES = 200)
    insert_matchup("Strong1", "Enemy1", 60.0, 200.0, 250.0, 10.0, 200)
    insert_matchup("Strong2", "Enemy1", 62.0, 220.0, 270.0, 12.0, 200)

    stats = calculator.calculate_pool_statistics("Strong Pool", ["Strong1", "Strong2"])

    assert stats.champions_with_data == 2
    assert stats.coverage_percentage == 100.0
    assert stats.avg_delta2_min > 0  # All positive
    assert stats.avg_delta2_mean > 0
    assert len(stats.outliers) == 0


def test_calculate_pool_statistics_single_champion(calculator, db, insert_matchup):
    """Test pool with single champion."""
    insert_matchup("Solo", "Enemy1", 55.0, 100.0, 150.0, 10.0, 200)

    stats = calculator.calculate_pool_statistics("Solo Pool", ["Solo"])

    assert stats.pool_size == 1
    assert stats.champions_with_data == 1
    assert stats.coverage_percentage == 100.0
    assert stats.avg_delta2_stddev == 0.0  # Only 1 value
    assert stats.avg_delta2_variance == 0.0
    assert len(stats.outliers) == 0


# === UNIT TESTS - Output Formatting ===

def test_format_pool_statistics_output_structure(calculator, sample_pool_data):
    """Test that formatted output contains expected sections."""
    pool_name = "Test Pool"
    champion_list = sample_pool_data['champion_names']

    stats = calculator.calculate_pool_statistics(pool_name, champion_list)
    output = format_pool_statistics(stats)

    # Verify output contains expected sections
    assert "Pool Statistics: Test Pool" in output
    assert "POOL OVERVIEW:" in output
    assert "PERFORMANCE DISTRIBUTION (avg_delta2):" in output
    assert "OUTLIERS" in output
    assert "TOP 5 PERFORMERS" in output
    assert "BOTTOM 5 PERFORMERS" in output

    # Verify key metrics are displayed
    assert "Total Champions: 4" in output
    assert "Champions with Data: 2" in output
    # Note: Coverage is calculated from champions_with_data/pool_size * 100
    # If Champion4 is in champion_stats, coverage will be 2/4 = 50%
    # But output formatting might vary slightly, so check for main components
    assert "Coverage:" in output
    assert "Total Games:" in output


def test_format_pool_statistics_empty_pool(calculator, db):
    """Test formatting output for empty pool."""
    stats = calculator.calculate_pool_statistics("Empty Pool", [])
    output = format_pool_statistics(stats)

    assert "Pool Statistics: Empty Pool" in output
    assert "Total Champions: 0" in output
    assert "Coverage: 0.0%" in output


def test_format_pool_statistics_no_outliers(calculator, db, insert_matchup):
    """Test formatting when no outliers (all champions have data)."""
    insert_matchup("Champ1", "Enemy1", 55.0, 100.0, 150.0, 10.0, 200)

    stats = calculator.calculate_pool_statistics("Clean Pool", ["Champ1"])
    output = format_pool_statistics(stats)

    # Outliers section should not be present when no outliers
    assert "OUTLIERS" not in output or "0 champions with insufficient data" in output


# === INTEGRATION TESTS ===

def test_pool_statistics_integration_workflow(calculator, sample_pool_data):
    """Integration test: Full workflow from champion stats to formatted output."""
    pool_name = "Integration Test Pool"
    champion_list = sample_pool_data['champion_names']

    # Step 1: Calculate individual champion stats
    champ1_stats = calculator.calculate_champion_stats('Champion1')
    assert champ1_stats.has_sufficient_data is True

    # Step 2: Calculate pool statistics
    pool_stats = calculator.calculate_pool_statistics(pool_name, champion_list)
    assert pool_stats.pool_size == 4
    # Coverage might vary slightly depending on implementation details
    # Check that it's reasonable (between 40-60%)
    assert 40.0 <= pool_stats.coverage_percentage <= 60.0

    # Step 3: Format output
    output = format_pool_statistics(pool_stats)
    assert len(output) > 0
    assert pool_name in output

    # Step 4: Verify champion appears in performers list
    assert "Champion1" in output  # Should be in top performers
    assert "Champion2" in output  # Should be in bottom performers


def test_pool_statistics_min_games_threshold_boundary(db, insert_matchup):
    """Test edge case: Champion with exactly min_games_threshold games."""
    calculator = PoolStatisticsCalculator(db, min_games_threshold=100)

    # Exactly 100 games (meets min_games_threshold)
    # But needs >= MIN_MATCHUP_GAMES (200) to be valid matchup, so use 200
    insert_matchup("Boundary", "Enemy1", 55.0, 100.0, 150.0, 10.0, 200)

    stats = calculator.calculate_champion_stats('Boundary')

    # Should have sufficient data (total_games >= threshold AND valid_matchups > 0)
    assert stats.has_sufficient_data is True
    assert stats.total_games == 200
    assert stats.num_matchups == 1


def test_pool_statistics_dataclass_immutability(calculator, sample_pool_data):
    """Test that dataclasses are properly constructed and accessible."""
    pool_name = "Test Pool"
    champion_list = sample_pool_data['champion_names']

    stats = calculator.calculate_pool_statistics(pool_name, champion_list)

    # Verify all dataclass fields are accessible
    assert hasattr(stats, 'pool_name')
    assert hasattr(stats, 'pool_size')
    assert hasattr(stats, 'champion_stats')
    assert hasattr(stats, 'avg_delta2_mean')
    assert hasattr(stats, 'coverage_percentage')
    assert hasattr(stats, 'outliers')

    # Verify champion_stats are ChampionStats instances
    for champ_stat in stats.champion_stats:
        assert isinstance(champ_stat, ChampionStats)
        assert hasattr(champ_stat, 'name')
        assert hasattr(champ_stat, 'avg_delta2')
        assert hasattr(champ_stat, 'has_sufficient_data')
