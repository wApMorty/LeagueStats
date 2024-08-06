import requests

class RiotAPI:
    def __init__(self) -> None:
        self.current_patch = self.downloadCurrentPatch()
        self.champions_list = self.downloadChampsFromCurrentPatch()

    ### DOWNLOAD DATA FROM INTERNET

    def downloadCurrentPatch(self) -> str:
        return self.getFileFromURL("https://ddragon.leagueoflegends.com/api/versions.json")[0]

    def downloadChampsFromCurrentPatch(self) -> dict:
        champList = self.getFileFromURL("https://ddragon.leagueoflegends.com/cdn/"+self.current_patch+"/data/en_US/champion.json")["data"].keys()
        champList= ["Wukong" if x == "MonkeyKing" else x for x in champList] # The MonkeyKing case, the famous one
        return champList

    ### RETURN DATA TO ASKERS

    def getCurrentPatch(self) -> str:
        return self.current_patch
    
    def getChampsFromCurrentPatch(self) -> dict:
        return self.champions_list
    
    ### TOOLS ?

    def getFileFromURL(self, url):
        try:
            response = requests.get(url)
            if response.status_code == 200:
                json_data = response.json()
                return json_data
            else:
                print("Request failed:", response.status_code)
                return None
        except requests.RequestException as e:
            print("Impossible de récupérer les données JSON. ", e)
            return None