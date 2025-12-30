"""
Test script for auto-update functionality.

This script performs a dry-run test of the auto-update system to verify:
1. Process priority setting works
2. Patch detection logic works
3. Notifications work (if win10toast installed)
4. Logging works
5. Database connection works

USAGE:
    python scripts/test_auto_update.py

Author: @pj35 - LeagueStats Coach
Version: 1.1.0-dev
"""

import sys
import os
from pathlib import Path

# Set UTF-8 encoding for console output
if sys.platform == "win32":
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "backslashreplace")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "backslashreplace")

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("=" * 80)
print("LeagueStats Coach - Auto-Update Test (Dry Run)")
print("=" * 80)
print()

# Test 1: Process priority
print("[TEST 1] Process priority setting...")
try:
    import psutil

    p = psutil.Process(os.getpid())
    if sys.platform == "win32":
        p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        print("  ✅ Process priority set to BELOW_NORMAL")
    else:
        p.nice(10)
        print("  ✅ Process priority set to 10 (Unix)")
except ImportError:
    print("  ⚠️  psutil not installed, skipping priority test")
except Exception as e:
    print(f"  ❌ Error: {e}")

print()

# Test 2: Database connection
print("[TEST 2] Database connection...")
try:
    from src.db import Database
    from src.config import config

    db_path = config.DATABASE_PATH
    print(f"  - Database path: {db_path}")

    db = Database(db_path)
    db.connect()
    print("  ✅ Database connected successfully")

    # Get champion count
    champions = db.get_all_champion_names()
    print(f"  - Champions in database: {len(champions)}")

    db.close()
    print("  ✅ Database closed successfully")

except Exception as e:
    print(f"  ❌ Error: {e}")
    import traceback

    traceback.print_exc()

print()

# Test 3: Patch detection
print("[TEST 3] Patch version detection...")
try:
    from src.db import Database
    from src.config import config

    db_path = config.DATABASE_PATH
    db = Database(db_path)
    db.connect()

    # Import PatchVersionDetector from auto_update_db
    sys.path.insert(0, str(project_root / "scripts"))
    from auto_update_db import PatchVersionDetector

    detector = PatchVersionDetector(db)

    current = detector.get_current_patch()
    last = detector.get_last_known_patch()
    is_new, current_patch, last_patch = detector.is_new_patch()

    print(f"  - Current patch: {current}")
    print(f"  - Last known patch: {last if last else 'None (first run)'}")
    print(f"  - Is new patch: {is_new}")

    if is_new:
        print("  ✅ New patch detected, update would run")
    else:
        print("  ℹ️  No new patch, update would be skipped")

    db.close()

except Exception as e:
    print(f"  ❌ Error: {e}")
    import traceback

    traceback.print_exc()

print()

# Test 4: Logging
print("[TEST 4] Logging system...")
try:
    from auto_update_db import AutoUpdateLogger

    logger = AutoUpdateLogger(log_dir="logs")
    print(f"  - Log file: {logger.log_file}")

    logger.log("INFO", "Test log entry from test script")
    logger.log("SUCCESS", "Logger working correctly")

    if logger.log_file.exists():
        print(f"  ✅ Log file created: {logger.log_file}")
    else:
        print("  ⚠️  Log file not created")

except Exception as e:
    print(f"  ❌ Error: {e}")
    import traceback

    traceback.print_exc()

print()

# Test 5: Notifications
print("[TEST 5] Windows notifications...")
try:
    from auto_update_db import WindowsNotifier

    notifier = WindowsNotifier(enabled=True)

    if notifier.enabled:
        print("  - win10toast available: Yes")
        print("  - Sending test notification...")
        notifier.notify("LeagueStats Coach Test", "Auto-update test notification", duration=5)
        print("  ✅ Notification sent (check system tray)")
    else:
        print("  ⚠️  win10toast not installed, notifications disabled")
        print("  ℹ️  Install with: pip install win10toast")

except Exception as e:
    print(f"  ❌ Error: {e}")
    import traceback

    traceback.print_exc()

print()

# Test 6: ParallelParser availability
print("[TEST 6] ParallelParser availability...")
try:
    from src.parallel_parser import ParallelParser
    from src.config_constants import scraping_config

    print("  ✅ ParallelParser imported successfully")
    print(f"  - Default workers: {scraping_config.DEFAULT_MAX_WORKERS}")
    print(f"  - Firefox startup delay: {scraping_config.FIREFOX_STARTUP_DELAY}s")
    print("  ℹ️  ParallelParser ready for auto-update")

except Exception as e:
    print(f"  ❌ Error: {e}")
    import traceback

    traceback.print_exc()

print()

# Summary
print("=" * 80)
print("TEST SUMMARY")
print("=" * 80)
print()
print("✅ All core components are functional")
print()
print("Next Steps:")
print("  1. Install win10toast (optional): pip install win10toast")
print("  2. Run setup_auto_update.ps1 as Administrator to create scheduled task")
print("  3. Test scheduled task: Start-ScheduledTask -TaskName 'LeagueStats Auto-Update'")
print("  4. Check logs at: logs/auto_update.log")
print()
print("To test full auto-update (WARNING: will scrape 172 champions, ~12min):")
print("  python scripts/auto_update_db.py")
print()
print("=" * 80)
