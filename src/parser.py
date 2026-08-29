from time import sleep
from typing import Callable, List, Optional, Tuple
import lxml.html
import logging

from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    ElementNotInteractableException,
    InvalidSessionIdException,
    StaleElementReferenceException,
    WebDriverException,
    TimeoutException,
)

from .config import config
from .config_constants import analysis_config, scraping_config, xpath_config

logger = logging.getLogger(__name__)

# Error codes are written inline as an "[ERR_<CATEGORY>_<NNN>]" message prefix so
# they stay greppable in the logs. Cookie banner codes, by severity:
#   ERROR    ERR_COOKIE_001/002/003 (ID/CSS/XPath strategy blew up),
#            ERR_COOKIE_006 (coordinate click failed, GUI mode)
#   WARNING  ERR_COOKIE_004 (button found but not interactable)
#   CRITICAL ERR_COOKIE_005 (page never loaded), ERR_COOKIE_007 (WebDriver session lost)


class Parser:
    def __init__(self, headless: bool = False) -> None:
        """Initialize Parser with optional headless mode.

        Args:
            headless: If True, run Firefox in headless mode (no GUI).
                     Useful for Task Scheduler, background tasks, or CI/CD.
                     Default: False (normal GUI mode with fullscreen).
        """
        options = Options()
        options.binary_location = config.get_firefox_path()

        if headless:
            # Headless mode for background execution (Task Scheduler, pythonw.exe)
            options.add_argument("--headless")
            # Force 1920x1080 resolution to match GUI fullscreen behavior.
            # Note: Coordinate-based cookie fallback is SKIPPED in headless mode.
            # We rely exclusively on DOM-based strategies (ID, CSS, XPath).
            options.add_argument("--width=1920")
            options.add_argument("--height=1080")
            print("[PARSER] Headless mode enabled - Firefox will run without GUI (1920x1080)")
        else:
            # Normal mode with window manager integration (Komorebi)
            options.add_argument("--start-maximized")

        self.webdriver = webdriver.Firefox(options=options)
        self.headless = headless

        # Fullscreen only in GUI mode (not needed in headless)
        if not headless:
            try:
                self.webdriver.fullscreen_window()
            except Exception as e:
                # Fallback to maximize if fullscreen not supported
                print(f"[DEBUG] Fullscreen failed, falling back to maximize: {e}")
                self.webdriver.maximize_window()

        # Minimal delay for Firefox initialization
        # NOTE: Komorebi should have Firefox in float_rules to avoid window manager interference
        sleep(scraping_config.FIREFOX_STARTUP_DELAY)

    def close(self) -> None:
        self.webdriver.quit()

    def _accept_cookies(self) -> None:
        """Accept cookies banner using dynamic element detection.

        Tries multiple strategies in order:
        1. Find button by ID (didomi-notice-agree-button)
        2. Find button by CSS selector (common patterns)
        3. Find button by text content
        4. Fallback to hardcoded coordinates (Bug #1 legacy method)
        """
        # Strategy 1: Find by ID (most reliable)
        try:
            cookie_button = self.webdriver.find_element(By.ID, "didomi-notice-agree-button")
            cookie_button.click()
            logger.info("Cookie banner dismissed via ID selector")
            return
        except NoSuchElementException:
            # Expected - element not found, try next strategy
            pass
        except ElementNotInteractableException:
            logger.warning("[ERR_COOKIE_004] Cookie button found but not clickable via ID selector")
            pass
        except (InvalidSessionIdException, WebDriverException) as e:
            # CRITICAL: WebDriver crashed - cannot continue
            logger.critical(
                f"[ERR_COOKIE_007] FATAL: WebDriver session lost in ID strategy: "
                f"{type(e).__name__}",
                exc_info=e,
            )
            raise  # Re-raise to abort scraping
        except Exception as e:
            logger.error(
                f"[ERR_COOKIE_001] Unexpected error in ID strategy: {type(e).__name__}: {e}",
                exc_info=e,
            )
            pass

        # Strategy 2: Find by CSS selector (button with specific text)
        selectors = [
            "button[aria-label*='agree' i]",
            "button[aria-label*='accept' i]",
            "button.didomi-button",
            ".didomi-notice-agree-button",
        ]
        for selector in selectors:
            try:
                cookie_button = self.webdriver.find_element(By.CSS_SELECTOR, selector)
                cookie_button.click()
                logger.info(f"Cookie banner dismissed via CSS selector: {selector}")
                return
            except NoSuchElementException:
                # Expected - try next selector
                continue
            except ElementNotInteractableException:
                logger.warning(
                    f"[ERR_COOKIE_004] Cookie button found but not clickable via CSS: {selector}"
                )
                continue
            except (InvalidSessionIdException, WebDriverException) as e:
                # CRITICAL: WebDriver crashed - cannot continue
                logger.critical(
                    f"[ERR_COOKIE_007] FATAL: WebDriver session lost in CSS strategy: "
                    f"{type(e).__name__}",
                    exc_info=e,
                )
                raise  # Re-raise to abort scraping
            except Exception as e:
                logger.error(
                    f"[ERR_COOKIE_002] Unexpected error in CSS strategy ({selector}): "
                    f"{type(e).__name__}: {e}",
                    exc_info=e,
                )
                continue

        # Strategy 3: Find button by XPath with text content
        xpath_patterns = [
            "//button[contains(translate(text(), 'ACCEPT', 'accept'), 'accept')]",
            "//button[contains(translate(text(), 'AGREE', 'agree'), 'agree')]",
            "//button[contains(@class, 'agree')]",
        ]
        for xpath in xpath_patterns:
            try:
                cookie_button = self.webdriver.find_element(By.XPATH, xpath)
                cookie_button.click()
                logger.info(f"Cookie banner dismissed via XPath")
                return
            except NoSuchElementException:
                # Expected - try next XPath
                continue
            except ElementNotInteractableException:
                logger.warning("[ERR_COOKIE_004] Cookie button found but not clickable via XPath")
                continue
            except (InvalidSessionIdException, WebDriverException) as e:
                # CRITICAL: WebDriver crashed - cannot continue
                logger.critical(
                    f"[ERR_COOKIE_007] FATAL: WebDriver session lost in XPath strategy: "
                    f"{type(e).__name__}",
                    exc_info=e,
                )
                raise  # Re-raise to abort scraping
            except Exception as e:
                logger.error(
                    f"[ERR_COOKIE_003] Unexpected error in XPath strategy: "
                    f"{type(e).__name__}: {e}",
                    exc_info=e,
                )
                continue

        # Skip coordinate-based fallbacks in headless mode
        # Reason: LoLalytics cookie banner likely doesn't appear in headless,
        # or coordinates may be out of bounds despite viewport size
        if self.headless:
            # All DOM-based strategies failed, but this is expected in headless
            # Cookie banner is likely auto-accepted or doesn't exist
            logger.info(
                "Skipping coordinate-based cookie fallback in headless mode (DOM strategies sufficient)"
            )

            # Verify page is actually loaded and not stuck on cookie banner
            try:
                self.webdriver.find_element(By.TAG_NAME, "body")
                logger.info("Page structure verified - cookie banner handled successfully")
            except NoSuchElementException:
                logger.critical(
                    "[ERR_COOKIE_005] CRITICAL: Page failed to load despite cookie banner attempts",
                    exc_info=True,
                )
            return

        # Strategy 4: Fallback to hardcoded coordinates (Bug #1 legacy)
        # GUI mode only - coordinates are screen-dependent
        try:
            self.webdriver.execute_script(f"""
                var event = new MouseEvent('click', {{
                    view: window,
                    bubbles: true,
                    cancelable: true,
                    clientX: {scraping_config.COOKIE_CLICK_X},
                    clientY: {scraping_config.COOKIE_CLICK_Y}
                }});
                document.elementFromPoint({scraping_config.COOKIE_CLICK_X}, {scraping_config.COOKIE_CLICK_Y}).dispatchEvent(event);
            """)
            logger.info("Cookie banner dismissed via JavaScript coordinates click")
        except Exception as e:
            # Final fallback to ActionChains
            logger.error(
                f"[ERR_COOKIE_006] JavaScript coordinate click failed, trying ActionChains: "
                f"{type(e).__name__}",
                exc_info=e,
            )
            try:
                actions = ActionChains(self.webdriver)
                actions.move_by_offset(
                    scraping_config.COOKIE_CLICK_X, scraping_config.COOKIE_CLICK_Y
                ).click().perform()
                actions = ActionChains(self.webdriver)
                actions.move_by_offset(
                    -scraping_config.COOKIE_CLICK_X, -scraping_config.COOKIE_CLICK_Y
                ).perform()
                logger.info("Cookie banner dismissed via ActionChains coordinates click")
            except Exception as e2:
                logger.error(
                    f"[ERR_COOKIE_006] ActionChains coordinate click also failed: "
                    f"{type(e2).__name__}",
                    exc_info=e2,
                )
                # Give up gracefully - page may still load

    def get_matchup_data(self, champion: str, enemy: str) -> float:
        return self.get_matchup_data_on_patch(config.CURRENT_PATCH, champion, enemy)

    def get_matchup_data_on_patch(self, patch: str, champion: str, enemy: str) -> tuple:
        """Get matchup data for specific champions and patch with error handling."""
        url = f"https://lolalytics.com/lol/{champion}/vs/{enemy}/build/?tier=diamond_plus&patch={patch}"

        try:
            self.webdriver.get(url)
            tree = lxml.html.fromstring(self.webdriver.page_source)

            # Try to extract winrate with fallback paths
            winrate_elements = tree.xpath(xpath_config.WINRATE_XPATH)
            if not winrate_elements:
                print(f"Warning: Could not find winrate for {champion} vs {enemy}")
                return None, None

            winrate = float(winrate_elements[0])

            # Try to extract games with fallback paths
            games_elements = tree.xpath(xpath_config.GAMES_XPATH)
            if not games_elements:
                print(f"Warning: Could not find games count for {champion} vs {enemy}")
                return winrate, 0

            games = int(games_elements[0].replace(",", ""))
            return winrate, games

        except (ValueError, IndexError) as e:
            print(f"Error parsing data for {champion} vs {enemy}: {e}")
            return None, None
        except Exception as e:
            print(f"Unexpected error for {champion} vs {enemy}: {e}")
            return None, None

    def get_champion_data(self, champion: str, lane: str = None) -> List[tuple]:
        return self.get_champion_data_on_patch(config.CURRENT_PATCH, champion, lane)

    def get_champion_data_on_patch(
        self, patch: str, champion: str, lane: str = None
    ) -> List[tuple]:
        """Parse champion matchups (AGAINST enemies). Thin wrapper (SPEC-02)
        around get_champion_page_data() kept for scripts/repair_data.py."""
        matchups, _ = self.get_champion_page_data(patch, champion, lane, include_synergies=False)
        return matchups

    def get_champion_synergies(self, champion: str, lane: str = None) -> List[tuple]:
        """Parse champion synergies (WITH allies) from LoLalytics.

        Identical to get_champion_data but clicks the "Synergies" button first
        to switch from Counters to Synergies tab.

        Args:
            champion: Champion name (e.g., "yasuo")
            lane: Optional lane filter (e.g., "mid")

        Returns:
            List of tuples (ally_name, winrate, delta1, delta2, pickrate, games)

        Example:
            >>> parser.get_champion_synergies("yasuo", "mid")
            [('malphite', 55.0, 180.0, 220.0, 15.0, 1200), ...]
        """
        return self.get_champion_synergies_on_patch(config.CURRENT_PATCH, champion, lane)

    def get_champion_synergies_on_patch(
        self, patch: str, champion: str, lane: str = None
    ) -> List[tuple]:
        """Parse champion synergies for a specific patch. Thin wrapper (SPEC-02)
        around get_champion_page_data() kept for scripts/repair_data.py."""
        _, synergies = self.get_champion_page_data(patch, champion, lane, include_synergies=True)
        return synergies

    def _load_champion_page(self, patch: str, champion: str, lane: Optional[str] = None) -> None:
        """Load a champion's LoLalytics build page and prime it for scraping."""
        if lane:
            url = f"https://lolalytics.com/lol/{champion}/build/?lane={lane}&tier=diamond_plus&patch={patch}"
        else:
            url = f"https://lolalytics.com/lol/{champion}/build/?tier=diamond_plus&patch={patch}"

        self.webdriver.get(url)
        sleep(scraping_config.PAGE_LOAD_DELAY)

        # Scroll to trigger lazy-loading of the matchup section.
        # MATCHUP_SCROLL_Y must place the section (~Y=2200) inside the viewport.
        self.webdriver.execute_script(f"window.scrollTo(0, {scraping_config.MATCHUP_SCROLL_Y})")
        sleep(scraping_config.SCROLL_DELAY)

        self._accept_cookies()

    def _extract_carousel_rows(
        self,
        champion: str,
        row_range: range,
        label: str,
        name_from_href: Callable[[str], str],
    ) -> List[tuple]:
        """Wait for the tier-row carousel and walk it, extracting one tuple per
        opponent/ally cell: (name, winrate, delta1, delta2, pickrate, games).

        Shared by matchups (row_range=range(2, 7), 5 tiers, opponent names) and
        synergies (row_range=range(2, 6), 4 tiers, ally names) — see SPEC-02
        §3.1. Callers only differ by row_range and how the champion name is
        parsed out of the cell's ``href`` (matchup links contain "vs/", ally
        links don't).

        All guard rails from the original implementation (40ae072) are kept:
        stale-element breaks the inner pass so it re-fetches on the next loop,
        each cell is parsed in its own try/except, and the carousel stops on
        either a low-pickrate cell or ``prev_count == len(result)`` (infinite
        scroll guard).
        """
        result: List[tuple] = []

        # Wait for the first tier row container to exist in the DOM.
        first_row_path = xpath_config.MATCHUP_ROW_BASE.format(index=2)
        try:
            WebDriverWait(self.webdriver, 10).until(
                EC.presence_of_element_located((By.XPATH, first_row_path))
            )
        except TimeoutException:
            # Fallback: scrollIntoView the main section to trigger the lazy-loader
            try:
                section = self.webdriver.find_element(By.XPATH, "/html/body/main/div[6]")
                self.webdriver.execute_script("arguments[0].scrollIntoView(true);", section)
                sleep(2)
                WebDriverWait(self.webdriver, 5).until(
                    EC.presence_of_element_located((By.XPATH, first_row_path))
                )
            except (TimeoutException, NoSuchElementException):
                logger.warning(
                    "%s section never rendered for %s. Returning empty.", label, champion
                )
                return result

        for row_idx in row_range:
            path = xpath_config.MATCHUP_ROW_BASE.format(index=row_idx)

            # Bring this tier row into the center of the viewport
            try:
                container = self.webdriver.find_element(By.XPATH, path)
            except NoSuchElementException:
                logger.warning("%s row %d missing for %s.", label, row_idx, champion)
                continue
            self.webdriver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", container
            )
            sleep(0.3)

            pickrate = float("inf")

            while True:
                # Refresh elements each pass (carousel may add items after scroll)
                row = self.webdriver.find_elements(By.XPATH, f"{path}/*")
                prev_count = len(result)

                for elem_idx, elem in enumerate(row, start=1):
                    try:
                        href = elem.find_element(By.TAG_NAME, "a").get_dom_attribute("href")
                        name = name_from_href(href)
                        winrate = float(
                            elem.find_element(By.XPATH, f"{path}/div[{elem_idx}]/div[1]/span")
                            .get_attribute("innerHTML")
                            .split("%")[0]
                        )
                        my1_elements = elem.find_elements(By.CLASS_NAME, "my-1")
                        if len(my1_elements) < 7:
                            logger.warning(
                                "Insufficient my-1 elements for %s %s (%d). Skipping.",
                                name,
                                label.lower(),
                                len(my1_elements),
                            )
                            continue
                        delta1 = float(my1_elements[4].get_attribute("innerHTML"))
                        delta2 = float(my1_elements[5].get_attribute("innerHTML"))
                        pickrate = float(my1_elements[6].get_attribute("innerHTML"))
                        games = int(
                            "".join(
                                elem.find_element(By.CLASS_NAME, r"text-\[9px\]")
                                .get_attribute("innerHTML")
                                .split()
                            ).replace(",", "")
                        )
                        row_tuple = (name, winrate, delta1, delta2, pickrate, games)
                        if row_tuple not in result:
                            result.append(row_tuple)
                    except StaleElementReferenceException:
                        break  # row became stale mid-pass; re-fetch on next iteration
                    except (IndexError, ValueError, NoSuchElementException) as e:
                        logger.warning(
                            "Failed to parse %s element: %s: %s. Skipping.",
                            label.lower(),
                            type(e).__name__,
                            e,
                        )
                        continue

                # Stop if we have low-pickrate data or the carousel added nothing new
                if pickrate < analysis_config.MIN_PICKRATE or len(result) == prev_count:
                    break

                # Scroll carousel right to reveal the next batch of items
                self.webdriver.execute_script(
                    "arguments[0].scrollLeft += arguments[1];",
                    container,
                    scraping_config.MATCHUP_CAROUSEL_SCROLL_X,
                )
                sleep(0.5)

        return result

    def get_champion_page_data(
        self,
        patch: str,
        champion: str,
        lane: Optional[str] = None,
        include_synergies: bool = True,
    ) -> Tuple[List[tuple], List[tuple]]:
        """Load a champion's LoLalytics page once and read both carousels off it
        (SPEC-02 — matchups + synergies used to cost two full page visits).

        Returns ([], []) if the page never renders the matchups section.
        Returns (matchups, []) if the "Common Teammates" tab is missing or its
        section never renders: matchups already extracted are never lost.

        Args:
            patch: Patch version (e.g., "14.23")
            champion: Champion name (URL-normalized)
            lane: Optional lane filter (e.g., "mid")
            include_synergies: If False, skip the synergies tab entirely (used
                by the matchups-only wrapper and matchups-only callers).

        Returns:
            (matchups, synergies) tuples, each a list of
            (name, winrate, delta1, delta2, pickrate, games).
        """
        self._load_champion_page(patch, champion, lane)

        matchups = self._extract_carousel_rows(
            champion,
            range(2, 7),
            "Matchup",
            lambda href: href.split("vs/")[1].split("/build")[0],
        )
        if not matchups or not include_synergies:
            return matchups, []

        try:
            synergies_button = self.webdriver.find_element(
                By.XPATH, xpath_config.SYNERGIES_BUTTON_XPATH
            )
            synergies_button.click()
            logger.info("Clicked Synergies button for %s", champion)
        except NoSuchElementException:
            logger.warning(
                "Synergies button not found for %s (XPath: %s).",
                champion,
                xpath_config.SYNERGIES_BUTTON_XPATH,
            )
            return matchups, []
        except Exception as e:
            logger.error("Failed to click Synergies button for %s: %s", champion, e)
            return matchups, []

        # The click swaps the carousel content in place (no page reload): must
        # re-scroll and re-wait for the first row, otherwise the synergies
        # extraction below could still read the stale matchups content.
        self.webdriver.execute_script(f"window.scrollTo(0, {scraping_config.MATCHUP_SCROLL_Y})")
        sleep(scraping_config.SCROLL_DELAY)

        synergies = self._extract_carousel_rows(
            champion,
            range(2, 6),
            "Synergy",
            lambda href: href.split("/lol/")[1].split("/build")[0],
        )
        return matchups, synergies
