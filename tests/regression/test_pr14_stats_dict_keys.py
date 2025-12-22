"""Regression test for PR #14: ParallelParser stats dict key naming.

Bug Report:
-----------
Date: 2025-12-22
Reporter: User (@pj35)
Symptom: Auto-update logs showed "0/172 succeeded" despite successful scraping
Log: [2025-12-22 01:17:16] INFO: Champions parsed: 0/172 succeeded, 0 failed

Root Cause:
-----------
- scripts/auto_update_db.py line 189 used: stats.get('successful', 0)
- src/parallel_parser.py line 228 returned: stats['success']
- Key mismatch caused default value 0 to be returned

Fix:
----
Commit: 980048d
PR: #14
Change: 'successful' → 'success' in auto_update_db.py

Prevention:
-----------
This test ensures the stats dict keys remain consistent and documented.
"""

import pytest
from src.parallel_parser import ParallelParser
from src.db import Database
from src.constants import normalize_champion_name_for_url


def test_parallel_parser_stats_dict_has_correct_keys():
    """Verify ParallelParser.parse_all_champions() returns correct stats dict keys.

    Regression test for PR #14 bug where 'successful' was used instead of 'success',
    causing stats to report 0 champions parsed.
    """
    # Setup: Create in-memory database
    db = Database(":memory:")
    db.connect()

    # Create minimal parser (1 worker to speed up test)
    parser = ParallelParser(max_workers=1, patch_version="14")

    try:
        # Act: Call parse_all_champions (will scrape from Riot API)
        # Note: This is an integration test that hits real API
        stats = parser.parse_all_champions(db, normalize_champion_name_for_url)

        # Assert: Verify all expected keys exist
        assert 'success' in stats, (
            "stats dict must contain 'success' key (not 'successful'). "
            "Bug: PR #14 commit 980048d fixed this typo."
        )
        assert 'failed' in stats, "stats dict must contain 'failed' key"
        assert 'total' in stats, "stats dict must contain 'total' key"
        assert 'duration' in stats, "stats dict must contain 'duration' key"

        # Assert: Verify old incorrect key doesn't exist
        assert 'successful' not in stats, (
            "stats dict must NOT contain 'successful' key. "
            "This was a typo that caused '0/172 succeeded' false reporting. "
            "Fixed in PR #14 commit 980048d."
        )

        # Assert: Verify values are reasonable
        assert isinstance(stats['success'], int), "'success' must be an integer"
        assert isinstance(stats['failed'], int), "'failed' must be an integer"
        assert isinstance(stats['total'], int), "'total' must be an integer"
        assert isinstance(stats['duration'], (int, float)), "'duration' must be numeric"

        assert stats['success'] >= 0, "'success' count cannot be negative"
        assert stats['failed'] >= 0, "'failed' count cannot be negative"
        assert stats['total'] > 0, "'total' count must be positive (champions from Riot API)"
        assert stats['success'] + stats['failed'] == stats['total'], (
            "success + failed must equal total"
        )

    finally:
        # Cleanup
        parser.close()
        db.close()


def test_stats_dict_keys_documentation():
    """Document the expected stats dict structure for future developers.

    This test serves as living documentation of the ParallelParser contract.
    """
    expected_keys = {
        'success': 'Number of champions successfully scraped (int)',
        'failed': 'Number of champions that failed to scrape (int)',
        'total': 'Total number of champions attempted (int)',
        'duration': 'Time taken in seconds (float)',
    }

    forbidden_keys = {
        'successful': 'Typo that caused PR #14 bug - use "success" instead',
    }

    # This test always passes - it's just documentation
    assert expected_keys, "Stats dict must contain these keys"
    assert forbidden_keys, "Stats dict must NOT contain these keys"
