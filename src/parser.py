from time import sleep
from typing import List
import lxml.html

from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options

from .config import config
from .config_constants import scraping_config, xpath_config


class Parser:
    def __init__(self) -> None:
        options = Options()
        options.binary_location = config.get_firefox_path()
        # Add argument to start maximized (helps with window managers like Komorebi)
        options.add_argument("--start-maximized")
        self.webdriver = webdriver.Firefox(options=options)

        # Fullscreen mode (with Firefox exception configured in Komorebi)
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
        try:
            # Strategy 1: Find by ID (most reliable)
            cookie_button = self.webdriver.find_element(By.ID, "didomi-notice-agree-button")
            cookie_button.click()
            return
        except Exception:
            # Strategy 1 failed, try next approach
            pass

        try:
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
                    return
                except Exception:
                    continue
        except Exception:
            # Strategy 2 failed, try next approach
            pass

        try:
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
                    return
                except Exception:
                    continue
        except Exception:
            # Strategy 3 failed, try next approach
            pass

        # Strategy 4: Fallback to hardcoded coordinates (Bug #1 legacy)
        try:
            self.webdriver.execute_script(
                f"""
                var event = new MouseEvent('click', {{
                    view: window,
                    bubbles: true,
                    cancelable: true,
                    clientX: {scraping_config.COOKIE_CLICK_X},
                    clientY: {scraping_config.COOKIE_CLICK_Y}
                }});
                document.elementFromPoint({scraping_config.COOKIE_CLICK_X}, {scraping_config.COOKIE_CLICK_Y}).dispatchEvent(event);
            """
            )
        except Exception:
            # Final fallback to ActionChains
            actions = ActionChains(self.webdriver)
            actions.move_by_offset(
                scraping_config.COOKIE_CLICK_X, scraping_config.COOKIE_CLICK_Y
            ).click().perform()
            actions = ActionChains(self.webdriver)
            actions.move_by_offset(
                -scraping_config.COOKIE_CLICK_X, -scraping_config.COOKIE_CLICK_Y
            ).perform()

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
        result = []

        # Build URL with optional lane parameter
        if lane:
            url = f"https://lolalytics.com/lol/{champion}/build/?lane={lane}&tier=diamond_plus&patch={patch}"
        else:
            url = f"https://lolalytics.com/lol/{champion}/build/?tier=diamond_plus&patch={patch}"

        self.webdriver.get(url)

        sleep(scraping_config.PAGE_LOAD_DELAY)

        self.webdriver.execute_script(f"window.scrollTo(0,{scraping_config.MATCHUP_SCROLL_Y})")

        sleep(scraping_config.SCROLL_DELAY)

        # region Accepting cookies
        self._accept_cookies()
        # endregion

        for index in range(2, 7):
            path = f"/html/body/main/div[6]/div[1]/div[{index}]/div[2]/div"
            row = self.webdriver.find_elements(By.XPATH, f"{path}/*")
            actions = ActionChains(self.webdriver)
            actions.move_to_element_with_offset(
                row[0], scraping_config.MATCHUP_CAROUSEL_SCROLL_X, 0
            ).perform()
            enough_data = False
            while not enough_data:
                for elem in row:
                    index = row.index(elem) + 1
                    champ = (
                        elem.find_element(By.TAG_NAME, "a")
                        .get_dom_attribute("href")
                        .split("vs/")[1]
                        .split("/build")[0]
                    )
                    winrate = float(
                        elem.find_element(By.XPATH, f"{path}/div[{index}]/div[1]/span")
                        .get_attribute("innerHTML")
                        .split("%")[0]
                    )
                    delta1 = float(
                        elem.find_elements(By.CLASS_NAME, "my-1")[4].get_attribute("innerHTML")
                    )
                    delta2 = float(
                        elem.find_elements(By.CLASS_NAME, "my-1")[5].get_attribute("innerHTML")
                    )
                    pickrate = float(
                        elem.find_elements(By.CLASS_NAME, "my-1")[6].get_attribute("innerHTML")
                    )
                    games = int(
                        "".join(
                            elem.find_element(By.CLASS_NAME, r"text-\[9px\]")
                            .get_attribute("innerHTML")
                            .split()
                        )
                    )
                    if not self.contains(result, champ, winrate, delta1, delta2, pickrate, games):
                        result.append((champ, winrate, delta1, delta2, pickrate, games))
                actions = ActionChains(self.webdriver)
                actions.click_and_hold().move_by_offset(
                    -scraping_config.MATCHUP_CAROUSEL_SCROLL_X, 0
                ).release().move_by_offset(scraping_config.MATCHUP_CAROUSEL_SCROLL_X, 0).perform()
                enough_data = pickrate < config.MIN_PICKRATE
        return result

    def contains(self, list, champ, winrate, d1, d2, pick, games) -> bool:
        ctns = False
        for i in range(len(list)):
            l_champ, l_winrate, l_delta1, l_delta2, l_pickrate, l_games = list[i]
            if (
                l_champ == champ
                and l_winrate == winrate
                and l_delta1 == d1
                and l_delta2 == d2
                and l_pickrate == pick
                and l_games == games
            ):
                ctns = True
                break
        return ctns
