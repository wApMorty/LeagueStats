"""
Tests for cloudflare_detector module.

Validates detect_cloudflare() behaviour:
- Returns silently when the page title is not suspicious (fast path).
- Returns silently when the title is suspicious but no secondary signal is found
  (avoids false positives on slow-loading pages).
- Waits for the Cloudflare JS challenge to auto-resolve when detected.
- Raises CloudflareException only when the wait timeout expires.
- Never propagates exceptions from the WebDriver itself.
"""

import logging

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException as SeleniumTimeoutException

from src.cloudflare_detector import CloudflareException, detect_cloudflare


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def make_mock_driver(
    title="LoLAlytics - Champion Stats",
    current_url="https://lolalytics.com/lol/aatrox/build/",
    dom_elements=None,
    title_raises=None,
    url_raises=None,
    find_elements_raises=None,
):
    """
    Build a MagicMock WebDriver with configurable behaviour.

    Args:
        title: Value returned by driver.title.
        current_url: Value returned by driver.current_url.
        dom_elements: List returned by driver.find_elements() (default: empty).
        title_raises: If set, driver.title access raises this exception.
        url_raises: If set, driver.current_url access raises this exception.
        find_elements_raises: If set, driver.find_elements() raises this exception.

    Returns:
        Configured MagicMock instance.
    """
    driver = MagicMock()

    if title_raises is not None:
        type(driver).title = property(lambda self: (_ for _ in ()).throw(title_raises))
    else:
        type(driver).title = property(lambda self: title)

    if url_raises is not None:
        type(driver).current_url = property(lambda self: (_ for _ in ()).throw(url_raises))
    else:
        type(driver).current_url = property(lambda self: current_url)

    if find_elements_raises is not None:
        driver.find_elements.side_effect = find_elements_raises
    else:
        driver.find_elements.return_value = dom_elements if dom_elements is not None else []

    return driver


# ---------------------------------------------------------------------------
# Class 1 — Normal cases: no exception expected
# ---------------------------------------------------------------------------


class TestDetectCloudflareNormal:
    """Verify detect_cloudflare() does NOT raise for legitimate pages."""

    def test_normal_lolalytics_title_no_exception(self):
        """Legitimate LoLAlytics title must not trigger CloudflareException."""
        driver = make_mock_driver(title="LoLAlytics - Aatrox Build")
        # Must complete without raising
        detect_cloudflare(driver, url="https://lolalytics.com/lol/aatrox/")

    def test_empty_title_no_exception(self):
        """Empty page title must not trigger CloudflareException."""
        driver = make_mock_driver(title="")
        detect_cloudflare(driver, url="https://lolalytics.com/")

    def test_partial_match_title_no_exception(self):
        """Title that partially overlaps with CF keywords but does not contain them must not raise."""
        # "moment" alone is not in _CF_TITLES; the full phrase "just a moment" is required.
        driver = make_mock_driver(title="The moment you've been waiting for")
        detect_cloudflare(driver, url="https://lolalytics.com/")

    def test_suspicious_title_no_secondary_signal_no_exception(self):
        """Suspicious title without any secondary signal must NOT raise (avoids false positives)."""
        driver = make_mock_driver(
            title="Just a Moment...",  # Matches _CF_TITLES
            current_url="https://lolalytics.com/lol/aatrox/",  # No /cdn-cgi/
            dom_elements=[],  # No CF DOM elements
        )
        # find_elements returns [] for every selector -> no secondary signal
        detect_cloudflare(driver, url="https://lolalytics.com/lol/aatrox/")

    def test_driver_title_raises_exception_silently_ignored(self):
        """When driver.title itself raises, detect_cloudflare must return silently."""
        driver = make_mock_driver(title_raises=RuntimeError("session dead"))
        # Must NOT propagate RuntimeError
        detect_cloudflare(driver, url="https://lolalytics.com/")


# ---------------------------------------------------------------------------
# Class 2 — Blocked cases: CloudflareException must be raised
# ---------------------------------------------------------------------------


