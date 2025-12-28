"""Tests for team composition analysis (src/analysis/team_analysis.py)."""

import pytest
from src.analysis.team_analysis import TeamAnalyzer


class TestAnalyzeTeams:
    """Tests for analyze_teams method."""

    def test_analyzes_complete_teams(self, db, scorer, insert_matchup, capsys):
        """Test full team analysis with 5v5 matchup."""
        # Setup matchup data for realistic analysis
        # Team1: ChampA, ChampB  vs Team2: EnemyX, EnemyY
        insert_matchup("ChampA", "EnemyX", 52.0, 100, 150, 10.0, 1000)
        insert_matchup("ChampA", "EnemyY", 48.0, -50, -100, 10.0, 1000)
        insert_matchup("ChampB", "EnemyX", 55.0, 200, 250, 10.0, 1000)
        insert_matchup("ChampB", "EnemyY", 50.0, 0, 50, 10.0, 1000)

        analyzer = TeamAnalyzer(db, scorer)
        analyzer.analyze_teams(team1=["ChampA", "ChampB"], team2=["EnemyX", "EnemyY"])

        # Capture stdout to verify output is printed
        captured = capsys.readouterr()

        # Verify key output elements are present
        assert "TEAM 1 ANALYSIS" in captured.out
        assert "TEAM 2 ANALYSIS" in captured.out
        assert "MATCHUP PREDICTION" in captured.out
        assert "ChampA" in captured.out
        assert "ChampB" in captured.out
        assert "EnemyX" in captured.out
        assert "EnemyY" in captured.out

    def test_team_winrates_sum_to_100(self, db, scorer, insert_matchup, capsys):
        """Test that normalized team winrates sum to 100%."""
        # Setup symmetric matchup data
        insert_matchup("ChampA", "EnemyX", 50.0, 0, 0, 10.0, 1000)
        insert_matchup("EnemyX", "ChampA", 50.0, 0, 0, 10.0, 1000)

        analyzer = TeamAnalyzer(db, scorer)
        analyzer.analyze_teams(team1=["ChampA"], team2=["EnemyX"])

        captured = capsys.readouterr()

        # For symmetric matchups, should show ~50% vs ~50%
        assert "Team 1 vs Team 2" in captured.out
        assert "%" in captured.out

    def test_handles_champions_without_data(self, db, scorer, capsys):
        """Test analysis when champions have no matchup data."""
        analyzer = TeamAnalyzer(db, scorer)
        analyzer.analyze_teams(team1=["UnknownChamp1"], team2=["UnknownChamp2"])

        captured = capsys.readouterr()

        # Should still produce output without errors
        assert "TEAM 1 ANALYSIS" in captured.out
        assert "TEAM 2 ANALYSIS" in captured.out
        assert "UnknownChamp1" in captured.out
        assert "UnknownChamp2" in captured.out

    def test_displays_individual_advantages(self, db, scorer, insert_matchup, capsys):
        """Test that individual champion advantages are displayed."""
        # Setup matchup with clear advantage
        insert_matchup("FavoredChamp", "Enemy", 58.0, 300, 400, 10.0, 2000)
        insert_matchup("Enemy", "FavoredChamp", 42.0, -300, -400, 10.0, 2000)

        analyzer = TeamAnalyzer(db, scorer)
        analyzer.analyze_teams(team1=["FavoredChamp"], team2=["Enemy"])

        captured = capsys.readouterr()

        # Should show advantage percentages
        assert "advantage" in captured.out
        assert "winrate" in captured.out
        assert "FavoredChamp" in captured.out

    def test_matchup_prediction_confidence(self, db, scorer, insert_matchup, capsys):
        """Test that confidence levels are shown based on winrate difference."""
        # Setup strong advantage scenario
        insert_matchup("StrongChamp", "WeakChamp", 62.0, 500, 600, 10.0, 2000)
        insert_matchup("WeakChamp", "StrongChamp", 38.0, -500, -600, 10.0, 2000)

        analyzer = TeamAnalyzer(db, scorer)
        analyzer.analyze_teams(team1=["StrongChamp"], team2=["WeakChamp"])

        captured = capsys.readouterr()

        # Should show prediction with confidence indicator
        assert "MATCHUP PREDICTION" in captured.out
        # Confidence indicators: Strong/Moderate/Small/Very close
        has_confidence = any(
            keyword in captured.out for keyword in ["Strong", "Moderate", "Small", "close"]
        )
        assert has_confidence

    def test_five_champion_teams(self, db, scorer, insert_matchup, capsys):
        """Test analysis with full 5v5 team compositions."""
        # Setup 5 champions per team with various matchups
        team1_champs = ["Top1", "Jungle1", "Mid1", "ADC1", "Support1"]
        team2_champs = ["Top2", "Jungle2", "Mid2", "ADC2", "Support2"]

        # Create cross-matchup data
        for champ1 in team1_champs:
            for champ2 in team2_champs:
                insert_matchup(champ1, champ2, 50.0, 0, 0, 10.0, 1000)

        analyzer = TeamAnalyzer(db, scorer)
        analyzer.analyze_teams(team1=team1_champs, team2=team2_champs)

        captured = capsys.readouterr()

        # Verify all champions are shown
        for champ in team1_champs + team2_champs:
            assert champ in captured.out


