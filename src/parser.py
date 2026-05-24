"""Web scraper for LoLalytics champion matchup and synergy data.

Uses Playwright (Chromium) + playwright-stealth to bypass Cloudflare detection.
Replaces the previous Selenium/Firefox implementation (ADR-018).

Public API is identical to the old Selenium parser — drop-in replacement.
"""

import os
import random
import time
import logging
import lxml.html
from typing import List

from playwright.sync_api import (
    sync_playwright,
    Page,
    Browser,
    BrowserContext,
    TimeoutError as PlaywrightTimeoutError,
    Error as PlaywrightError,
)
from playwright_stealth import Stealth

from .cloudflare_detector import CloudflareException, detect_cloudflare
from .config import config
from .config_constants import scraping_config, xpath_config

logger = logging.getLogger(__name__)


class Parser:
    def __init__(self, headless: bool = False) -> None:
        """Initialize Parser with Playwright Chromium + stealth.

        Args:
            headless: If True, run Chromium in headless mode (no GUI).
                     Useful for Task Scheduler, background tasks, or CI/CD.
                     Default: False (normal GUI mode).
        """
        if headless:
            print("[PARSER] Headless mode enabled - Chromium will run without GUI (1920x1080)")

        self._playwright = sync_playwright().start()
        self._browser: Browser = self._playwright.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        # Load persistent storage state (cf_clearance cookie reuse) if configured
        storage_state = scraping_config.PLAYWRIGHT_STORAGE_STATE_PATH or None
        if storage_state and not os.path.exists(storage_state):
            # First run: file doesn't exist yet — ignore it
            storage_state = None

        self._context: BrowserContext = self._browser.new_context(
            storage_state=storage_state,
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
        )
        self._page: Page = self._context.new_page()
        Stealth().apply_stealth_sync(self._page)
        self.headless = headless

    def close(self) -> None:
        """Close browser and persist storage state (cf_clearance cookie)."""
        storage_path = scraping_config.PLAYWRIGHT_STORAGE_STATE_PATH
        if storage_path:
            try:
                self._context.storage_state(path=storage_path)
                logger.info("Storage state saved to %s", storage_path)
            except Exception as exc:
                logger.warning("Could not save storage state: %s", exc)
        try:
            self._context.close()
        except Exception:
            pass
        try:
            self._browser.close()
        except Exception:
            pass
        try:
            self._playwright.stop()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _navigate(self, url: str) -> None:
        """Navigate to URL and run Cloudflare detection."""
        self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        detect_cloudflare(self._page, url=url)

    def _human_mouse_move(self) -> None:
        """Simulate a human-like random mouse movement."""
        x = random.randint(200, 1700)
        y = random.randint(200, 800)
        self._page.mouse.move(x, y)

    def _accept_cookies(self) -> None:
        """Dismiss cookie banner using multiple strategies (Playwright version).

        Tries in order:
        1. Button by ID (didomi-notice-agree-button)
        2. CSS selectors (common GDPR patterns)
        3. XPath with text content
        """
        # Strategy 1: By ID
        try:
            btn = self._page.query_selector("#didomi-notice-agree-button")
            if btn:
                btn.click()
                logger.info("Cookie banner dismissed via ID selector")
                return
        except Exception as exc:
            logger.debug("Cookie ID strategy failed: %s", exc)

        # Strategy 2: CSS selectors
        selectors = [
            "button[aria-label*='agree' i]",
            "button[aria-label*='accept' i]",
            "button.didomi-button",
            ".didomi-notice-agree-button",
        ]
        for selector in selectors:
            try:
                btn = self._page.query_selector(selector)
                if btn:
                    btn.click()
                    logger.info("Cookie banner dismissed via CSS selector: %s", selector)
                    return
            except Exception as exc:
                logger.debug("Cookie CSS strategy (%s) failed: %s", selector, exc)

        # Strategy 3: XPath with text
        xpath_patterns = [
            "//button[contains(translate(text(), 'ACCEPT', 'accept'), 'accept')]",
            "//button[contains(translate(text(), 'AGREE', 'agree'), 'agree')]",
            "//button[contains(@class, 'agree')]",
        ]
        for xpath in xpath_patterns:
            try:
                btn = self._page.query_selector(f"xpath={xpath}")
                if btn:
                    btn.click()
                    logger.info("Cookie banner dismissed via XPath")
                    return
            except Exception as exc:
                logger.debug("Cookie XPath strategy failed: %s", exc)

        logger.info("No cookie banner found or all strategies exhausted")

    def _parse_carousel_row(self, path: str, result: list, is_synergy: bool = False) -> float:
        """Parse one carousel row and append unique entries to result.

        Args:
            path: XPath base path for the row container.
            result: Accumulator list (modified in-place).
            is_synergy: If True, parse synergy href format instead of matchup.

        Returns:
            Last pickrate seen (used to decide when to stop scrolling).
        """
        row_elements = self._page.query_selector_all(f"xpath={path}/*")
        if not row_elements:
            return float("inf")

        pickrate = float("inf")
        for idx, elem in enumerate(row_elements, start=1):
            try:
                # Champion / ally name
                anchor = elem.query_selector("a")
                if anchor is None:
                    continue
                href = anchor.get_attribute("href") or ""
                if is_synergy:
                    # Synergy href: /lol/{ally}/build/...
                    champ = href.split("/lol/")[1].split("/build")[0]
                else:
                    # Matchup href: /lol/{champ}/vs/{enemy}/build/...
                    champ = href.split("vs/")[1].split("/build")[0]

                # Winrate: first <span> inside div[1] of this row entry
                wr_elem = elem.query_selector(f"xpath={path}/div[{idx}]/div[1]/span")
                if wr_elem is None:
                    continue
                winrate = float(wr_elem.inner_html().split("%")[0])

                # Delta / pickrate from .my-1 children
                my1_elements = elem.query_selector_all(".my-1")
                if len(my1_elements) < 7:
                    logger.warning(
                        "Insufficient .my-1 elements for %s (found %d, expected ≥7). Skipping.",
                        champ,
                        len(my1_elements),
                    )
                    continue

                delta1 = float(my1_elements[4].inner_html())
                delta2 = float(my1_elements[5].inner_html())
                pickrate = float(my1_elements[6].inner_html())

                # Games count from .text-\[9px\] element
                games_elem = elem.query_selector(r".text-\[9px\]")
                if games_elem is None:
                    continue
                games = int("".join(games_elem.inner_html().split()).replace(",", ""))

                entry = (champ, winrate, delta1, delta2, pickrate, games)
                if not self._contains(result, *entry):
                    result.append(entry)

            except (IndexError, ValueError) as exc:
                logger.warning(
                    "Failed to parse carousel element: %s: %s. Skipping.",
                    type(exc).__name__,
                    exc,
                )
                continue

        return pickrate

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_matchup_data(self, champion: str, enemy: str) -> float:
        return self.get_matchup_data_on_patch(config.CURRENT_PATCH, champion, enemy)

    def get_matchup_data_on_patch(self, patch: str, champion: str, enemy: str) -> tuple:
        """Get head-to-head winrate and games for a specific matchup and patch."""
        url = (
            f"https://lolalytics.com/lol/{champion}/vs/{enemy}/build/"
            f"?tier=diamond_plus&patch={patch}"
        )
        try:
            self._navigate(url)
            tree = lxml.html.fromstring(self._page.content())

            winrate_elements = tree.xpath(xpath_config.WINRATE_XPATH)
            if not winrate_elements:
                print(f"Warning: Could not find winrate for {champion} vs {enemy}")
                return None, None
            winrate = float(winrate_elements[0])

            games_elements = tree.xpath(xpath_config.GAMES_XPATH)
            if not games_elements:
                print(f"Warning: Could not find games count for {champion} vs {enemy}")
                return winrate, 0
            games = int(games_elements[0].replace(",", ""))
            return winrate, games

        except CloudflareException:
            raise
        except (ValueError, IndexError) as exc:
            print(f"Error parsing data for {champion} vs {enemy}: {exc}")
            return None, None
        except Exception as exc:
            print(f"Unexpected error for {champion} vs {enemy}: {exc}")
            return None, None

    def get_champion_data(self, champion: str, lane: str = None) -> List[tuple]:
        return self.get_champion_data_on_patch(config.CURRENT_PATCH, champion, lane)

    def get_champion_data_on_patch(
        self, patch: str, champion: str, lane: str = None
    ) -> List[tuple]:
        """Scrape all matchup data for a champion on a given patch."""
        result: List[tuple] = []

        if lane:
            url = (
                f"https://lolalytics.com/lol/{champion}/build/"
                f"?lane={lane}&tier=diamond_plus&patch={patch}"
            )
        else:
            url = (
                f"https://lolalytics.com/lol/{champion}/build/" f"?tier=diamond_plus&patch={patch}"
            )

        self._navigate(url)
        time.sleep(
            random.uniform(scraping_config.PAGE_LOAD_DELAY_MIN, scraping_config.PAGE_LOAD_DELAY_MAX)
        )
        self._page.evaluate(f"window.scrollTo(0, {scraping_config.MATCHUP_SCROLL_Y})")
        time.sleep(
            random.uniform(scraping_config.SCROLL_DELAY_MIN, scraping_config.SCROLL_DELAY_MAX)
        )
        self._accept_cookies()
        self._human_mouse_move()

        for index in range(2, 7):
            path = f"/html/body/main/div[6]/div[1]/div[{index}]/div[2]/div"
            enough_data = False
            while not enough_data:
                pickrate = self._parse_carousel_row(path, result, is_synergy=False)
                # Scroll carousel horizontally
                self._page.evaluate(
                    f"""
                    (function() {{
                        var el = document.evaluate(
                            "{path}",
                            document,
                            null,
                            XPathResult.FIRST_ORDERED_NODE_TYPE,
                            null
                        ).singleNodeValue;
                        if (el) el.scrollLeft += {scraping_config.MATCHUP_CAROUSEL_SCROLL_X};
                    }})();
                    """
                )
                enough_data = pickrate < config.MIN_PICKRATE

        return result

    def get_champion_synergies(self, champion: str, lane: str = None) -> List[tuple]:
        """Parse champion synergies (WITH allies) from LoLalytics.

        Identical to get_champion_data but clicks the "Synergies" button first
        to switch from Counters to Synergies tab.

        Args:
            champion: Champion name (e.g., "yasuo")
            lane: Optional lane filter (e.g., "mid")

        Returns:
            List of tuples (ally_name, winrate, delta1, delta2, pickrate, games)
        """
        return self.get_champion_synergies_on_patch(config.CURRENT_PATCH, champion, lane)

    def get_champion_synergies_on_patch(
        self, patch: str, champion: str, lane: str = None
    ) -> List[tuple]:
        """Parse champion synergies for a specific patch.

        Args:
            patch: Patch version (e.g., "14.23")
            champion: Champion name
            lane: Optional lane filter

        Returns:
            List of tuples (ally_name, winrate, delta1, delta2, pickrate, games)
        """
        result: List[tuple] = []

        if lane:
            url = (
                f"https://lolalytics.com/lol/{champion}/build/"
                f"?lane={lane}&tier=diamond_plus&patch={patch}"
            )
        else:
            url = (
                f"https://lolalytics.com/lol/{champion}/build/" f"?tier=diamond_plus&patch={patch}"
            )

        self._navigate(url)
        time.sleep(
            random.uniform(scraping_config.PAGE_LOAD_DELAY_MIN, scraping_config.PAGE_LOAD_DELAY_MAX)
        )
        self._accept_cookies()

        # Click "Synergies" (Common Teammates) button to switch tabs
        try:
            btn = self._page.query_selector(f"xpath={xpath_config.SYNERGIES_BUTTON_XPATH}")
            if btn is None:
                logger.warning(
                    "Synergies button not found for %s. XPath: %s",
                    champion,
                    xpath_config.SYNERGIES_BUTTON_XPATH,
                )
                return []
            btn.click()
            logger.info("Clicked Synergies button for %s", champion)

            # Wait for first synergy row to appear
            first_row_xpath = "/html/body/main/div[6]/div[1]/div[2]/div[2]/div"
            self._page.wait_for_selector(f"xpath={first_row_xpath}", timeout=10000)
            logger.info("Synergies data loaded for %s", champion)
            time.sleep(
                random.uniform(
                    scraping_config.PAGE_LOAD_DELAY_MIN, scraping_config.PAGE_LOAD_DELAY_MAX
                )
            )

        except PlaywrightTimeoutError:
            logger.error(
                "Synergies data failed to load for %s after clicking button. "
                "Timeout waiting for first synergy row.",
                champion,
            )
            return []
        except PlaywrightError as exc:
            logger.error("Failed to click Synergies button for %s: %s", champion, exc)
            return []
        except Exception as exc:
            logger.error("Unexpected error clicking Synergies button for %s: %s", champion, exc)
            return []

        # Scroll to synergies section
        self._page.evaluate(f"window.scrollTo(0, {scraping_config.MATCHUP_SCROLL_Y})")
        time.sleep(
            random.uniform(scraping_config.SCROLL_DELAY_MIN, scraping_config.SCROLL_DELAY_MAX)
        )
        self._human_mouse_move()

        # Parse synergies (4 rows, not 5 like matchups)
        for index in range(2, 6):
            path = f"/html/body/main/div[6]/div[1]/div[{index}]/div[2]/div"
            enough_data = False
            pickrate = float("inf")
            while not enough_data:
                pickrate = self._parse_carousel_row(path, result, is_synergy=True)
                self._page.evaluate(
                    f"""
                    (function() {{
                        var el = document.evaluate(
                            "{path}",
                            document,
                            null,
                            XPathResult.FIRST_ORDERED_NODE_TYPE,
                            null
                        ).singleNodeValue;
                        if (el) el.scrollLeft += {scraping_config.MATCHUP_CAROUSEL_SCROLL_X};
                    }})();
                    """
                )
                enough_data = pickrate < config.MIN_PICKRATE

        return result

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _contains(
        self,
        lst: list,
        champ: str,
        winrate: float,
        d1: float,
        d2: float,
        pick: float,
        games: int,
    ) -> bool:
        """Return True if an identical entry already exists in lst."""
        for entry in lst:
            l_champ, l_winrate, l_delta1, l_delta2, l_pickrate, l_games = entry
            if (
                l_champ == champ
                and l_winrate == winrate
                and l_delta1 == d1
                and l_delta2 == d2
                and l_pickrate == pick
                and l_games == games
            ):
                return True
        return False

    # Legacy alias for backward-compatibility.
    def contains(self, lst, champ, winrate, d1, d2, pick, games) -> bool:
        return self._contains(lst, champ, winrate, d1, d2, pick, games)
