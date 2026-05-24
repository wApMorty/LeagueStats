"""
Regression test: Cloudflare French-locale title "Un instant…" was not detected.

Bug: headless Firefox receives the French Cloudflare challenge page (title="Un
instant…") because its Accept-Language header triggers locale switching.
detect_cloudflare() saw the title change from "just a moment..." to "Un
instant…" and logged "challenge resolved automatically" — treating an active
Cloudflare challenge as a clean page.  The scraper then found no matchup DOM
elements and returned empty data for every champion.

Fix: added French (and other locale) title variants to _CF_TITLES so the
WebDriverWait loop keeps waiting until a genuinely non-CF title appears.
"""

import pytest
from unittest.mock import MagicMock, PropertyMock

from src.cloudflare_detector import CloudflareException, detect_cloudflare


def _make_driver_with_cdn_cgi(title: str) -> MagicMock:
    driver = MagicMock()
    type(driver).title = PropertyMock(return_value=title)
    type(driver).current_url = PropertyMock(
        return_value="https://lolalytics.com/cdn-cgi/challenge"
    )
    driver.find_elements.return_value = []
    return driver


class TestCloudflareFrenchLocaleRegression:
    """
    Verify that Cloudflare challenge pages in non-English locales are treated
    as active challenges, not as resolved pages.
    """

    def test_french_un_instant_raises_cloudflare_exception(self):
        """'Un instant…' (French 'Just a moment') must raise CloudflareException."""
        driver = _make_driver_with_cdn_cgi("Un instant…")
        with pytest.raises(CloudflareException):
            detect_cloudflare(driver, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)

    def test_french_un_instant_lowercase_raises(self):
        """Lowercase 'un instant' must also be detected (case-insensitive check)."""
        driver = _make_driver_with_cdn_cgi("un instant...")
        with pytest.raises(CloudflareException):
            detect_cloudflare(driver, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)

    def test_french_verification_raises(self):
        """French 'Vérification' variant must raise CloudflareException."""
        driver = _make_driver_with_cdn_cgi("Vérification de votre navigateur")
        with pytest.raises(CloudflareException):
            detect_cloudflare(driver, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)

    def test_spanish_un_momento_raises(self):
        """Spanish 'Un momento' variant must raise CloudflareException."""
        driver = _make_driver_with_cdn_cgi("Un momento...")
        with pytest.raises(CloudflareException):
            detect_cloudflare(driver, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)

    def test_german_einen_moment_raises(self):
        """German 'Einen Moment' variant must raise CloudflareException."""
        driver = _make_driver_with_cdn_cgi("Einen Moment...")
        with pytest.raises(CloudflareException):
            detect_cloudflare(driver, url="https://lolalytics.com/lol/aatrox/", wait_timeout=0)

    def test_challenge_not_prematurely_resolved_on_locale_switch(self):
        """
        When title switches from English CF to French CF, challenge must NOT be
        considered resolved — wait must continue until a real page title appears.

        This is the exact scenario that triggered the bug: WebDriverWait saw
        'Un instant…' as non-CF and returned, leaving the page still on CF.
        """
        # Sequence: English CF → French CF → real page (resolution)
        _titles = ["Just a moment...", "Un instant…", "Un instant…", "LoLAlytics - Aatrox"]
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

        # Should not raise — eventually resolves to a real title
        detect_cloudflare(driver, url="https://lolalytics.com/lol/aatrox/", wait_timeout=5)
