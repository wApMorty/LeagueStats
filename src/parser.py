from time import sleep
from typing import List
import lxml.html

from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options

from .config import config, denormalize_champion_name_from_url

class Parser:
    def __init__(self) -> None:
        options = Options()
        options.binary_location = config.get_firefox_path()
        self.webdriver = webdriver.Firefox(options=options)
        self.webdriver.maximize_window()

    def close(self) -> None:
        self.webdriver.quit()

    def get_matchup_data(self, champion: str, enemy: str) -> float :
        return self.get_matchup_data_on_patch(config.CURRENT_PATCH, champion, enemy)

    def get_matchup_data_on_patch(self, patch: str, champion: str, enemy: str) -> tuple:
        """Get matchup data for specific champions and patch with error handling."""
        url = f"https://lolalytics.com/lol/{champion}/vs/{enemy}/build/?tier=diamond_plus&patch={patch}"
        
        try:
            self.webdriver.get(url)
            tree = lxml.html.fromstring(self.webdriver.page_source)
            
            # Try to extract winrate with fallback paths
            winrate_xpath = '/html/body/main/div[5]/div[1]/div[2]/div[3]/div/div/div[1]/div[1]/text()'
            winrate_elements = tree.xpath(winrate_xpath)
            if not winrate_elements:
                print(f"Warning: Could not find winrate for {champion} vs {enemy}")
                return None, None
            
            winrate = float(winrate_elements[0])
            
            # Try to extract games with fallback paths
            games_xpath = '/html/body/main/div[5]/div[1]/div[2]/div[3]/div/div/div[2]/div[1]/text()'
            games_elements = tree.xpath(games_xpath)
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

    def get_champion_data_on_patch(self, patch: str, champion: str, lane: str = None) -> List[tuple]:
        result = []
        
        url = ""
        if lane is not None:
            url = f"https://lolalytics.com/lol/{champion}/build/?lane={lane}&tier=diamond_plus&patch={patch}"
        else:
            url = f"https://lolalytics.com/lol/{champion}/build/?tier=diamond_plus&patch={patch}"

        self.webdriver.get(url)
        
        sleep(config.PAGE_LOAD_DELAY)
        
        self.webdriver.execute_script("window.scrollTo(0,1310)")
        
        sleep(config.SCROLL_DELAY)
        
        #region Accepting cookies
        actions = ActionChains(self.webdriver)
        actions.move_by_offset(1661, 853).click().perform()
        
        actions = ActionChains(self.webdriver)
        actions.move_by_offset(-1661, -853).perform()
        #endregion
        
        try:
            for index in range(2, 7):
                path = f"/html/body/main/div[6]/div[1]/div[{index}]/div[2]/div"
                row = self.webdriver.find_elements(By.XPATH, f"{path}/*")
                
                if not row:
                    print(f"Warning: No elements found for {champion} at index {index}")
                    continue
                    
                actions = ActionChains(self.webdriver)
                actions.move_to_element_with_offset(row[0], 460, 0).perform()
                enough_data = False
                
                while not enough_data:
                    try:
                        for elem_idx, elem in enumerate(row):
                            try:
                                # Extract champion name
                                link_elem = elem.find_element(By.TAG_NAME, "a")
                                href = link_elem.get_dom_attribute("href")
                                if not href or "vs/" not in href:
                                    continue
                                url_name = href.split("vs/")[1].split("/build")[0]
                                champ = denormalize_champion_name_from_url(url_name)
                                
                                # Extract stats with error handling
                                winrate_elem = elem.find_element(By.XPATH, f"{path}/div[{elem_idx+1}]/div[1]/span")
                                winrate_text = winrate_elem.get_attribute('innerHTML')
                                winrate = float(winrate_text.split('%')[0]) if winrate_text else 0.0
                                
                                my_elements = elem.find_elements(By.CLASS_NAME, "my-1")
                                if len(my_elements) < 7:
                                    print(f"Warning: Insufficient data elements for {champ}")
                                    continue
                                    
                                delta1 = float(my_elements[4].get_attribute('innerHTML') or 0)
                                delta2 = float(my_elements[5].get_attribute('innerHTML') or 0)
                                pickrate = float(my_elements[6].get_attribute('innerHTML') or 0)
                                
                                games_elem = elem.find_element(By.CLASS_NAME, r"text-\[9px\]")
                                games_text = games_elem.get_attribute('innerHTML')
                                games = int(''.join(games_text.split())) if games_text else 0
                                
                                if not self.contains(result, champ, winrate, delta1, delta2, pickrate, games):
                                    result.append((champ, winrate, delta1, delta2, pickrate, games))
                                    
                            except Exception as e:
                                print(f"Error processing element for {champion}: {e}")
                                continue
                        
                        # Scroll action with error handling
                        try:
                            actions = ActionChains(self.webdriver)
                            actions.click_and_hold().move_by_offset(-460, 0).release().move_by_offset(460, 0).perform()
                            enough_data = pickrate < 0.5
                        except Exception as e:
                            print(f"Error during scroll action: {e}")
                            break
                            
                    except Exception as e:
                        print(f"Error in data extraction loop for {champion}: {e}")
                        break
                        
        except Exception as e:
            print(f"Critical error in get_champion_data_on_patch for {champion}: {e}")
            return result
        return result
    
    def contains(self, list, champ, winrate, d1, d2, pick, games) -> bool:
        ctns = False
        for i in range(len(list)):
            l_champ, l_winrate, l_delta1, l_delta2, l_pickrate, l_games = list[i]
            if (l_champ == champ and l_winrate == winrate and l_delta1 == d1 and l_delta2 == d2 and l_pickrate == pick and l_games == games):
                ctns = True
                break;
        return ctns