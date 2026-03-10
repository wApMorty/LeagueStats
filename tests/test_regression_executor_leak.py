"""
Regression tests for bug: Executor leak in ParallelParser causing multiple Firefox instances.

Bug description:
    When parse_all_champions() was followed by parse_all_synergies() (or vice-versa),
    a new ThreadPoolExecutor was created without shutting down the old one. This caused
    20 Firefox + 20 geckodriver processes to run simultaneously (2x max_workers) because
    both thread pools co-existed and their Parser instances were never cleaned up.

    Symptom: 20 Firefox + 20 geckodriver processes simultaneously when only 10 expected.

Fixed in: T2 (2026-03-10)
    - Added _cleanup_existing_resources() method to ParallelParser
    - Called at the beginning of parse_all_champions(), parse_all_synergies(),
      parse_champions_by_role(), and parse_synergies_by_role()
    - Method shuts down existing executor (wait=True) and closes all existing parsers

Test approach:
    All tests use mocks to avoid creating real Firefox/geckodriver processes.
    Parser.__init__ and Parser.close are patched throughout.
"""

import pytest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, MagicMock, patch, call, patch as mock_patch


class TestCleanupExistingResourcesExecutor:
    """Tests for _cleanup_existing_resources() - executor shutdown behaviour."""

    def test_cleanup_shuts_down_existing_executor(self):
        """
        Regression: _cleanup_existing_resources() must call shutdown(wait=True) on existing executor.

        Before fix: No cleanup, old executor kept running alongside new one.
        After fix: executor.shutdown(wait=True) called, self.executor set to None.
        """
        # GIVEN: A ParallelParser with a mock executor already set
        with patch("src.parallel_parser.Parser") as mock_parser_class:
            mock_parser_class.return_value = Mock()

            from src.parallel_parser import ParallelParser

            pp = ParallelParser(max_workers=3)

            mock_executor = Mock(spec=ThreadPoolExecutor)
            pp.executor = mock_executor

            # WHEN: _cleanup_existing_resources() is called
            pp._cleanup_existing_resources()

            # THEN: shutdown(wait=True) must have been called
            mock_executor.shutdown.assert_called_once_with(wait=True)

    def test_cleanup_sets_executor_to_none_after_shutdown(self):
        """
        Regression: After shutdown, self.executor must be None (not a closed executor).

        Before fix: self.executor retained reference to closed executor.
        After fix: self.executor = None after shutdown.
        """
        # GIVEN: A ParallelParser with a mock executor already set
        with patch("src.parallel_parser.Parser") as mock_parser_class:
            mock_parser_class.return_value = Mock()

            from src.parallel_parser import ParallelParser

            pp = ParallelParser(max_workers=3)

            mock_executor = Mock(spec=ThreadPoolExecutor)
            pp.executor = mock_executor

            # WHEN: _cleanup_existing_resources() is called
            pp._cleanup_existing_resources()

            # THEN: self.executor must be None
            assert pp.executor is None

    def test_cleanup_does_nothing_when_executor_is_none(self):
        """
        Regression: _cleanup_existing_resources() must be safe to call when no executor exists.

        Scenario: First call to parse_* has no previous executor to clean up.
        """
        # GIVEN: A ParallelParser with no executor (freshly created)
        with patch("src.parallel_parser.Parser") as mock_parser_class:
            mock_parser_class.return_value = Mock()

            from src.parallel_parser import ParallelParser

            pp = ParallelParser(max_workers=3)

            assert pp.executor is None

            # WHEN: _cleanup_existing_resources() is called
            # THEN: No exception should be raised
            pp._cleanup_existing_resources()

            # THEN: executor remains None
            assert pp.executor is None


