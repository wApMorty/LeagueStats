"""Regression test for bug "Multiple rows" in get_synergy_delta2.

Bug Report:
-----------
Function: server/src/db.py::Database.get_synergy_delta2()
Error: "Multiple rows were found when one or none was required"
Cause: synergies table contains multiple rows for champion-ally pairs (multi-lane data)
       Old code used scalar_one_or_none() which expects 0 or 1 row

Fix Applied:
-----------
1. Changed select() to fetch both delta2 AND games columns
2. Changed scalar_one_or_none() to all() to fetch all rows
3. Calculate weighted average in Python: SUM(delta2 * games) / SUM(games)
4. Return None if no rows found

This test ensures the bug never resurfaces by testing with multi-lane data.

Author: Python Expert (Claude Sonnet 4.5)
Created: 2026-02-13
Sprint: 2 - Tâche #16 (Support des Synergies)
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from server.src.db import Database


class TestGetSynergyDelta2MultiLaneRegression:
    """Regression tests for get_synergy_delta2 with multi-lane data."""

    def test_single_row_synergy(self):
        """Test get_synergy_delta2 with single row (normal case)."""
        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()

            if call_count[0] == 1:  # Champion ID query
                result.scalar_one_or_none.return_value = 1
            elif call_count[0] == 2:  # Ally ID query
                result.scalar_one_or_none.return_value = 2
            elif call_count[0] == 3:  # Synergy query - single row
                row = MagicMock()
                row.delta2 = 220.0
                row.games = 1200
                result.all.return_value = [row]

            return result

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.close = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_session_maker = MagicMock(return_value=mock_session)

        db = Database()
        with patch("server.src.db.get_session_maker", return_value=mock_session_maker):
            result = db.get_synergy_delta2("Yasuo", "Malphite")

        # Single row: weighted average = delta2 itself
        assert result == pytest.approx(220.0, abs=0.01)

    def test_multi_lane_synergy_aggregation(self):
        """Test get_synergy_delta2 with multiple rows (multi-lane data).

        This is the REGRESSION TEST for the "Multiple rows" bug.
        """
        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()

            if call_count[0] == 1:  # Champion ID query
                result.scalar_one_or_none.return_value = 1
            elif call_count[0] == 2:  # Ally ID query
                result.scalar_one_or_none.return_value = 2
            elif call_count[0] == 3:  # Synergy query - MULTIPLE rows (multi-lane)
                row1 = MagicMock()
                row1.delta2 = 220.0
                row1.games = 800

                row2 = MagicMock()
                row2.delta2 = 180.0
                row2.games = 400

                row3 = MagicMock()
                row3.delta2 = 200.0
                row3.games = 600

                result.all.return_value = [row1, row2, row3]

            return result

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.close = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_session_maker = MagicMock(return_value=mock_session)

        db = Database()
        with patch("server.src.db.get_session_maker", return_value=mock_session_maker):
            result = db.get_synergy_delta2("Yasuo", "Malphite")

        # Expected weighted average: (220*800 + 180*400 + 200*600) / (800+400+600)
        # = (176000 + 72000 + 120000) / 1800 = 368000 / 1800 = 204.44
        expected = (220.0 * 800 + 180.0 * 400 + 200.0 * 600) / (800 + 400 + 600)
        assert result == pytest.approx(expected, abs=0.01)

    def test_no_synergy_data(self):
        """Test get_synergy_delta2 with no matching rows."""
        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()

            if call_count[0] == 1:  # Champion ID query
                result.scalar_one_or_none.return_value = 1
            elif call_count[0] == 2:  # Ally ID query
                result.scalar_one_or_none.return_value = 2
            elif call_count[0] == 3:  # Synergy query - NO rows
                result.all.return_value = []

            return result

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.close = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_session_maker = MagicMock(return_value=mock_session)

        db = Database()
        with patch("server.src.db.get_session_maker", return_value=mock_session_maker):
            result = db.get_synergy_delta2("Yasuo", "Malphite")

        # No rows = None
        assert result is None

    def test_champion_not_found(self):
        """Test get_synergy_delta2 when champion doesn't exist."""
        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()

            if call_count[0] == 1:  # Champion ID query - not found
                result.scalar_one_or_none.return_value = None

            return result

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.close = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_session_maker = MagicMock(return_value=mock_session)

        db = Database()
        with patch("server.src.db.get_session_maker", return_value=mock_session_maker):
            result = db.get_synergy_delta2("InvalidChampion", "Malphite")

        # Champion not found = None
        assert result is None

    def test_ally_not_found(self):
        """Test get_synergy_delta2 when ally doesn't exist."""
        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()

            if call_count[0] == 1:  # Champion ID query
                result.scalar_one_or_none.return_value = 1
            elif call_count[0] == 2:  # Ally ID query - not found
                result.scalar_one_or_none.return_value = None

            return result

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.close = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_session_maker = MagicMock(return_value=mock_session)

        db = Database()
        with patch("server.src.db.get_session_maker", return_value=mock_session_maker):
            result = db.get_synergy_delta2("Yasuo", "InvalidAlly")

        # Ally not found = None
        assert result is None

    def test_weighted_average_with_unequal_games(self):
        """Test weighted average calculation with very unequal game counts."""
        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            result = MagicMock()

            if call_count[0] == 1:  # Champion ID query
                result.scalar_one_or_none.return_value = 1
            elif call_count[0] == 2:  # Ally ID query
                result.scalar_one_or_none.return_value = 2
            elif call_count[0] == 3:  # Synergy query - very unequal games
                row1 = MagicMock()
                row1.delta2 = 300.0
                row1.games = 10  # Low weight

                row2 = MagicMock()
                row2.delta2 = 200.0
                row2.games = 990  # High weight

                result.all.return_value = [row1, row2]

            return result

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.close = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_session_maker = MagicMock(return_value=mock_session)

        db = Database()
        with patch("server.src.db.get_session_maker", return_value=mock_session_maker):
            result = db.get_synergy_delta2("Yasuo", "Malphite")

        # Expected: (300*10 + 200*990) / (10+990) = (3000 + 198000) / 1000 = 201.0
        expected = (300.0 * 10 + 200.0 * 990) / (10 + 990)
        assert result == pytest.approx(expected, abs=0.01)
        # Result should be very close to 200.0 (high weight dominates)
        assert result == pytest.approx(201.0, abs=0.01)
