"""
Tests for cloudflare_detector module (Playwright version).

Validates detect_cloudflare(page) behaviour:
- Returns silently when the page title is not suspicious (fast path).
- Returns silently when suspicious title but no secondary signal (avoids false positives).
- Waits for Cloudflare challenge to auto-resolve when detected.
- Raises CloudflareException only when wait timeout expires.
- Never propagates exceptions from the Page itself.
"""

import logging

import pytest
from unittest.mock import MagicMock, patch

from src.cloudflare_detector import CloudflareException, detect_cloudflare


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def make_mock_page(
    title="LoLAlytics - Champion Stats",
    url="https://lolalytics.com/lol/aatrox/build/",
    dom_elements=None,
    title_raises=None,
):
    """
    Build a MagicMock Playwright Page with configurable behaviour.

    Args:
        title: Value returned by page.title().
        url: Value of page.url attribute.
        dom_elements: List returned by page.query_selector_all() (default: []).
        title_raises: If set, page.title() raises this exception.

    Returns:
        Configured MagicMock instance.
    """
    page = MagicMock()

    if title_raises is not None:
        page.title.side_effect = title_raises
    else:
        page.title.return_value = title

    page.url = url
    page.query_selector_all.return_value = dom_elements if dom_elements is not None else []

    return page


# ---------------------------------------------------------------------------
# Class 1 — Normal cases: no exception expected
# ---------------------------------------------------------------------------


class TestDetectCloudflareNormal:
    """Verify detect_cloudflare() does NOT raise for legitimate pages."""

    def test_normal_lolalytics_title_no_exception(self):
        """Legitimate LoLAlytics title must not trigger CloudflareException."""
        page = make_mock_page(title="LoLAlytics - Aatrox Build")
        detect_cloudflare(page, url="https://lolalytics.com/lol/aatrox/")

    def test_empty_title_no_exception(self):
        """Empty page title must not trigger CloudflareException."""
        page = make_mock_page(title="")
        detect_cloudflare(page, url="https://lolalytics.com/")

    def test_partial_match_title_no_exception(self):
        """Title overlapping with CF keywords (but not containing them) must not raise."""
        page = make_mock_page(title="The moment you've been waiting for")
        detect_cloudflare(page, url="https://lolalytics.com/")

    def test_suspicious_title_no_secondary_signal_no_exception(self):
        """Suspicious title without any secondary signal must NOT raise (avoids false positives)."""
        page = make_mock_page(
            title="Just a Moment...",
            url="https://lolalytics.com/lol/aatrox/",  # No /cdn-cgi/
            dom_elements=[],
        )
        detect_cloudflare(page, url="https://lolalytics.com/lol/aatrox/")

    def test_page_title_raises_silently_ignored(self):
        """When page.title() raises, detect_cloudflare must return silently."""
        page = make_mock_page(title_raises=RuntimeError("session dead"))
        detect_cloudflare(page, url="https://lolalytics.com/")


# ---------------------------------------------------------------------------
# Class 2 — Blocked cases: CloudflareException must be raised
# ---------------------------------------------------------------------------


