"""Cookie banner dismissal mixin for Parser (dette de code, TODO.md P4).

Extracted from src/parser.py : déplacement verbatim, aucun changement de
comportement. Concern autonome (4 stratégies de repli pour fermer le
bandeau cookies Didomi de LoLalytics) qui n'utilise que
``self.webdriver``/``self.headless`` — aucun état supplémentaire à câbler,
mixin partageant le même ``self`` que le reste de ``Parser``.
"""

import logging

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    NoSuchElementException,
    ElementNotInteractableException,
    InvalidSessionIdException,
    WebDriverException,
)

from .config_constants import scraping_config

logger = logging.getLogger(__name__)

# Error codes are written inline as an "[ERR_<CATEGORY>_<NNN>]" message prefix so
# they stay greppable in the logs. Cookie banner codes, by severity:
#   ERROR    ERR_COOKIE_001/002/003 (ID/CSS/XPath strategy blew up),
#            ERR_COOKIE_006 (coordinate click failed, GUI mode)
#   WARNING  ERR_COOKIE_004 (button found but not interactable)
#   CRITICAL ERR_COOKIE_005 (page never loaded), ERR_COOKIE_007 (WebDriver session lost)


class _CookieBannerMixin:
    """_accept_cookies() — fermeture du bandeau cookies Didomi de LoLalytics."""

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
