"""
Cloudflare protection page detector for LeagueStats scraper.

Detects Cloudflare challenge/block pages using multiple signals to avoid
false positives on legitimate pages that are simply slow to load.
"""

import logging

from selenium import webdriver
from selenium.webdriver.common.by import By

logger = logging.getLogger(__name__)

# Titles that indicate a Cloudflare challenge page (case-insensitive match)
_CF_TITLES = (
    "just a moment",
    "attention required",
    "please wait",
    "checking your browser",
)


class CloudflareException(Exception):
    """Raised when Cloudflare protection page is detected."""

    pass


def detect_cloudflare(driver: webdriver.Firefox, url: str = "") -> None:
    """
    Detects Cloudflare protection pages and raises CloudflareException.
    Uses multiple signals to avoid false positives.

    A CloudflareException is raised only when the page title matches a known
    Cloudflare pattern AND at least one additional structural signal is
    present (URL pattern, DOM element, or suspicious meta tag).

    Args:
        driver: Active Firefox WebDriver instance.
        url: URL that was loaded, used for logging purposes only.

    Raises:
        CloudflareException: When Cloudflare protection is confidently detected.
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
        logger.warning(
            "cloudflare_detector: Cloudflare protection detected " "(title=%r, signal=%s, url=%s)",
            title,
            secondary_signal,
            url or driver.current_url,
        )
        raise CloudflareException(
            f"Cloudflare protection page detected: title={title!r}, "
            f"signal={secondary_signal}, url={url}"
        )

    # Title matched but no secondary signal found — log a debug notice and
    # do NOT raise (avoids false positives on slow-loading pages).
    logger.debug(
        "cloudflare_detector: suspicious title %r but no secondary signal found "
        "(url=%s) — skipping raise to avoid false positive",
        title,
        url,
    )
