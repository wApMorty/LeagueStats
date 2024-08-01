import lxml.html
from constants import CURRENT_PATCH, CHAMPIONS_LIST
from selenium import webdriver
from selenium.webdriver.firefox.options import Options

class Parser:
    def __init__(self) -> None:
        options = Options()
        options.binary_location = r'C:\Program Files\Mozilla Firefox\firefox.exe'
        self.webdriver = webdriver.Firefox(executable_path=r'D:\Users\Paul\Téléchargement\geckodriver-v0.34.0-win32\geckodriver.exe', options=options)

    def close(self) -> None:
        self.webdriver.quit()

    def get_matchup_data(self, champion: str, enemy: str) -> float :
        return self.get_matchup_data_on_patch(CURRENT_PATCH, champion, enemy)

    def get_matchup_data_on_patch(self, patch: str, champion: str, enemy: str) -> float :
        winrate = None
        games = None

        url = f"https://lolalytics.com/lol/{champion}/vs/{enemy}/build/?tier=diamond_plus&patch={patch}"

        self.webdriver.get(url)
        tree = lxml.html.fromstring(self.webdriver.page_source)
        
        winrate = float(tree.xpath('/html/body/main/div[5]/div[1]/div[2]/div[3]/div/div/div[1]/div[1]/text()')[0])
        games = int(tree.xpath('/html/body/main/div[5]/div[1]/div[2]/div[3]/div/div/div[2]/div[1]/text()')[0].replace(",", ""))

        return winrate, games

    def get_champion_data(self, champion: str) -> dict:
        return self.get_champion_data_on_patch(CURRENT_PATCH, champion)

    def get_champion_data_on_patch(self, patch: str, champion: str) -> dict:
        url = f"https://lolalytics.com/lol/{champion}/build/?tier=diamond_plus&patch={patch}"
        
        self.webdriver.get(url)
        tree = lxml.html.fromstring(self.webdriver.page_source)
        page_data = tree.xpath('/html/body/main/div[6]/div[1]')
        