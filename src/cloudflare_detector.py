"""
Cloudflare protection page detector for LeagueStats scraper.

Detects Cloudflare challenge/block pages using multiple signals to avoid
false positives on legitimate pages that are simply slow to load.

When a challenge is detected, waits up to CLOUDFLARE_WAIT_SECONDS for the
JS challenge to auto-resolve and redirect to the real page before raising.
"""

import logging

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

from .config_constants import scraping_config

logger = logging.getLogger(__name__)

# Titles that indicate a Cloudflare challenge page (case-insensitive match).
# Includes common localisations: Cloudflare switches the UI language based on
# browser Accept-Language, so headless Firefox may receive a French page even
# when the target site is in English.
_CF_TITLES = (
    # English
    "just a moment",
    "attention required",
    "please wait",
    "checking your browser",
    # French
    "un instant",
    "vérification",
    # Spanish / Portuguese
    "un momento",
    "verificando",
    # German
    "einen moment",
    # Italian
    "attendere",
    # Dutch
    "even geduld",
)


class CloudflareException(Exception):
    """Raised when Cloudflare protection page is detected."""

    pass


def detect_cloudflare(
    driver: webdriver.Firefox, url: str = "", wait_timeout: int | None = None
) -> None:
    """
    Detects Cloudflare protection pages and waits for the challenge to resolve.

    Uses multiple signals to avoid false positives. When a challenge is
    confidently detected (suspicious title + secondary signal), waits up to
    ``wait_timeout`` seconds for the JS challenge to auto-resolve. Only raises
    CloudflareException if the challenge does not resolve within that window.

    Args:
        driver: Active Firefox WebDriver instance.
        url: URL that was loaded, used for logging purposes only.
        wait_timeout: Seconds to wait for challenge resolution. Defaults to
            scraping_config.CLOUDFLARE_WAIT_SECONDS (30s).

    Raises:
        CloudflareException: When Cloudflare challenge did not resolve within
            the wait timeout.
    """
    # --- Signal 1: page title ---
    try:
        title = driver.title.lower().strip()
    except Exception as exc:  # noqa: BLE001
        logger.debug("cloudflare_detector: could not read page title: %s", exc)
        return

    title_is_suspicious = any(cf_title in title for cf_title in _CF_TITLES)

    if not title_is_suspicious:
        # Title alone clears us; no need to inspect further signals.
        return

    # Title is suspicious — look for at least one corroborating signal.
    secondary_signal: str | None = None

    # --- Signal 2: URL contains /cdn-cgi/ (Cloudflare Turnstile redirect) ---
    try:
        current_url = driver.current_url
        if "/cdn-cgi/" in current_url:
            secondary_signal = f"URL contains /cdn-cgi/ ({current_url})"
    except Exception as exc:  # noqa: BLE001
        logger.debug("cloudflare_detector: could not read current URL: %s", exc)

    # --- Signal 3: Cloudflare DOM elements ---
    if secondary_signal is None:
        cf_selectors = [
            (By.ID, "cf-wrapper"),
            (By.CSS_SELECTOR, "div.cf-browser-verification"),
            (By.ID, "challenge-form"),
        ]
        for by, selector in cf_selectors:
            try:
                elements = driver.find_elements(by, selector)
                if elements:
                    secondary_signal = f"DOM element found: {selector}"
                    break
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "cloudflare_detector: error checking selector %s: %s",
                    selector,
                    exc,
                )

    # --- Signal 4: <meta name="robots" content="noindex"> ---
    if secondary_signal is None:
        try:
            meta_elements = driver.find_elements(
                By.XPATH,
                "//meta[@name='robots' and contains(@content,'noindex')]",
            )
            if meta_elements:
                secondary_signal = "meta robots=noindex present with suspicious title"
        except Exception as exc:  # noqa: BLE001
            logger.debug("cloudflare_detector: error checking meta robots tag: %s", exc)

    if secondary_signal is not None:
        timeout = (
            wait_timeout if wait_timeout is not None else scraping_config.CLOUDFLARE_WAIT_SECONDS
        )
        logger.warning(
            "cloudflare_detector: Cloudflare challenge detected, waiting up to %ds for auto-resolve "
            "(title=%r, signal=%s, url=%s)",
            timeout,
            title,
            secondary_signal,
            url or driver.current_url,
        )
        # Print to stdout so the user sees it in the console even if log level filters warnings
        print(
            f"\n[CLOUDFLARE] Challenge detected for {url or 'page'}\n"
            f"  → If a Firefox window is open, click 'Verify you are human'.\n"
            f"  → Waiting up to {timeout}s for the challenge to resolve...\n",
            flush=True,
        )
        try:
            WebDriverWait(driver, timeout).until(
                lambda d: not any(cf_title in d.title.lower().strip() for cf_title in _CF_TITLES)
            )
            logger.info(
                "cloudflare_detector: challenge resolved automatically (new title=%r, url=%s)",
                driver.title,
                url,
            )
            return
        except TimeoutException:
            raise CloudflareException(
                f"Cloudflare challenge did not resolve in {timeout}s: "
                f"title={title!r}, signal={secondary_signal}, url={url}"
            )

    # Title matched but no secondary signal found — log a debug notice and
    # do NOT raise (avoids false positives on slow-loading pages).
    logger.debug(
        "cloudflare_detector: suspicious title %r but no secondary signal found "
        "(url=%s) — skipping raise to avoid false positive",
        title,
        url,
    )