class TestDetectCloudflareBlocked:
    """Verify detect_cloudflare() raises CloudflareException when challenge does not resolve.

    All tests use wait_timeout=0 so WebDriverWait times out instantly — no 30s waits in CI.
    """

    def test_just_a_moment_with_cdn_cgi_url_raises(self):
        """'Just a moment' title + /cdn-cgi/ in URL must raise CloudflareException."""
        driver = make_mock_driver(
            title="Just a moment...",
            current_url="https://lolalytics.com/cdn-cgi/challenge-platform/h/b/orchestrate/jsch/v1",
        )
        with pytest.raises(CloudflareException):
            detect_cloudflare(driver, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)

    def test_attention_required_with_cf_wrapper_dom_raises(self):
        """'Attention Required!' + #cf-wrapper DOM element must raise CloudflareException."""
        cf_element = MagicMock()
        driver = make_mock_driver(
            title="Attention Required!",
            current_url="https://lolalytics.com/lol/aatrox/",
        )

        def find_elements_side_effect(by, selector):
            if by == By.ID and selector == "cf-wrapper":
                return [cf_element]
            return []

        driver.find_elements.side_effect = find_elements_side_effect

        with pytest.raises(CloudflareException):
            detect_cloudflare(driver, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)

    def test_please_wait_with_challenge_form_raises(self):
        """'please wait' title + #challenge-form DOM element must raise CloudflareException."""
        cf_element = MagicMock()
        driver = make_mock_driver(
            title="please wait",
            current_url="https://lolalytics.com/lol/aatrox/",
        )

        def find_elements_side_effect(by, selector):
            if by == By.ID and selector == "challenge-form":
                return [cf_element]
            return []

        driver.find_elements.side_effect = find_elements_side_effect

        with pytest.raises(CloudflareException):
            detect_cloudflare(driver, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)

    def test_checking_your_browser_with_meta_noindex_raises(self):
        """'Checking your browser' + meta robots=noindex must raise CloudflareException."""
        meta_element = MagicMock()
        driver = make_mock_driver(
            title="Checking your browser",
            current_url="https://lolalytics.com/lol/aatrox/",
        )

        def find_elements_side_effect(by, selector):
            if by == By.XPATH:
                return [meta_element]
            return []

        driver.find_elements.side_effect = find_elements_side_effect

        with pytest.raises(CloudflareException):
            detect_cloudflare(driver, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)

    def test_exception_message_contains_detected_title(self):
        """CloudflareException message must include the suspicious title that was detected."""
        driver = make_mock_driver(
            title="Just a moment...",
            current_url="https://lolalytics.com/cdn-cgi/challenge",
        )
        with pytest.raises(CloudflareException, match="just a moment"):
            detect_cloudflare(driver, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)


# ---------------------------------------------------------------------------
# Class 3 — Driver errors during secondary signal checks
# ---------------------------------------------------------------------------


class TestDetectCloudflareDriverErrors:
    """Verify that WebDriver errors inside secondary signal checks are silenced."""

    def test_current_url_raises_does_not_block_dom_signals(self):
        """When driver.current_url raises, DOM signals must still be evaluated."""
        cf_element = MagicMock()
        driver = make_mock_driver(
            title="just a moment",
            url_raises=RuntimeError("url unavailable"),
        )

        def find_elements_side_effect(by, selector):
            if by == By.ID and selector == "cf-wrapper":
                return [cf_element]
            return []

        driver.find_elements.side_effect = find_elements_side_effect

        with pytest.raises(CloudflareException):
            detect_cloudflare(driver, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)

    def test_find_elements_raises_does_not_block_meta_signal(self):
        """When find_elements() raises for DOM selectors, meta XPATH check must still run."""
        meta_element = MagicMock()
        driver = make_mock_driver(
            title="attention required",
            current_url="https://lolalytics.com/lol/aatrox/",
        )

        def find_elements_side_effect(by, selector):
            if by == By.XPATH:
                return [meta_element]
            raise RuntimeError("DOM lookup failed")

        driver.find_elements.side_effect = find_elements_side_effect

        with pytest.raises(CloudflareException):
            detect_cloudflare(driver, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)


# ---------------------------------------------------------------------------
# Parametric test — all four known CF title variants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cf_title",
    [
        "Just a moment...",
        "Attention Required! | Cloudflare",
        "Please Wait... | Cloudflare",
        "Checking your browser before accessing the site.",
    ],
)
def test_all_cf_title_variants_raise_with_cdn_cgi(cf_title):
    """
    All four Cloudflare title variants must raise CloudflareException when
    paired with a /cdn-cgi/ URL and the challenge does not resolve.
    """
    driver = make_mock_driver(
        title=cf_title,
        current_url="https://lolalytics.com/cdn-cgi/challenge-platform/h/b",
    )
    with pytest.raises(CloudflareException):
        detect_cloudflare(driver, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)


# ---------------------------------------------------------------------------
# Logging tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Class 4 — Wait-for-challenge behaviour
# ---------------------------------------------------------------------------


