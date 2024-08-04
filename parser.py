from time import sleep
from typing import List
from constants import CURRENT_PATCH

import lxml.html

from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options

class Parser:
    def __init__(self) -> None:
        options = Options()
        options.binary_location = r'C:\Program Files\Mozilla Firefox\firefox.exe'
        self.webdriver = webdriver.Firefox(executable_path=r'D:\Users\Paul\Téléchargement\geckodriver-v0.34.0-win32\geckodriver.exe', options=options)
        self.webdriver.maximize_window()

    def close(self) -> None:
        self.webdriver.quit()

    def get_matchup_data(self, champion: str, enemy: str) -> float :
        return self.get_matchup_data_on_patch(CURRENT_PATCH, champion, enemy)

    def get_matchup_data_on_patch(self, patch: str, champion: str, enemy: str) -> tuple :
        winrate = None
        games = None

        url = f"https://lolalytics.com/lol/{champion}/vs/{enemy}/build/?tier=diamond_plus&patch={patch}"

        self.webdriver.get(url)
        tree = lxml.html.fromstring(self.webdriver.page_source)
        
        winrate = float(tree.xpath('/html/body/main/div[5]/div[1]/div[2]/div[3]/div/div/div[1]/div[1]/text()')[0])
        games = int(tree.xpath('/html/body/main/div[5]/div[1]/div[2]/div[3]/div/div/div[2]/div[1]/text()')[0].replace(",", ""))

        return winrate, games

    def get_champion_data(self, champion: str) -> List[tuple]:
        return self.get_champion_data_on_patch(CURRENT_PATCH, champion)

    def get_champion_data_on_patch(self, patch: str, champion: str) -> List[tuple]:
        result = []
        
        url = f"https://lolalytics.com/lol/{champion}/build/?tier=diamond_plus&patch={patch}"

        self.webdriver.get(url)
        
        self.webdriver.execute_script("window.scrollTo(0,1310)")
        
        sleep(5)
        
        # Accepting cookies
        actions = ActionChains(self.webdriver)
        actions.move_by_offset(1661, 853).click().perform()
        
        actions = ActionChains(self.webdriver)
        actions.move_by_offset(-1661, -853).perform()
        
        actions = ActionChains(self.webdriver)
        actions.move_by_offset(1187, 151).perform()
        
        for index in range (2, 7):
            actions = ActionChains(self.webdriver)
            actions.move_by_offset(0, 154).perform()
            path = f"/html/body/main/div[6]/div[1]/div[{index}]/div[2]/div"
            enough_data = False
            
            while not enough_data:
                row = self.webdriver.find_elements(By.XPATH, f"{path}/*")
                
                for elem in row:
                    champ = elem.find_element(By.TAG_NAME, "a").get_dom_attribute("href").split("vs/")[1].split("/build")[0]
                    winrate = float(elem.find_element(By.XPATH, f"{path}/div[{row.index(elem)+1}]/div[1]/span").get_attribute('innerHTML').split('%')[0])
                    delta1 = float(elem.find_elements(By.CLASS_NAME, "my-1")[4].get_attribute('innerHTML'))
                    delta2 = float(elem.find_elements(By.CLASS_NAME, "my-1")[5].get_attribute('innerHTML'))
                    pickrate = float(elem.find_elements(By.CLASS_NAME, "my-1")[6].get_attribute('innerHTML'))
                    games = int(''.join(elem.find_element(By.CLASS_NAME, "text-\[9px\]").get_attribute('innerHTML').split()))
                    if not self.contains(result, champ, winrate, delta1, delta2, pickrate, games):
                        result.append((champ, winrate, delta1, delta2, pickrate, games))
                
                enough_data = pickrate < 0.2
                actions = ActionChains(self.webdriver)
                actions.click().perform()
            
        return result
    
    def contains(self, list, champ, winrate, d1, d2, pick, games) -> bool:
        ctns = False
        for i in range(len(list)):
            l_champ, l_winrate, l_delta1, l_delta2, l_pickrate, l_games = list[i]
            if (l_champ == champ and l_winrate == winrate and l_delta1 == d1 and l_delta2 == d2 and l_pickrate == pick and l_games == games):
                ctns = True
                break;
        return ctns