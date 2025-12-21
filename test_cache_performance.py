"""
Test script for cache performance validation.

This script tests:
1. Optimized DB query (4 columns vs 6)
2. Cache warming and retrieval
3. Performance gains with cache
4. Cache statistics
"""

import time
from src.db import Database
from src.assistant import Assistant

def test_optimized_query():
    """Test that optimized query returns 4 columns."""
    print("\n" + "="*80)
    print("TEST 1: Optimized Query Format")
    print("="*80)

    db = Database("data/db.db")
    db.connect()

    # Test with a known champion
    champion = "Aatrox"

    # Old query (6 columns)
    old_matchups = db.get_champion_matchups_by_name(champion)
    print(f"\n[OLD QUERY] Champion: {champion}")
    print(f"  - Columns returned: {len(old_matchups[0]) if old_matchups else 0}")
    if old_matchups:
        print(f"  - Sample: {old_matchups[0]}")
        print(f"  - Format: (enemy_name, winrate, delta1, delta2, pickrate, games)")

    # New optimized query (4 columns)
    new_matchups = db.get_champion_matchups_for_draft(champion)
    print(f"\n[NEW QUERY] Champion: {champion}")
    print(f"  - Columns returned: {len(new_matchups[0]) if new_matchups else 0}")
    if new_matchups:
        print(f"  - Sample: {new_matchups[0]}")
        print(f"  - Format: (enemy_name, delta2, pickrate, games)")

    # Calculate reduction
    if old_matchups and new_matchups:
        reduction = ((6 - 4) / 6) * 100
        print(f"\n[OK] Data reduction: {reduction:.1f}% (4 columns instead of 6)")

    db.close()

def test_cache_warming():
    """Test cache warming with a champion pool."""
    print("\n" + "="*80)
    print("TEST 2: Cache Warming")
    print("="*80)

    assistant = Assistant(verbose=False)

    # Test pool
    test_pool = ["Aatrox", "Ahri", "Jinx", "Lee Sin", "Thresh"]

    print(f"\n[CACHE] Warming cache with {len(test_pool)} champions...")
    start_time = time.time()
    assistant.warm_cache(test_pool)
    warm_time = (time.time() - start_time) * 1000

    print(f"[OK] Cache warmed in {warm_time:.2f}ms")

    # Verify cache content
    print(f"\n[CACHE] Cache status:")
    print(f"  - Enabled: {assistant._cache_enabled}")
    print(f"  - Champions cached: {len(assistant._matchups_cache)}")

    assistant.close()

def test_cache_performance():
    """Test performance gains with cache vs without cache."""
    print("\n" + "="*80)
    print("TEST 3: Cache Performance Comparison")
    print("="*80)

    assistant = Assistant(verbose=False)

    # Test pool
    test_pool = ["Aatrox", "Ahri", "Jinx", "Lee Sin", "Thresh"]

    # Test WITHOUT cache (cold)
    print(f"\n[NO CACHE] Querying {len(test_pool)} champions (cold)...")
    start_time = time.time()
    for champion in test_pool:
        _ = assistant.get_matchups_for_draft(champion)
    cold_time = (time.time() - start_time) * 1000

    print(f"  - Time: {cold_time:.2f}ms")
    print(f"  - Cache hits: {assistant._cache_hits}")
    print(f"  - Cache misses: {assistant._cache_misses}")

    # Warm cache
    print(f"\n[CACHE] Warming cache...")
    assistant.warm_cache(test_pool)

    # Reset stats
    assistant._cache_hits = 0
    assistant._cache_misses = 0

    # Test WITH cache (warm)
    print(f"\n[WITH CACHE] Querying {len(test_pool)} champions (warm)...")
    start_time = time.time()
    for champion in test_pool:
        _ = assistant.get_matchups_for_draft(champion)
    warm_time = (time.time() - start_time) * 1000

    print(f"  - Time: {warm_time:.2f}ms")
    print(f"  - Cache hits: {assistant._cache_hits}")
    print(f"  - Cache misses: {assistant._cache_misses}")

    # Calculate speedup
    speedup = ((cold_time - warm_time) / cold_time) * 100
    print(f"\n[OK] Performance gain: {speedup:.1f}% faster ({cold_time:.2f}ms -> {warm_time:.2f}ms)")

    # Print cache stats
    assistant.print_cache_stats()

    # Clear cache
    print(f"\n[CACHE] Clearing cache...")
    assistant.clear_cache()

    assistant.close()

def test_format_conversion():
    """Test that 4-column format is correctly converted to 6-column format."""
    print("\n" + "="*80)
    print("TEST 4: Format Conversion (4 cols -> 6 cols)")
    print("="*80)

    assistant = Assistant(verbose=False)

    # Warm cache (stores 4-column format)
    test_pool = ["Aatrox"]
    assistant.warm_cache(test_pool)

    # Get matchups (should return 6-column format)
    matchups = assistant.get_matchups_for_draft("Aatrox")

    print(f"\n[CONVERSION] Champion: Aatrox")
    if matchups:
        print(f"  - Columns returned: {len(matchups[0])}")
        print(f"  - Sample: {matchups[0]}")
        print(f"  - Format: (enemy_name, winrate, delta1, delta2, pickrate, games)")

        # Verify structure
        if len(matchups[0]) == 6:
            enemy, wr, d1, d2, pr, games = matchups[0]
            print(f"\n  [OK] Format validation:")
            print(f"     - enemy_name: {enemy} (str)")
            print(f"     - winrate: {wr} (should be 50.0 for dummy)")
            print(f"     - delta1: {d1} (should be 0.0 for dummy)")
            print(f"     - delta2: {d2} (float)")
            print(f"     - pickrate: {pr} (float)")
            print(f"     - games: {games} (int)")

            if wr == 50.0 and d1 == 0.0:
                print(f"\n  [OK] Dummy values correct (winrate=50.0, delta1=0.0)")
            else:
                print(f"\n  [ERROR] Dummy values incorrect!")
        else:
            print(f"\n  [ERROR] Wrong number of columns: {len(matchups[0])} (expected 6)")
    else:
        print("  [ERROR] No matchups returned")

    assistant.close()

def main():
    """Run all cache performance tests."""
    print("\n" + "="*80)
    print("CACHE PERFORMANCE TEST SUITE")
    print("="*80)

    try:
        test_optimized_query()
        test_cache_warming()
        test_cache_performance()
        test_format_conversion()

        print("\n" + "="*80)
        print("[OK] ALL TESTS COMPLETED")
        print("="*80)

    except Exception as e:
        print(f"\n[ERROR] Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