class TestDetectCloudflareWaitForChallenge:
    """Verify the wait-for-redirect mechanism added to detect_cloudflare()."""

    def test_challenge_resolves_returns_normally(self):
        """When the CF challenge auto-resolves, detect_cloudflare() must return without raising."""
        # Simulate: first few calls return CF title, then real title after challenge resolves.
        # Use a clamped function to avoid StopIteration inside generator expressions (PEP 479).
        _titles = ["Just a moment...", "Just a moment...", "LoLAlytics - Aatrox Build"]
        _idx = [0]

        def title_side_effect():
            val = _titles[min(_idx[0], len(_titles) - 1)]
            _idx[0] += 1
            return val

        driver = MagicMock()
        type(driver).title = PropertyMock(side_effect=title_side_effect)
        type(driver).current_url = PropertyMock(
            return_value="https://lolalytics.com/cdn-cgi/challenge"
        )
        driver.find_elements.return_value = []

        # Should not raise — challenge resolves after a few polls
        detect_cloudflare(driver, url="https://lolalytics.com/lol/aatrox/", wait_timeout=5)

    def test_challenge_timeout_raises_cloudflare_exception(self):
        """When the CF challenge never resolves, CloudflareException must be raised."""
        driver = make_mock_driver(
            title="Just a moment...",
            current_url="https://lolalytics.com/cdn-cgi/challenge",
        )
        with pytest.raises(CloudflareException):
            detect_cloudflare(driver, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)

    def test_wait_timeout_parameter_overrides_default(self):
        """The wait_timeout parameter must be used instead of scraping_config default."""
        driver = make_mock_driver(
            title="Just a moment...",
            current_url="https://lolalytics.com/cdn-cgi/challenge",
        )
        # wait_timeout=0 forces immediate timeout — test would hang 30s without this parameter
        with pytest.raises(CloudflareException):
            detect_cloudflare(driver, wait_timeout=0)

    def test_no_wait_when_no_secondary_signal(self):
        """When only a suspicious title is present (no secondary signal), must return without waiting."""
        driver = make_mock_driver(
            title="Just a moment...",
            current_url="https://lolalytics.com/lol/aatrox/",
            dom_elements=[],
        )
        # Must return immediately — no secondary signal means no CloudflareException, no wait
        detect_cloudflare(driver, url="https://lolalytics.com/lol/aatrox/")

    def test_info_log_when_challenge_resolves(self, caplog):
        """When challenge resolves, an INFO log must be emitted."""
        caplog.set_level(logging.INFO, logger="src.cloudflare_detector")
        _titles = ["Just a moment...", "Just a moment...", "LoLAlytics - Aatrox Build"]
        _idx = [0]

        def title_side_effect():
            val = _titles[min(_idx[0], len(_titles) - 1)]
            _idx[0] += 1
            return val

        driver = MagicMock()
        type(driver).title = PropertyMock(side_effect=title_side_effect)
        type(driver).current_url = PropertyMock(
            return_value="https://lolalytics.com/cdn-cgi/challenge"
        )
        driver.find_elements.return_value = []

        detect_cloudflare(driver, url="https://lolalytics.com/lol/aatrox/", wait_timeout=5)
        assert "resolved" in caplog.text.lower()


class TestDetectCloudflareLogging:
    """Verify that detect_cloudflare() emits correct log messages."""

    def test_no_log_on_clean_title(self, caplog):
        """Fast-path exit on clean title must produce no log output."""
        caplog.set_level(logging.DEBUG, logger="src.cloudflare_detector")
        driver = make_mock_driver(title="LoLAlytics - Champion Stats")
        detect_cloudflare(driver)
        assert caplog.text == ""

    def test_debug_log_when_suspicious_title_no_secondary_signal(self, caplog):
        """Suspicious title with no secondary signal must log a debug-level message."""
        caplog.set_level(logging.DEBUG, logger="src.cloudflare_detector")
        driver = make_mock_driver(
            title="just a moment",
            current_url="https://lolalytics.com/lol/aatrox/",
            dom_elements=[],
        )
        detect_cloudflare(driver)
        assert "suspicious title" in caplog.text.lower() or "false positive" in caplog.text.lower()

    def test_warning_log_on_detection(self, caplog):
        """Confirmed CF detection must emit a WARNING log."""
        caplog.set_level(logging.WARNING, logger="src.cloudflare_detector")
        driver = make_mock_driver(
            title="Just a moment...",
            current_url="https://lolalytics.com/cdn-cgi/challenge",
        )
        with pytest.raises(CloudflareException):
            detect_cloudflare(driver, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)
        assert any(r.levelno >= logging.WARNING for r in caplog.records)
