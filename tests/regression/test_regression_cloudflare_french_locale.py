"""
Regression tests: Cloudflare detection must handle non-English challenge pages.

Bug: _CF_TITLES only contained English variants. When Cloudflare served a French
challenge page ('Un instant…'), the title was not detected as suspicious. The
poll loop then called page.title() and got a different title, causing detect_cloudflare()
to return silently — i.e., the Cloudflare block was NOT raised.

Fix: Added multilingual CF title variants to _CF_TITLES.

These tests ensure no regression: every locale variant must be detected.
"""

import pytest
from unittest.mock import MagicMock, patch

from src.cloudflare_detector import CloudflareException, detect_cloudflare


def _page_with_title_and_cdn_cgi(title: str) -> MagicMock:
    """Build a mock Page that returns the given title and a /cdn-cgi/ URL."""
    page = MagicMock()
    page.title.return_value = title
    page.url = "https://lolalytics.com/cdn-cgi/challenge"
    page.query_selector_all.return_value = []
    return page


# ---------------------------------------------------------------------------
# Regression: French locale
# ---------------------------------------------------------------------------


class TestFrenchLocaleDetected:
    """Cloudflare French challenge page must be detected (not silently passed)."""

    def test_un_instant_raises_cloudflare_exception(self):
        """'Un instant…' (French CF challenge) must raise CloudflareException."""
        page = _page_with_title_and_cdn_cgi("Un instant…")
        with pytest.raises(CloudflareException):
            detect_cloudflare(page, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)

    def test_verification_raises_cloudflare_exception(self):
        """'Vérification' (French CF challenge) must raise CloudflareException."""
        page = _page_with_title_and_cdn_cgi("Vérification du navigateur")
        with pytest.raises(CloudflareException):
            detect_cloudflare(page, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)

    def test_french_title_lowercase_raises(self):
        """Detection must be case-insensitive for French titles."""
        page = _page_with_title_and_cdn_cgi("UN INSTANT...")
        with pytest.raises(CloudflareException):
            detect_cloudflare(page, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)


# ---------------------------------------------------------------------------
# Regression: other locales
# ---------------------------------------------------------------------------


class TestOtherLocalesDetected:
    """Cloudflare non-English challenge pages (German, Spanish, Italian, Dutch) must be detected."""

    def test_spanish_un_momento_raises(self):
        """'Un momento' (Spanish) must raise CloudflareException."""
        page = _page_with_title_and_cdn_cgi("Un momento...")
        with pytest.raises(CloudflareException):
            detect_cloudflare(page, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)

    def test_german_einen_moment_raises(self):
        """'Einen Moment' (German) must raise CloudflareException."""
        page = _page_with_title_and_cdn_cgi("Einen Moment bitte...")
        with pytest.raises(CloudflareException):
            detect_cloudflare(page, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)

    def test_italian_attendere_raises(self):
        """'Attendere' (Italian) must raise CloudflareException."""
        page = _page_with_title_and_cdn_cgi("Attendere prego...")
        with pytest.raises(CloudflareException):
            detect_cloudflare(page, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)

    def test_portuguese_verificando_raises(self):
        """'Verificando' (Portuguese) must raise CloudflareException."""
        page = _page_with_title_and_cdn_cgi("Verificando seu navegador...")
        with pytest.raises(CloudflareException):
            detect_cloudflare(page, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)

    def test_dutch_even_geduld_raises(self):
        """'Even geduld' (Dutch) must raise CloudflareException."""
        page = _page_with_title_and_cdn_cgi("Even geduld...")
        with pytest.raises(CloudflareException):
            detect_cloudflare(page, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)


# ---------------------------------------------------------------------------
# Regression: locale switch in wait loop must not cause premature resolution
# ---------------------------------------------------------------------------


class TestLocaleChangeInWaitLoop:
    """When Cloudflare switches from one locale's CF page to another's, it must still be detected."""

    def test_english_to_french_locale_switch_not_prematurely_resolved(self):
        """
        Regression: English CF page → French CF page in wait loop must NOT resolve.

        Before fix: 'Un instant…' was not in _CF_TITLES so the poll loop saw
        a non-suspicious title and returned silently, falsely thinking CF resolved.
        After fix: Both English and French titles are in _CF_TITLES → CloudflareException raised.
        """
        _calls = [0]

        def title_side_effect():
            _calls[0] += 1
            if _calls[0] == 1:
                return "Just a moment..."  # English CF (initial detection)
            return "Un instant..."  # French CF (locale switch — still a block!)

        page = MagicMock()
        page.title.side_effect = title_side_effect
        page.url = "https://lolalytics.com/cdn-cgi/challenge"
        page.query_selector_all.return_value = []

        with pytest.raises(CloudflareException):
            with patch("src.cloudflare_detector.time.sleep"):
                # [0] = set deadline (deadline=5), [1] = first loop check (1<5 → True),
                # [6] = second loop check (6<5 → False → loop exits → raise)
                with patch("src.cloudflare_detector.time.monotonic", side_effect=[0, 1, 6]):
                    detect_cloudflare(
                        page,
                        url="https://lolalytics.com/lol/aatrox/",
                        wait_timeout=5,
                    )