class TestCleanupExistingResourcesParsers:
    """Tests for _cleanup_existing_resources() - parser cleanup behaviour."""

    def test_cleanup_calls_close_on_all_existing_parsers(self):
        """
        Regression: _cleanup_existing_resources() must call close() on each existing parser.

        Before fix: Old parser instances never closed -> zombie Firefox processes.
        After fix: close() called on every parser in self.parsers before clearing.
        """
        # GIVEN: A ParallelParser with 3 mock parsers already tracked
        with patch("src.parallel_parser.Parser") as mock_parser_class:
            mock_parser_class.return_value = Mock()

            from src.parallel_parser import ParallelParser

            pp = ParallelParser(max_workers=3)

            mock_parser_1 = Mock()
            mock_parser_2 = Mock()
            mock_parser_3 = Mock()
            pp.parsers = [mock_parser_1, mock_parser_2, mock_parser_3]

            # WHEN: _cleanup_existing_resources() is called
            pp._cleanup_existing_resources()

            # THEN: close() must be called on each parser
            mock_parser_1.close.assert_called_once()
            mock_parser_2.close.assert_called_once()
            mock_parser_3.close.assert_called_once()

    def test_cleanup_clears_parsers_list_after_closing(self):
        """
        Regression: After cleanup, self.parsers must be empty.

        Before fix: Stale parser references remained in self.parsers.
        After fix: self.parsers.clear() called -> empty list.
        """
        # GIVEN: A ParallelParser with mock parsers
        with patch("src.parallel_parser.Parser") as mock_parser_class:
            mock_parser_class.return_value = Mock()

            from src.parallel_parser import ParallelParser

            pp = ParallelParser(max_workers=3)

            pp.parsers = [Mock(), Mock()]

            # WHEN: _cleanup_existing_resources() is called
            pp._cleanup_existing_resources()

            # THEN: parsers list must be empty
            assert pp.parsers == []

    def test_cleanup_does_nothing_when_parsers_list_is_empty(self):
        """
        Regression: _cleanup_existing_resources() must be safe with empty parsers list.

        Scenario: First invocation - no parsers have been created yet.
        """
        # GIVEN: A ParallelParser with no parsers
        with patch("src.parallel_parser.Parser") as mock_parser_class:
            mock_parser_class.return_value = Mock()

            from src.parallel_parser import ParallelParser

            pp = ParallelParser(max_workers=3)

            assert pp.parsers == []

            # WHEN: _cleanup_existing_resources() is called
            # THEN: No exception should be raised
            pp._cleanup_existing_resources()

            # THEN: parsers remains empty
            assert pp.parsers == []

    def test_cleanup_continues_if_one_parser_close_raises(self):
        """
        Regression: _cleanup_existing_resources() must not abort if one parser.close() raises.

        Scenario: First parser fails to close (e.g. geckodriver already crashed),
        but remaining parsers must still be closed.
        """
        # GIVEN: 3 parsers where the first one raises on close()
        with patch("src.parallel_parser.Parser") as mock_parser_class:
            mock_parser_class.return_value = Mock()

            from src.parallel_parser import ParallelParser

            pp = ParallelParser(max_workers=3)

            failing_parser = Mock()
            failing_parser.close.side_effect = RuntimeError("geckodriver crashed")
            ok_parser_1 = Mock()
            ok_parser_2 = Mock()

            pp.parsers = [failing_parser, ok_parser_1, ok_parser_2]

            # WHEN: _cleanup_existing_resources() is called
            # THEN: Should not raise, should continue past the failing parser
            pp._cleanup_existing_resources()

            # THEN: All parsers attempted to close
            failing_parser.close.assert_called_once()
            ok_parser_1.close.assert_called_once()
            ok_parser_2.close.assert_called_once()

            # THEN: parsers list cleared despite failure
            assert pp.parsers == []