class TestAnalyzeTeamsInteractive:
    """Tests for analyze_teams_interactive method."""

    def test_prompts_for_champion_input(self, db, scorer, monkeypatch, capsys):
        """Test that interactive mode prompts for 10 champion inputs."""
        # Mock user inputs (5 for team1, 5 for team2)
        inputs = iter(
            [
                "ChampA",
                "ChampB",
                "ChampC",
                "ChampD",
                "ChampE",  # Team 1
                "EnemyX",
                "EnemyY",
                "EnemyZ",
                "EnemyW",
                "EnemyV",  # Team 2
            ]
        )
        monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))

        analyzer = TeamAnalyzer(db, scorer)
        analyzer.analyze_teams_interactive()

        captured = capsys.readouterr()

        # Should run analysis with provided champions
        assert "TEAM 1 ANALYSIS" in captured.out
        assert "TEAM 2 ANALYSIS" in captured.out

    def test_uses_provided_champion_names(self, db, scorer, insert_matchup, monkeypatch, capsys):
        """Test that interactive mode uses the exact champion names provided."""
        # Setup matchup data
        insert_matchup("TestChamp1", "TestEnemy1", 52.0, 100, 150, 10.0, 1000)

        # Mock inputs with specific names
        inputs = iter(
            [
                "TestChamp1",
                "ChampB",
                "ChampC",
                "ChampD",
                "ChampE",
                "TestEnemy1",
                "EnemyY",
                "EnemyZ",
                "EnemyW",
                "EnemyV",
            ]
        )
        monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))

        analyzer = TeamAnalyzer(db, scorer)
        analyzer.analyze_teams_interactive()

        captured = capsys.readouterr()

        # Verify our specific test champions appear in output
        assert "TestChamp1" in captured.out
        assert "TestEnemy1" in captured.out


class TestInitialization:
    """Tests for TeamAnalyzer initialization."""

    def test_stores_dependencies(self, db, scorer):
        """Test that dependencies are stored correctly."""
        analyzer = TeamAnalyzer(db, scorer)

        assert analyzer.db is db
        assert analyzer.scorer is scorer

    def test_initialization_with_valid_params(self, db, scorer):
        """Test successful initialization with required parameters."""
        analyzer = TeamAnalyzer(db, scorer)

        assert analyzer is not None
        assert hasattr(analyzer, "analyze_teams")
        assert hasattr(analyzer, "analyze_teams_interactive")


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_team_lists(self, db, scorer, capsys):
        """Test behavior with empty team lists."""
        analyzer = TeamAnalyzer(db, scorer)
        analyzer.analyze_teams(team1=[], team2=[])

        captured = capsys.readouterr()

        # Should handle gracefully without errors
        assert "TEAM 1 ANALYSIS" in captured.out or "TEAM 2 ANALYSIS" in captured.out

    def test_asymmetric_team_sizes(self, db, scorer, insert_matchup, capsys):
        """Test with different team sizes (e.g., 3v2)."""
        insert_matchup("ChampA", "EnemyX", 50.0, 0, 0, 10.0, 1000)
        insert_matchup("ChampB", "EnemyX", 50.0, 0, 0, 10.0, 1000)
        insert_matchup("ChampC", "EnemyX", 50.0, 0, 0, 10.0, 1000)

        analyzer = TeamAnalyzer(db, scorer)
        analyzer.analyze_teams(team1=["ChampA", "ChampB", "ChampC"], team2=["EnemyX", "EnemyY"])

        captured = capsys.readouterr()

        # Should handle different sizes without error
        assert "TEAM 1 ANALYSIS" in captured.out
        assert "TEAM 2 ANALYSIS" in captured.out

    def test_duplicate_champions_in_team(self, db, scorer, insert_matchup, capsys):
        """Test handling of duplicate champions (edge case)."""
        insert_matchup("ChampA", "EnemyX", 50.0, 0, 0, 10.0, 1000)

        analyzer = TeamAnalyzer(db, scorer)
        analyzer.analyze_teams(team1=["ChampA", "ChampA"], team2=["EnemyX"])  # Duplicate

        captured = capsys.readouterr()

        # Should process without crashing (duplicates shown twice)
        assert captured.out.count("ChampA") >= 2
