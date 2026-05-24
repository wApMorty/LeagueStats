"""
Regression tests for two bugs fixed in ParallelParser.

Bug 1: close() did not set self.executor = None after shutdown.
    Before fix: self.executor retained a reference to the closed (defunct) executor.
    After fix:  self.executor = None after executor.shutdown(wait=True) in close().

Bug 2: _scrape_champion_synergies_with_retry() had no @retry decorator.
    Before fix: Any WebDriverException or TimeoutException immediately propagated
                without retrying, causing premature failures during synergy scraping.
    After fix:  @retry decorator added (stop=stop_after_attempt(3),
                wait=wait_exponential(...), retry=retry_if_exception_type(...),
                reraise=True) — mirrors the behaviour of _scrape_champion_with_retry.

Test approach:
    All tests use mocks to avoid creating real Firefox/geckodriver processes.
    Parser.__init__ and Parser.close are patched throughout.
"""

import pytest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

from src.cloudflare_detector import CloudflareException


class TestCloseResetsExecutorToNone:
    """Regression tests for Bug 1: close() must set self.executor = None."""

    def test_close_sets_executor_to_none(self):
        """
        Regression Bug 1: close() must set self.executor = None after shutdown.

        Before fix: executor.shutdown(wait=True) was called but self.executor kept a
                    reference to the defunct executor object.
        After fix:  self.executor = None immediately after shutdown.
        """
        # GIVEN: A ParallelParser with a mock executor already set
        with patch("src.parallel_parser.Parser") as mock_parser_class:
            mock_parser_class.return_value = Mock()

            from src.parallel_parser import ParallelParser

            pp = ParallelParser(max_workers=2)

            mock_executor = Mock(spec=ThreadPoolExecutor)
            pp.executor = mock_executor

            # WHEN: close() is called
            pp.close()

            # THEN: self.executor must be None (not a stale reference)
            assert pp.executor is None, (
                "close() must set self.executor = None after shutdown. "
                "Before the fix, self.executor retained a reference to the closed executor."
            )

    def test_close_calls_shutdown_before_setting_none(self):
        """
        Regression Bug 1: close() must call executor.shutdown(wait=True) before
        setting self.executor = None.

        Verifies the correct shutdown sequence to ensure threads finish gracefully.
        """
        # GIVEN: A ParallelParser with a mock executor
        with patch("src.parallel_parser.Parser") as mock_parser_class:
            mock_parser_class.return_value = Mock()

            from src.parallel_parser import ParallelParser

            pp = ParallelParser(max_workers=2)

            mock_executor = Mock(spec=ThreadPoolExecutor)
            pp.executor = mock_executor

            # WHEN: close() is called
            pp.close()

            # THEN: shutdown(wait=True) must have been called on the executor
            mock_executor.shutdown.assert_called_once_with(wait=True)

    def test_close_executor_none_when_no_executor(self):
        """
        Regression Bug 1: close() must remain safe to call when executor is None.

        Scenario: close() called before any parse_* method ran (executor never set).
        After close(), self.executor must still be None and no exception raised.
        """
        # GIVEN: A freshly created ParallelParser (no executor)
        with patch("src.parallel_parser.Parser") as mock_parser_class:
            mock_parser_class.return_value = Mock()

            from src.parallel_parser import ParallelParser

            pp = ParallelParser(max_workers=2)

            assert pp.executor is None

            # WHEN: close() is called with no executor present
            # THEN: No exception raised
            pp.close()

            # THEN: executor remains None
            assert pp.executor is None


