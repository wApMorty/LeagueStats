from riotapi import RiotAPI
import numpy as np

rAPI = RiotAPI()

CURRENT_PATCH = rAPI.getCurrentPatch()
CHAMPIONS_LIST = np.unique(rAPI.getChampsFromCurrentPatch())