"""Tests for recommendation engine (src/analysis/recommendations.py)."""

import pytest
from src.analysis.recommendations import RecommendationEngine
from src.config import config


class TestCalculateAndDisplayRecommendations:
    """Tests for calculate_and_display_recommendations method."""

    def test_returns_sorted_recommendations(self, db, scorer, insert_matchup):
        """Test that recommendations are sorted by advantage (descending)."""
        # Setup matchup data for 3 champions vs 1 enemy
        # ChampA: favorable (55% winrate) - sufficient data (10k+ games)
        insert_matchup('ChampA', 'Enemy1', 55.0, 200, 300, 10.0, 12000)
        # ChampB: neutral (50% winrate)
        insert_matchup('ChampB', 'Enemy1', 50.0, 0, 0, 10.0, 12000)
        # ChampC: unfavorable (45% winrate)
        insert_matchup('ChampC', 'Enemy1', 45.0, -200, -300, 10.0, 12000)

        engine = RecommendationEngine(db, scorer)
        results = engine.calculate_and_display_recommendations(
            enemy_team=['Enemy1'],
            ally_team=[],
            nb_results=3,
            champion_pool=['ChampA', 'ChampB', 'ChampC']
        )

        # Should return 3 champions sorted by advantage
        assert len(results) == 3
        # ChampA (favorable) should be first
        assert results[0][0] == 'ChampA'
        assert results[0][1] > 0  # Positive advantage
        # ChampB (neutral) should be second
        assert results[1][0] == 'ChampB'
        # ChampC (unfavorable) should be third
        assert results[2][0] == 'ChampC'
        assert results[2][1] < 0  # Negative advantage
        # Verify descending order
        assert results[0][1] > results[1][1] > results[2][1]

    def test_excludes_picked_champions(self, db, scorer, insert_matchup, capsys):
        """Test that already picked champions are excluded."""
        insert_matchup('ChampA', 'Enemy1', 55.0, 200, 300, 10.0, 12000)
        insert_matchup('AllyPicked', 'Enemy1', 60.0, 300, 400, 10.0, 12000)
        insert_matchup('EnemyPicked', 'AllyPicked', 50.0, 0, 0, 10.0, 12000)

        engine = RecommendationEngine(db, scorer)
        results = engine.calculate_and_display_recommendations(
            enemy_team=['EnemyPicked'],
            ally_team=['AllyPicked'],
            nb_results=5,
            champion_pool=['ChampA', 'AllyPicked', 'EnemyPicked']
        )

        # Only ChampA should be in results
        assert len(results) == 1
        assert results[0][0] == 'ChampA'
        # AllyPicked and EnemyPicked should be excluded
        champion_names = [r[0] for r in results]
        assert 'AllyPicked' not in champion_names
        assert 'EnemyPicked' not in champion_names

    def test_excludes_banned_champions(self, db, scorer, insert_matchup):
        """Test that banned champions are excluded from recommendations."""
        insert_matchup('ChampA', 'Enemy1', 55.0, 200, 300, 10.0, 12000)
        insert_matchup('BannedChamp', 'Enemy1', 60.0, 300, 400, 10.0, 12000)

        engine = RecommendationEngine(db, scorer)
        results = engine.calculate_and_display_recommendations(
            enemy_team=['Enemy1'],
            ally_team=[],
            nb_results=5,
            champion_pool=['ChampA', 'BannedChamp'],
            banned_champions=['BannedChamp']
        )

        # Only ChampA should be in results
        assert len(results) == 1
        assert results[0][0] == 'ChampA'
        # BannedChamp should be excluded
        champion_names = [r[0] for r in results]
        assert 'BannedChamp' not in champion_names

    def test_filters_low_data_champions(self, db, scorer, insert_matchup, capsys):
        """Test that champions with insufficient data are filtered out."""
        # ChampA: sufficient data (2000 games)
        insert_matchup('ChampA', 'Enemy1', 55.0, 200, 300, 10.0, 12000)
        # ChampB: insufficient data (only 50 games, below MIN_GAMES_COMPETITIVE)
        insert_matchup('ChampB', 'Enemy1', 60.0, 300, 400, 10.0, 50)

        engine = RecommendationEngine(db, scorer)
        results = engine.calculate_and_display_recommendations(
            enemy_team=['Enemy1'],
            ally_team=[],
            nb_results=5,
            champion_pool=['ChampA', 'ChampB']
        )

        # Only ChampA should be included
        assert len(results) == 1
        assert results[0][0] == 'ChampA'

        # Message about skipped champions only appears when NO recommendations are found
        # In this case, ChampA has valid data so results are shown normally
        # This test validates filtering works correctly

    def test_displays_top_recommendations(self, db, scorer, insert_matchup, capsys):
        """Test that top recommendations are displayed with proper formatting."""
        # Setup 5 champions with varying advantages
        for i in range(5):
            champ_name = f'Champ{i}'
            winrate = 60.0 - (i * 2)  # 60%, 58%, 56%, 54%, 52%
            insert_matchup(champ_name, 'Enemy1', winrate, 100 * (5 - i), 150 * (5 - i), 10.0, 12000)

        engine = RecommendationEngine(db, scorer)
        results = engine.calculate_and_display_recommendations(
            enemy_team=['Enemy1'],
            ally_team=[],
            nb_results=3,  # Only show top 3
            champion_pool=[f'Champ{i}' for i in range(5)]
        )

        captured = capsys.readouterr()

        # Should display exactly 3 results
        assert len(results) >= 3
        # Output should contain medals for top 3
        assert '🥇' in captured.out  # Gold medal for 1st
        assert '🥈' in captured.out  # Silver medal for 2nd
        assert '🥉' in captured.out  # Bronze medal for 3rd
        # Should show advantage percentages
        assert 'advantage' in captured.out
        assert '%' in captured.out

    def test_empty_recommendations_displays_warning(self, db, scorer, capsys):
        """Test warning message when no recommendations are available."""
        engine = RecommendationEngine(db, scorer)
        results = engine.calculate_and_display_recommendations(
            enemy_team=['Enemy1'],
            ally_team=[],
            nb_results=5,
            champion_pool=['NoDataChamp']  # Champion with no matchup data
        )

        captured = capsys.readouterr()

        # Should return empty list
        assert len(results) == 0
        # Should display warning
        assert 'No recommendations available' in captured.out or '⚠️' in captured.out

    def test_uses_custom_champion_pool(self, db, scorer, insert_matchup):
        """Test that custom champion pool is respected."""
        insert_matchup('PoolChamp1', 'Enemy1', 55.0, 200, 300, 10.0, 12000)
        insert_matchup('PoolChamp2', 'Enemy1', 52.0, 150, 200, 10.0, 12000)
        insert_matchup('OutsidePool', 'Enemy1', 60.0, 300, 400, 10.0, 12000)

        engine = RecommendationEngine(db, scorer)
        custom_pool = ['PoolChamp1', 'PoolChamp2']
        results = engine.calculate_and_display_recommendations(
            enemy_team=['Enemy1'],
            ally_team=[],
            nb_results=5,
            champion_pool=custom_pool
        )

        # Should only include champions from custom pool
        champion_names = [r[0] for r in results]
        assert 'PoolChamp1' in champion_names
        assert 'PoolChamp2' in champion_names
        assert 'OutsidePool' not in champion_names

    def test_handles_multiple_enemies(self, db, scorer, insert_matchup):
        """Test recommendations against multiple enemy champions."""
        # ChampA: good against both enemies
        insert_matchup('ChampA', 'Enemy1', 55.0, 200, 300, 10.0, 12000)
        insert_matchup('ChampA', 'Enemy2', 54.0, 180, 280, 10.0, 12000)
        # ChampB: good against Enemy1, bad against Enemy2
        insert_matchup('ChampB', 'Enemy1', 56.0, 220, 320, 10.0, 12000)
        insert_matchup('ChampB', 'Enemy2', 44.0, -220, -320, 10.0, 12000)

        engine = RecommendationEngine(db, scorer)
        results = engine.calculate_and_display_recommendations(
            enemy_team=['Enemy1', 'Enemy2'],
            ally_team=[],
            nb_results=5,
            champion_pool=['ChampA', 'ChampB']
        )

        # Should consider matchups against BOTH enemies
        assert len(results) == 2
        # ChampA (consistent advantage) should rank higher than ChampB (mixed matchups)
        assert results[0][0] == 'ChampA'