class TestParseAllChampionsCallsCleanup:
    """Tests verifying parse_all_champions() calls _cleanup_existing_resources() first."""

    def test_parse_all_champions_calls_cleanup_before_creating_executor(self):
        """
        Regression: parse_all_champions() must call _cleanup_existing_resources() before
        creating a new ThreadPoolExecutor.

        Before fix: New executor created without cleaning up old one.
        After fix: _cleanup_existing_resources() called first.
        """
        # GIVEN: A ParallelParser with _cleanup_existing_resources mocked
        with patch("src.parallel_parser.Parser") as mock_parser_class:
            mock_parser_class.return_value = Mock()

            from src.parallel_parser import ParallelParser

            pp = ParallelParser(max_workers=2)

            # Track call order
            call_log = []

            def mock_cleanup():
                call_log.append("cleanup")

            def mock_executor_init(*args, **kwargs):
                call_log.append("executor_created")
                return MagicMock()

            # Mock the db to avoid real DB calls
            mock_db = Mock()
            mock_db.create_riot_champions_table.return_value = True
            mock_db.update_champions_from_riot_api.return_value = None
            mock_db.init_matchups_table.return_value = None
            mock_db.build_champion_cache.return_value = {}
            mock_db.get_all_champion_names.return_value = {}  # Empty -> no scraping

            with (
                patch.object(pp, "_cleanup_existing_resources", side_effect=mock_cleanup),
                patch("src.parallel_parser.ThreadPoolExecutor", side_effect=mock_executor_init),
                patch("src.assistant.Assistant"),
            ):
                pp.parse_all_champions(mock_db, lambda x: x)

            # THEN: cleanup must have been called before executor creation
            assert "cleanup" in call_log
            assert "executor_created" in call_log
            assert call_log.index("cleanup") < call_log.index(
                "executor_created"
            ), "cleanup must be called BEFORE creating new executor"

    def test_parse_all_champions_calls_cleanup_exactly_once(self):
        """
        Regression: parse_all_champions() must call _cleanup_existing_resources() exactly once.
        """
        # GIVEN: A ParallelParser with _cleanup_existing_resources mocked
        with patch("src.parallel_parser.Parser") as mock_parser_class:
            mock_parser_class.return_value = Mock()

            from src.parallel_parser import ParallelParser

            pp = ParallelParser(max_workers=2)

            mock_db = Mock()
            mock_db.create_riot_champions_table.return_value = True
            mock_db.update_champions_from_riot_api.return_value = None
            mock_db.init_matchups_table.return_value = None
            mock_db.build_champion_cache.return_value = {}
            mock_db.get_all_champion_names.return_value = {}

            with (
                patch.object(pp, "_cleanup_existing_resources") as mock_cleanup,
                patch("src.parallel_parser.ThreadPoolExecutor") as mock_exec_class,
                patch("src.assistant.Assistant"),
            ):
                mock_exec_class.return_value = MagicMock()
                pp.parse_all_champions(mock_db, lambda x: x)

            mock_cleanup.assert_called_once()


class TestParseAllSynergiesCallsCleanup:
    """Tests verifying parse_all_synergies() calls _cleanup_existing_resources() first."""

    def test_parse_all_synergies_calls_cleanup_before_creating_executor(self):
        """
        Regression: parse_all_synergies() must call _cleanup_existing_resources() before
        creating a new ThreadPoolExecutor.

        Before fix: New executor stacked on top of existing one -> double Firefox instances.
        After fix: _cleanup_existing_resources() called first.
        """
        # GIVEN: A ParallelParser with _cleanup_existing_resources mocked
        with patch("src.parallel_parser.Parser") as mock_parser_class:
            mock_parser_class.return_value = Mock()

            from src.parallel_parser import ParallelParser

            pp = ParallelParser(max_workers=2)

            call_log = []

            def mock_cleanup():
                call_log.append("cleanup")

            def mock_executor_init(*args, **kwargs):
                call_log.append("executor_created")
                return MagicMock()

            mock_db = Mock()
            mock_db.init_synergies_table.return_value = None
            mock_db.build_champion_cache.return_value = {}
            mock_db.get_all_champion_names.return_value = {}  # Empty -> no scraping

            with (
                patch.object(pp, "_cleanup_existing_resources", side_effect=mock_cleanup),
                patch("src.parallel_parser.ThreadPoolExecutor", side_effect=mock_executor_init),
            ):
                pp.parse_all_synergies(mock_db, lambda x: x)

            # THEN: cleanup must have been called before executor creation
            assert "cleanup" in call_log
            assert "executor_created" in call_log
            assert call_log.index("cleanup") < call_log.index(
                "executor_created"
            ), "cleanup must be called BEFORE creating new executor"

    def test_parse_all_synergies_calls_cleanup_exactly_once(self):
        """
        Regression: parse_all_synergies() must call _cleanup_existing_resources() exactly once.
        """
        with patch("src.parallel_parser.Parser") as mock_parser_class:
            mock_parser_class.return_value = Mock()

            from src.parallel_parser import ParallelParser

            pp = ParallelParser(max_workers=2)

            mock_db = Mock()
            mock_db.init_synergies_table.return_value = None
            mock_db.build_champion_cache.return_value = {}
            mock_db.get_all_champion_names.return_value = {}

            with (
                patch.object(pp, "_cleanup_existing_resources") as mock_cleanup,
                patch("src.parallel_parser.ThreadPoolExecutor") as mock_exec_class,
            ):
                mock_exec_class.return_value = MagicMock()
                pp.parse_all_synergies(mock_db, lambda x: x)

            mock_cleanup.assert_called_once()