class TestDetectCloudflareBlocked:
    """Verify detect_cloudflare() raises CloudflareException when challenge does not resolve.

    All tests use wait_timeout=0 so the poll loop times out instantly.
    """

    def test_just_a_moment_with_cdn_cgi_url_raises(self):
        """'Just a moment' title + /cdn-cgi/ in URL must raise CloudflareException."""
        page = make_mock_page(
            title="Just a moment...",
            url="https://lolalytics.com/cdn-cgi/challenge-platform/h/b/orchestrate/jsch/v1",
        )
        with pytest.raises(CloudflareException):
            detect_cloudflare(page, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)

    def test_attention_required_with_cf_wrapper_dom_raises(self):
        """'Attention Required!' + #cf-wrapper DOM element must raise CloudflareException."""
        page = make_mock_page(
            title="Attention Required!",
            url="https://lolalytics.com/lol/aatrox/",
        )

        def qsa_side_effect(selector):
            if selector == "#cf-wrapper":
                return [MagicMock()]
            return []

        page.query_selector_all.side_effect = qsa_side_effect

        with pytest.raises(CloudflareException):
            detect_cloudflare(page, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)

    def test_please_wait_with_challenge_form_raises(self):
        """'please wait' title + #challenge-form DOM element must raise CloudflareException."""
        page = make_mock_page(
            title="please wait",
            url="https://lolalytics.com/lol/aatrox/",
        )

        def qsa_side_effect(selector):
            if selector == "#challenge-form":
                return [MagicMock()]
            return []

        page.query_selector_all.side_effect = qsa_side_effect

        with pytest.raises(CloudflareException):
            detect_cloudflare(page, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)

    def test_checking_your_browser_with_meta_noindex_raises(self):
        """'Checking your browser' + meta robots=noindex must raise CloudflareException."""
        page = make_mock_page(
            title="Checking your browser",
            url="https://lolalytics.com/lol/aatrox/",
        )

        def qsa_side_effect(selector):
            if "robots" in selector:
                return [MagicMock()]
            return []

        page.query_selector_all.side_effect = qsa_side_effect

        with pytest.raises(CloudflareException):
            detect_cloudflare(page, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)

    def test_exception_message_contains_detected_title(self):
        """CloudflareException message must include the suspicious title that was detected."""
        page = make_mock_page(
            title="Just a moment...",
            url="https://lolalytics.com/cdn-cgi/challenge",
        )
        with pytest.raises(CloudflareException, match="just a moment"):
            detect_cloudflare(page, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)


# ---------------------------------------------------------------------------
# Class 3 — Page errors during secondary signal checks
# ---------------------------------------------------------------------------


class TestDetectCloudflarePageErrors:
    """Verify that Page errors inside secondary signal checks are silenced."""

    def test_url_error_does_not_block_dom_signals(self):
        """When page.url access errors, DOM signals must still be evaluated."""
        page = make_mock_page(title="just a moment")
        # Assign non-string url so `"/cdn-cgi/" in page.url` raises TypeError (caught)
        page.url = 42

        def qsa_side_effect(selector):
            if selector == "#cf-wrapper":
                return [MagicMock()]
            return []

        page.query_selector_all.side_effect = qsa_side_effect

        with pytest.raises(CloudflareException):
            detect_cloudflare(page, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)

    def test_query_selector_raises_for_css_does_not_block_meta_signal(self):
        """When query_selector_all raises for CSS selectors, meta XPath check must still run."""
        page = make_mock_page(
            title="attention required",
            url="https://lolalytics.com/lol/aatrox/",
        )

        def qsa_side_effect(selector):
            if "robots" in selector:
                return [MagicMock()]
            raise RuntimeError("DOM lookup failed")

        page.query_selector_all.side_effect = qsa_side_effect

        with pytest.raises(CloudflareException):
            detect_cloudflare(page, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)


# ---------------------------------------------------------------------------
# Parametric test — all known CF title variants (including multilingual)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cf_title",
    [
        # English
        "Just a moment...",
        "Attention Required! | Cloudflare",
        "Please Wait... | Cloudflare",
        "Checking your browser before accessing the site.",
        # French
        "Un instant...",
        "Vérification de votre navigateur",
        # Spanish
        "Un momento...",
        # German
        "Einen Moment bitte...",
    ],
)
def test_all_cf_title_variants_raise_with_cdn_cgi(cf_title):
    """All Cloudflare title variants must raise CloudflareException with /cdn-cgi/ URL."""
    page = make_mock_page(
        title=cf_title,
        url="https://lolalytics.com/cdn-cgi/challenge-platform/h/b",
    )
    with pytest.raises(CloudflareException):
        detect_cloudflare(page, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)


# ---------------------------------------------------------------------------
# Class 4 — Wait-for-challenge behaviour
# ---------------------------------------------------------------------------


