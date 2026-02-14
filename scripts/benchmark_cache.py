"""
Benchmark script for bidirectional cache performance.

Measures performance improvements from adding reverse cache:
- warm_cache() overhead (direct only vs bidirectional)
- Ban recommendations speedup (reverse lookup optimization)
- Cache hit rates (direct vs reverse)
- Memory usage impact

This benchmark validates the Tâche #8 implementation:
- Objective: Measure >90% cache hit rate for ban recommendations
- Expected: 10-50x speedup vs SQL-only approach

USAGE:
    python scripts/benchmark_cache.py

Author: @pj35 - LeagueStats Coach
Version: 1.1.0-dev
"""

import sys
import time
from pathlib import Path

# Set UTF-8 encoding for console output
if sys.platform == "win32":
    import codecs

    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "backslashreplace")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "backslashreplace")

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.assistant import Assistant
from src.sqlite_data_source import SQLiteDataSource
from src.config import config


def benchmark_warm_cache(assistant: Assistant, champion_pool: list) -> float:
    """
    Measure warm_cache() time.

    Args:
        assistant: Assistant instance with cleared cache
        champion_pool: List of champion names to cache

    Returns:
        Time taken in milliseconds
    """
    start = time.perf_counter()
    assistant.warm_cache(champion_pool)
    end = time.perf_counter()
    return (end - start) * 1000  # Convert to ms


def benchmark_ban_recommendations(assistant: Assistant, champion_pool: list) -> tuple:
    """
    Measure ban recommendations time (uses reverse lookups heavily).

    Args:
        assistant: Assistant instance with warmed cache
        champion_pool: List of champion names in draft

    Returns:
        Tuple of (time_ms, cache_hits, cache_misses)
    """
    # Reset cache stats
    assistant._cache_hits = 0
    assistant._cache_misses = 0

    start = time.perf_counter()
    bans = assistant.get_ban_recommendations(champion_pool, num_bans=5)
    end = time.perf_counter()

    time_ms = (end - start) * 1000
    hits = assistant._cache_hits
    misses = assistant._cache_misses

    return time_ms, hits, misses


def benchmark_cache_memory(assistant: Assistant) -> dict:
    """
    Estimate cache memory usage (rough approximation).

    Args:
        assistant: Assistant instance with warmed cache

    Returns:
        Dict with direct_kb, reverse_kb, total_kb
    """
    import sys

    # Get dict sizes
    direct_size = sys.getsizeof(assistant._matchups_cache)
    reverse_size = sys.getsizeof(assistant._reverse_cache)

    # Add size of cached data (rough estimate)
    for champ, matchups in assistant._matchups_cache.items():
        direct_size += sys.getsizeof(champ)
        direct_size += sys.getsizeof(matchups)
        for matchup in matchups:
            direct_size += sys.getsizeof(matchup)

    for champ, matchups in assistant._reverse_cache.items():
        reverse_size += sys.getsizeof(champ)
        reverse_size += sys.getsizeof(matchups)
        for matchup in matchups:
            reverse_size += sys.getsizeof(matchup)

    total_size = direct_size + reverse_size

    return {
        "direct_kb": direct_size / 1024,
        "reverse_kb": reverse_size / 1024,
        "total_kb": total_size / 1024,
    }


def main():
    """Run comprehensive cache benchmark."""
    print("=" * 70)
    print("BENCHMARK: Bidirectional Cache Performance")
    print("=" * 70)
    print()

    # Initialize assistant with SQLite data source (local database)
    print("[1/5] Initializing assistant...")
    data_source = SQLiteDataSource(config.DATABASE_PATH)
    data_source.connect()
    assistant = Assistant(data_source=data_source, verbose=False)

    # Test pool (realistic size: 20 top lane champions)
    champion_pool = [
        "Darius",
        "Garen",
        "Jax",
        "Fiora",
        "Camille",
        "Renekton",
        "Sett",
        "Mordekaiser",
        "Aatrox",
        "Ornn",
        "Malphite",
        "Shen",
        "Cho'Gath",
        "Maokai",
        "Poppy",
        "Irelia",
        "Riven",
        "Yasuo",
        "Yone",
        "Kled",
    ]

    print(f"Test pool: {len(champion_pool)} champions")
    print()

    # Benchmark 1: warm_cache() time
    print("[2/5] Benchmarking warm_cache()...")
    warm_time = benchmark_warm_cache(assistant, champion_pool)
    print(f"  ⏱️  warm_cache() time: {warm_time:.2f}ms")
    print(f"  📊 Champions cached (direct): {len(assistant._matchups_cache)}")
    print(f"  📊 Champions cached (reverse): {len(assistant._reverse_cache)}")
    print()

    # Benchmark 2: Ban recommendations (uses reverse lookups)
    print("[3/5] Benchmarking ban recommendations (reverse lookups)...")
    ban_time, hits, misses = benchmark_ban_recommendations(assistant, champion_pool)
    total_queries = hits + misses
    hit_rate = (hits / total_queries * 100) if total_queries > 0 else 0

    print(f"  ⏱️  Ban recommendations time: {ban_time:.2f}ms")
    print(f"  📈 Cache hits: {hits} ({hit_rate:.1f}%)")
    print(f"  📉 Cache misses: {misses}")
    print(f"  🎯 Total queries: {total_queries}")
    print()

    # Benchmark 3: Cache stats
    print("[4/5] Cache statistics...")
    assistant.print_cache_stats()
    print()

    # Benchmark 4: Memory usage
    print("[5/5] Memory usage...")
    memory = benchmark_cache_memory(assistant)
    print(f"  💾 Direct cache: {memory['direct_kb']:.2f} KB")
    print(f"  💾 Reverse cache: {memory['reverse_kb']:.2f} KB")
    print(f"  💾 Total cache: {memory['total_kb']:.2f} KB")
    print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"✅ Cache warmed in {warm_time:.2f}ms")
    print(f"✅ Ban recommendations: {ban_time:.2f}ms with {hit_rate:.1f}% cache hit rate")
    print(f"✅ Memory overhead: {memory['total_kb']:.2f} KB (~{memory['total_kb']/1024:.2f} MB)")

    # Estimated improvement (compared to SQL queries)
    if misses > 0 or hits > 0:
        estimated_sql_time = total_queries * 10  # ~10ms per SQL query
        if ban_time > 0:
            speedup = estimated_sql_time / ban_time
            print(f"⚡ Estimated speedup vs SQL-only: {speedup:.1f}x faster")
            print(f"   (Avoided ~{hits} SQL queries = ~{hits*10}ms saved)")
        else:
            print("⚡ Ban recommendations completed too fast to measure speedup")

    print()
    print("🎉 Benchmark completed successfully!")

    # Cleanup
    assistant.clear_cache()
    data_source.close()


if __name__ == "__main__":
    main()
