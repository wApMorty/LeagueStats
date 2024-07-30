import lxml.html
from selenium import webdriver
from selenium.webdriver.firefox.options import Options

class Parser:
    CURRENT_PATCH = "14.14"

    def __init__(self) -> None:
        options = Options()
        options.binary_location = r'C:\Program Files\Mozilla Firefox\firefox.exe'
        self.webdriver = webdriver.Firefox(executable_path=r'D:\Users\Paul\Téléchargement\geckodriver-v0.34.0-win32\geckodriver.exe', options=options)
    
    
    def get_matchup_data(self, champion: str, enemy: str) -> float :
        return self.get_matchup_data_on_patch(self.CURRENT_PATCH, champion, enemy)
    
    def get_matchup_data_on_patch(self, patch: str, champion: str, enemy: str) -> float :
        winrate = None
        games = None

        url = f"https://lolalytics.com/lol/{champion}/vs/{enemy}/build/?tier=diamond_plus&patch={patch}"

        self.webdriver.get(url)
        tree = lxml.html.fromstring(self.webdriver.page_source)

        winrate = float(tree.xpath('/html/body/main/div[5]/div[1]/div[2]/div[3]/div/div/div[1]/div[1]/text()')[0])
        games = int(tree.xpath('/html/body/main/div[5]/div[1]/div[2]/div[3]/div/div/div[2]/div[1]/text()')[0].replace(",", ""))

        self.webdriver.close()

        return winrate, games