class TestScrapeChampionSynergiesWithRetryHasRetryDecorator:
    """Regression tests for Bug 2: _scrape_champion_synergies_with_retry must have @retry."""

    def test_scrape_champion_synergies_with_retry_has_retry_attribute(self):
        """
        Regression Bug 2: _scrape_champion_synergies_with_retry must have a tenacity
        @retry decorator, which adds a 'retry' attribute to the wrapped function.

        Before fix: No @retry decorator -> first WebDriverException propagated immediately.
        After fix:  @retry added -> tenacity wraps the function and adds 'retry' attribute.
        """
        from src.parallel_parser import ParallelParser

        method = ParallelParser._scrape_champion_synergies_with_retry

        assert hasattr(method, "retry"), (
            "_scrape_champion_synergies_with_retry must have a 'retry' attribute added by "
            "tenacity's @retry decorator. Before the fix, the decorator was missing and any "
            "WebDriverException would propagate immediately without retrying."
        )

    def test_scrape_champion_synergies_with_retry_decorator_is_callable(self):
        """
        Regression Bug 2: The 'retry' attribute added by tenacity must be callable,
        confirming the decorator was applied correctly (not just a coincidental attribute).
        """
        from src.parallel_parser import ParallelParser

        method = ParallelParser._scrape_champion_synergies_with_retry

        retry_attr = getattr(method, "retry", None)
        assert callable(retry_attr), (
            "The 'retry' attribute on _scrape_champion_synergies_with_retry must be callable. "
            "A non-callable attribute would indicate the tenacity decorator was not properly "
            "applied."
        )

    def test_scrape_champion_with_retry_also_has_retry_decorator(self):
        """
        Sanity check: _scrape_champion_with_retry (matchup method) already had @retry.
        Confirms the tenacity pattern we check for is consistent across both methods.
        """
        from src.parallel_parser import ParallelParser

        method = ParallelParser._scrape_champion_with_retry

        assert hasattr(method, "retry"), (
            "_scrape_champion_with_retry must still have its @retry decorator. "
            "This is a sanity check to confirm both methods now behave symmetrically."
        )

    def test_synergies_retry_decorator_mirrors_matchup_retry_decorator(self):
        """
        Regression Bug 2: The @retry configuration on _scrape_champion_synergies_with_retry
        must mirror the one on _scrape_champion_with_retry (same retry attribute type).

        Both methods must expose the same tenacity 'retry' interface for consistency.
        """
        from src.parallel_parser import ParallelParser

        synergies_method = ParallelParser._scrape_champion_synergies_with_retry
        matchup_method = ParallelParser._scrape_champion_with_retry

        # Both must have the 'retry' attribute
        assert hasattr(
            synergies_method, "retry"
        ), "_scrape_champion_synergies_with_retry is missing the 'retry' attribute."
        assert hasattr(
            matchup_method, "retry"
        ), "_scrape_champion_with_retry is missing the 'retry' attribute (regression in fix)."

        # Both retry attributes must be the same type
        assert type(synergies_method.retry) is type(matchup_method.retry), (
            "The 'retry' attribute type on _scrape_champion_synergies_with_retry "
            f"({type(synergies_method.retry)}) does not match the type on "
            f"_scrape_champion_with_retry ({type(matchup_method.retry)}). "
            "Both methods should use an identical tenacity retry configuration."
        )


class TestSynergiesRetryOnCloudflareException:
    """Regression test: _scrape_champion_synergies_with_retry must retry on CloudflareException."""

    def test_synergies_retry_on_cloudflare_exception(self):
        """
        Regression: _scrape_champion_synergies_with_retry must retry on CloudflareException.

        Before fix: CloudflareException was not listed in retry_if_exception_type, so the first
                    Cloudflare block immediately propagated without any retry attempt.
        After fix:  CloudflareException is included in the @retry decorator's
                    retry_if_exception_type tuple, so tenacity retries up to 3 times.

        Test approach (behavioural, no tenacity introspection):
            - Mock _get_parser() to return a parser whose get_champion_synergies_on_patch()
              always raises CloudflareException.
            - Call _scrape_champion_synergies_with_retry() and catch the final re-raised exception.
            - Assert the underlying scrape method was called more than once, proving retries happened.
        """
        with patch("src.parallel_parser.Parser") as mock_parser_class:
            mock_parser_class.return_value = Mock()

            from src.parallel_parser import ParallelParser

            pp = ParallelParser(max_workers=1)

            # Build a mock parser whose synergy-scrape method always raises CloudflareException
            mock_inner_parser = Mock()
            mock_inner_parser.get_champion_synergies_on_patch.side_effect = CloudflareException(
                "Cloudflare block detected"
            )

            # Patch _get_parser so no real Firefox is created
            with patch.object(pp, "_get_parser", return_value=mock_inner_parser):
                with pytest.raises(CloudflareException):
                    pp._scrape_champion_synergies_with_retry("Aatrox", lambda x: x)

            # THEN: the scrape was attempted more than once (tenacity retried)
            call_count = mock_inner_parser.get_champion_synergies_on_patch.call_count
            assert call_count >= 2, (
                f"Expected at least 2 scrape attempts (retry), but got {call_count}. "
                "Before the fix, CloudflareException was not in retry_if_exception_type, "
                "so it propagated immediately on the first attempt without any retry."
            )