class TestNoDoubleFirefoxOnSequentialParsing:
    """Tests verifying that sequential parse calls don't accumulate parser instances."""

    def test_sequential_calls_do_not_accumulate_parsers(self):
        """
        Regression: After parse_all_champions() -> parse_all_synergies(), the total number
        of live parser instances must be at most max_workers (not 2x max_workers).

        Before fix: parsers from first call remained alongside parsers from second call.
        After fix: _cleanup_existing_resources() clears parsers before second call.

        Test strategy:
            - Track parsers created and parsers closed via mocks
            - Verify that after cleanup, the parsers list is reset before new ones are added
        """
        with patch("src.parallel_parser.Parser") as mock_parser_class:
            mock_parser_class.return_value = Mock()

            from src.parallel_parser import ParallelParser

            pp = ParallelParser(max_workers=3)

            # Simulate the state after a first parse run: 3 parsers accumulated
            initial_parsers = [Mock(), Mock(), Mock()]
            for p in initial_parsers:
                p.close.return_value = None
            pp.parsers = list(initial_parsers)

            # Set a fake executor to simulate "parse already ran once"
            fake_old_executor = Mock(spec=ThreadPoolExecutor)
            fake_old_executor.shutdown.return_value = None
            pp.executor = fake_old_executor

            # WHEN: _cleanup_existing_resources() is called (as parse_all_synergies does)
            pp._cleanup_existing_resources()

            # THEN: All old parsers were closed
            for p in initial_parsers:
                p.close.assert_called_once()

            # THEN: parsers list is now empty (reset for fresh start)
            assert len(pp.parsers) == 0, (
                f"Expected 0 parsers after cleanup, got {len(pp.parsers)}. "
                "This indicates the executor leak bug is still present."
            )

            # THEN: executor is None (no zombie executor)
            assert pp.executor is None

    def test_cleanup_existing_resources_method_exists_on_parallel_parser(self):
        """
        Regression: ParallelParser must have _cleanup_existing_resources() method.

        Before fix: Method did not exist -> resource leak on sequential calls.
        After fix: Method exists and is callable.
        """
        # GIVEN: Import ParallelParser class
        from src.parallel_parser import ParallelParser

        # THEN: Class must have the _cleanup_existing_resources method
        assert hasattr(
            ParallelParser, "_cleanup_existing_resources"
        ), "ParallelParser must have _cleanup_existing_resources() method"

        # THEN: Method must be callable
        assert callable(getattr(ParallelParser, "_cleanup_existing_resources"))

    def test_max_parsers_count_never_exceeds_max_workers_after_cleanup(self):
        """
        Regression: After cleanup between two parse runs, the parsers count stays bounded.

        Simulates the lifecycle:
        1. First parse run accumulates max_workers parsers
        2. cleanup() is called
        3. Parsers count drops to 0
        4. Second parse run would accumulate at most max_workers parsers again (not 2x)

        This test verifies step 2-3 of the lifecycle.
        """
        max_workers = 5

        with patch("src.parallel_parser.Parser") as mock_parser_class:
            mock_parser_class.return_value = Mock()

            from src.parallel_parser import ParallelParser

            pp = ParallelParser(max_workers=max_workers)

            # Simulate state after first parse: max_workers parsers accumulated
            pp.parsers = [Mock() for _ in range(max_workers)]
            for p in pp.parsers:
                p.close.return_value = None

            pp.executor = Mock(spec=ThreadPoolExecutor)
            pp.executor.shutdown.return_value = None

            # WHEN: cleanup is called (as at the start of a second parse run)
            pp._cleanup_existing_resources()

            # THEN: parsers count must be 0, not max_workers (no accumulation)
            assert len(pp.parsers) == 0, (
                f"Expected 0 parsers after cleanup but got {len(pp.parsers)}. "
                f"Without the fix, this would be {max_workers} (leaked parsers from first run)."
            )