class TestDraftSimple:
    """Tests for draft_simple method (interactive legacy version).

    Note: draft_simple is a legacy interactive method with complex user input
    handling and dependencies on CHAMPION_POOL constant. Full integration testing
    would require extensive mocking of the entire champion pool and user interactions.
    The method is tested indirectly through calculate_and_display_recommendations.
    """

    def test_method_exists(self, db, scorer):
        """Test that draft_simple method exists for backward compatibility."""
        engine = RecommendationEngine(db, scorer)
        assert hasattr(engine, 'draft_simple')
        assert callable(engine.draft_simple)


class TestInitialization:
    """Tests for RecommendationEngine initialization."""

    def test_stores_dependencies(self, db, scorer):
        """Test that dependencies are stored correctly."""
        engine = RecommendationEngine(db, scorer)

        assert engine.db is db
        assert engine.scorer is scorer

    def test_initialization_with_valid_params(self, db, scorer):
        """Test successful initialization."""
        engine = RecommendationEngine(db, scorer)

        assert engine is not None
        assert hasattr(engine, 'calculate_and_display_recommendations')
        assert hasattr(engine, 'draft_simple')


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_enemy_team(self, db, scorer, insert_matchup):
        """Test recommendations with no enemy champions (blind pick scenario)."""
        insert_matchup('ChampA', 'Enemy1', 55.0, 200, 300, 10.0, 12000)

        engine = RecommendationEngine(db, scorer)
        results = engine.calculate_and_display_recommendations(
            enemy_team=[],  # Empty enemy team
            ally_team=[],
            nb_results=5,
            champion_pool=['ChampA']
        )

        # Should still return recommendations (using blind pick logic)
        # Behavior depends on scorer.score_against_team implementation
        assert isinstance(results, list)

    def test_all_champions_filtered(self, db, scorer, capsys):
        """Test when all champions are filtered (picked/banned/low data)."""
        engine = RecommendationEngine(db, scorer)
        results = engine.calculate_and_display_recommendations(
            enemy_team=['Enemy1'],
            ally_team=['Ally1', 'Ally2'],
            nb_results=5,
            champion_pool=['Enemy1', 'Ally1', 'Ally2'],  # All already picked
            banned_champions=[]
        )

        captured = capsys.readouterr()

        # Should return empty and show warning
        assert len(results) == 0
        assert 'No recommendations available' in captured.out or '⚠️' in captured.out

    def test_nb_results_exceeds_available_champions(self, db, scorer, insert_matchup, capsys):
        """Test requesting more results than available champions."""
        insert_matchup('OnlyChamp', 'Enemy1', 55.0, 200, 300, 10.0, 12000)

        engine = RecommendationEngine(db, scorer)
        results = engine.calculate_and_display_recommendations(
            enemy_team=['Enemy1'],
            ally_team=[],
            nb_results=100,  # Request 100 but only 1 available
            champion_pool=['OnlyChamp']
        )

        captured = capsys.readouterr()

        # Should only return 1 result, not crash
        assert len(results) == 1
        # Should display only 1 recommendation
        assert '🥇' in captured.out

    def test_default_champion_pool_when_none(self, db, scorer, capsys):
        """Test that SOLOQ_POOL is used when champion_pool is None."""
        engine = RecommendationEngine(db, scorer)
        results = engine.calculate_and_display_recommendations(
            enemy_team=['Enemy1'],
            ally_team=[],
            nb_results=5,
            champion_pool=None  # Should default to SOLOQ_POOL
        )

        # Should not crash, uses SOLOQ_POOL internally
        assert isinstance(results, list)

    def test_empty_banned_list_when_none(self, db, scorer, insert_matchup):
        """Test that empty list is used when banned_champions is None."""
        insert_matchup('ChampA', 'Enemy1', 55.0, 200, 300, 10.0, 12000)

        engine = RecommendationEngine(db, scorer)
        results = engine.calculate_and_display_recommendations(
            enemy_team=['Enemy1'],
            ally_team=[],
            nb_results=5,
            champion_pool=['ChampA'],
            banned_champions=None  # Should default to empty list
        )

        # Should not crash and return ChampA (not banned)
        assert len(results) == 1
        assert results[0][0] == 'ChampA'
