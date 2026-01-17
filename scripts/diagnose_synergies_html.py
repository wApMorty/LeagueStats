"""Diagnostic script to inspect synergies HTML structure."""

import sys
from pathlib import Path
from time import sleep

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from src.config_constants import xpath_config, scraping_config

print("=" * 80)
print("SYNERGIES HTML STRUCTURE DIAGNOSTIC")
print("=" * 80)

# Setup Firefox in headless mode
options = Options()
options.add_argument("--headless")
driver = webdriver.Firefox(options=options)
driver.maximize_window()

try:
    # Load Yasuo's page
    url = "https://lolalytics.com/lol/yasuo/build/?patch=14"
    print(f"\nLoading: {url}")
    driver.get(url)
    sleep(scraping_config.PAGE_LOAD_DELAY)

    # Accept cookies
    try:
        driver.execute_script(
            f"document.elementFromPoint({scraping_config.COOKIE_CLICK_X}, "
            f"{scraping_config.COOKIE_CLICK_Y}).click()"
        )
        sleep(scraping_config.COOKIE_BUTTON_DELAY)
        print("Cookies accepted")
    except:
        pass

    # Click Synergies button
    print(f"\nSearching for Synergies button with XPath: {xpath_config.SYNERGIES_BUTTON_XPATH}")
    synergies_button = driver.find_element(By.XPATH, xpath_config.SYNERGIES_BUTTON_XPATH)
    synergies_button.click()
    print("Clicked Synergies button")

    # Wait for synergies to load
    wait = WebDriverWait(driver, 10)
    first_row_xpath = "/html/body/main/div[6]/div[1]/div[2]/div[2]/div"
    wait.until(EC.presence_of_element_located((By.XPATH, first_row_xpath)))
    print("Synergies data loaded")
    sleep(scraping_config.PAGE_LOAD_DELAY)

    # Scroll to synergies section
    driver.execute_script(f"window.scrollTo(0,{scraping_config.MATCHUP_SCROLL_Y})")
    sleep(scraping_config.SCROLL_DELAY)

    # Inspect FIRST synergy element in detail
    print("\n" + "=" * 80)
    print("INSPECTING FIRST SYNERGY ELEMENT (Row 2, First Champion)")
    print("=" * 80)

    path = "/html/body/main/div[6]/div[1]/div[2]/div[2]/div"
    row = driver.find_elements(By.XPATH, f"{path}/*")

    print(f"\nTotal champions in row 2: {len(row)}")

    if row:
        first_elem = row[0]

        # Get champion name
        try:
            ally_link = first_elem.find_element(By.TAG_NAME, "a")
            href = ally_link.get_dom_attribute("href")
            print(f"\nChampion link: {href}")
            ally_name = href.split("vs/")[1].split("/build")[0]
            print(f"Champion name: {ally_name}")
        except Exception as e:
            print(f"Failed to get champion name: {e}")

        # Get winrate
        try:
            winrate_elem = first_elem.find_element(By.XPATH, f"{path}/div[1]/div[1]/span")
            winrate_html = winrate_elem.get_attribute("innerHTML")
            print(f"Winrate HTML: {winrate_html}")
        except Exception as e:
            print(f"Failed to get winrate: {e}")

        # CRITICAL: Inspect my-1 elements
        print("\n" + "-" * 80)
        print("MY-1 ELEMENTS INSPECTION:")
        print("-" * 80)

        my1_elements = first_elem.find_elements(By.CLASS_NAME, "my-1")
        print(f"\nTotal 'my-1' elements found: {len(my1_elements)}")

        if my1_elements:
            print("\nContent of each 'my-1' element:")
            for i, elem in enumerate(my1_elements):
                html = elem.get_attribute("innerHTML")
                print(f"  [{i}]: {html}")
        else:
            print("\nNO 'my-1' ELEMENTS FOUND!")

            # Alternative: Try to find ALL div elements
            print("\n" + "-" * 80)
            print("ALTERNATIVE: All div elements in first champion:")
            print("-" * 80)
            all_divs = first_elem.find_elements(By.TAG_NAME, "div")
            print(f"\nTotal div elements: {len(all_divs)}")

            # Try to find elements with different class names
            print("\n" + "-" * 80)
            print("SEARCHING FOR ALTERNATIVE CLASS NAMES:")
            print("-" * 80)

            possible_classes = ["my-1", "my-2", "mx-1", "mx-2", "m-1", "m-2", "text-xs", "text-sm"]
            for class_name in possible_classes:
                elements = first_elem.find_elements(By.CLASS_NAME, class_name)
                if elements:
                    print(f"\nClass '{class_name}': {len(elements)} elements found")
                    for i, elem in enumerate(elements[:5]):  # Show first 5
                        html = elem.get_attribute("innerHTML")
                        print(f"  [{i}]: {html}")

        # Get games count
        try:
            games_elem = first_elem.find_element(By.CLASS_NAME, r"text-\[9px\]")
            games_html = games_elem.get_attribute("innerHTML")
            print(f"\nGames HTML: {games_html}")
        except Exception as e:
            print(f"Failed to get games: {e}")

        print("\n" + "=" * 80)
        print("COMPARING WITH MATCHUPS TAB")
        print("=" * 80)

        # Click back to Counters/Matchups to compare structure
        try:
            counters_xpath = "//span[text()='Counters']/.."
            counters_button = driver.find_element(By.XPATH, counters_xpath)
            counters_button.click()
            sleep(scraping_config.PAGE_LOAD_DELAY)
            print("\nClicked Counters button")

            # Wait for matchups to load
            wait.until(EC.presence_of_element_located((By.XPATH, first_row_xpath)))
            sleep(scraping_config.PAGE_LOAD_DELAY)

            # Inspect first matchup element
            row = driver.find_elements(By.XPATH, f"{path}/*")
            if row:
                first_matchup = row[0]
                my1_matchup = first_matchup.find_elements(By.CLASS_NAME, "my-1")
                print(f"\nMatchups 'my-1' elements: {len(my1_matchup)}")

                if my1_matchup:
                    print("\nMatchup 'my-1' content:")
                    for i, elem in enumerate(my1_matchup):
                        html = elem.get_attribute("innerHTML")
                        print(f"  [{i}]: {html}")

        except Exception as e:
            print(f"Failed to compare with matchups: {e}")
            import traceback

            traceback.print_exc()

finally:
    driver.quit()
    print("\nDriver closed.")