class TestDetectCloudflareWaitForChallenge:
    """Verify the wait-for-resolve mechanism in detect_cloudflare()."""

    def test_challenge_resolves_returns_normally(self):
        """When the CF challenge auto-resolves, detect_cloudflare() must return without raising."""
        _calls = [0]

        def title_side_effect():
            _calls[0] += 1
            if _calls[0] <= 2:
                return "Just a moment..."
            return "LoLAlytics - Aatrox Build"

        page = make_mock_page(url="https://lolalytics.com/cdn-cgi/challenge")
        page.title.side_effect = title_side_effect

        with patch("src.cloudflare_detector.time.sleep"):
            with patch("src.cloudflare_detector.time.monotonic", side_effect=[0, 1, 2]):
                detect_cloudflare(page, url="https://lolalytics.com/lol/aatrox/", wait_timeout=5)

    def test_challenge_timeout_raises_cloudflare_exception(self):
        """When the CF challenge never resolves, CloudflareException must be raised."""
        page = make_mock_page(
            title="Just a moment...",
            url="https://lolalytics.com/cdn-cgi/challenge",
        )
        with pytest.raises(CloudflareException):
            detect_cloudflare(page, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)

    def test_wait_timeout_parameter_overrides_default(self):
        """The wait_timeout parameter must be used instead of scraping_config default."""
        page = make_mock_page(
            title="Just a moment...",
            url="https://lolalytics.com/cdn-cgi/challenge",
        )
        with pytest.raises(CloudflareException):
            detect_cloudflare(page, wait_timeout=0)

    def test_no_wait_when_no_secondary_signal(self):
        """Suspicious title with no secondary signal must return immediately without waiting."""
        page = make_mock_page(
            title="Just a moment...",
            url="https://lolalytics.com/lol/aatrox/",
            dom_elements=[],
        )
        detect_cloudflare(page, url="https://lolalytics.com/lol/aatrox/")

    def test_info_log_when_challenge_resolves(self, caplog):
        """When challenge resolves, an INFO log must be emitted."""
        caplog.set_level(logging.INFO, logger="src.cloudflare_detector")
        _calls = [0]

        def title_side_effect():
            _calls[0] += 1
            if _calls[0] <= 2:
                return "Just a moment..."
            return "LoLAlytics - Aatrox Build"

        page = make_mock_page(url="https://lolalytics.com/cdn-cgi/challenge")
        page.title.side_effect = title_side_effect

        with patch("src.cloudflare_detector.time.sleep"):
            with patch("src.cloudflare_detector.time.monotonic", side_effect=[0, 1, 2]):
                detect_cloudflare(page, url="https://lolalytics.com/lol/aatrox/", wait_timeout=5)

        assert "resolved" in caplog.text.lower()


# ---------------------------------------------------------------------------
# Class 5 — Logging
# ---------------------------------------------------------------------------


class TestDetectCloudflareLogging:
    """Verify that detect_cloudflare() emits correct log messages."""

    def test_no_log_on_clean_title(self, caplog):
        """Fast-path exit on clean title must produce no log output."""
        caplog.set_level(logging.DEBUG, logger="src.cloudflare_detector")
        page = make_mock_page(title="LoLAlytics - Champion Stats")
        detect_cloudflare(page)
        assert caplog.text == ""

    def test_debug_log_when_suspicious_title_no_secondary_signal(self, caplog):
        """Suspicious title with no secondary signal must log a debug-level message."""
        caplog.set_level(logging.DEBUG, logger="src.cloudflare_detector")
        page = make_mock_page(
            title="just a moment",
            url="https://lolalytics.com/lol/aatrox/",
            dom_elements=[],
        )
        detect_cloudflare(page)
        assert "suspicious title" in caplog.text.lower() or "false positive" in caplog.text.lower()

    def test_warning_log_on_detection(self, caplog):
        """Confirmed CF detection must emit a WARNING log."""
        caplog.set_level(logging.WARNING, logger="src.cloudflare_detector")
        page = make_mock_page(
            title="Just a moment...",
            url="https://lolalytics.com/cdn-cgi/challenge",
        )
        with pytest.raises(CloudflareException):
            detect_cloudflare(page, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)
        assert any(r.levelno >= logging.WARNING for r in caplog.records)
