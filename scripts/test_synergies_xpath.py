"""Quick test script for synergies XPath fix."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.parser import Parser
from src.config_constants import xpath_config

print("=" * 60)
print("SYNERGIES XPATH TEST")
print("=" * 60)

# Verify new XPath
print(f"\nConfigured XPath: {xpath_config.SYNERGIES_BUTTON_XPATH}")

# Test on Yasuo
print("\nTesting on Yasuo (GUI mode to see the page)...")
parser = Parser(headless=False)

try:
    synergies = parser.get_champion_synergies("yasuo")
    print(f"\nSuccess! Found {len(synergies)} synergies for Yasuo")

    if synergies:
        print("\nTop 5 synergies:")
        for ally, wr, d1, d2, pr, games in synergies[:5]:
            print(f"  - {ally:<15} WR={wr:5.1f}%  Delta2={d2:6.0f}  Games={games:,}")
    else:
        print("\nWARNING: No synergies returned (problem persists)")

except Exception as e:
    print(f"\nERROR: {e}")
    import traceback

    traceback.print_exc()
finally:
    parser.close()
    print("\nParser closed.")
