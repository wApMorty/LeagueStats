"""Quick smoke-test: scrape one champion and print results."""
import logging
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)

from src.parser import Parser
from src.config import config
from src.constants import normalize_champion_name_for_url

CHAMPION = "yasuo"
HEADLESS = False  # visible so you can see what Firefox does

print(f"[TEST] Scraping matchups for {CHAMPION} on patch {config.CURRENT_PATCH}")
parser = Parser(headless=HEADLESS)
try:
    matchups = parser.get_champion_data_on_patch(config.CURRENT_PATCH, CHAMPION)
    print(f"[TEST] Matchups found: {len(matchups)}")
    if matchups:
        print("[TEST] First 3:", matchups[:3])
    else:
        print("[TEST] WARNING: 0 matchups returned!")

    print(f"\n[TEST] Scraping synergies for {CHAMPION}")
    synergies = parser.get_champion_synergies_on_patch(config.CURRENT_PATCH, CHAMPION)
    print(f"[TEST] Synergies found: {len(synergies)}")
    if synergies:
        print("[TEST] First 3:", synergies[:3])
    else:
        print("[TEST] WARNING: 0 synergies returned!")
finally:
    parser.close()
    print("[TEST] Done.")
