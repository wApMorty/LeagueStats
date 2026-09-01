"""Bidirectional in-memory matchup cache (performance layer for draft analysis).

Extracted from src/assistant.py (SPEC-07 E10, lot 5) : déplacement verbatim,
aucun changement de comportement.
"""

from typing import Dict, List, Optional

from ..db import Database
from ..models import Matchup, MatchupDraft


class MatchupCache:
    """Direct + reverse in-memory cache of champion matchups.

    Direct cache: champion (as picker) -> [(enemy, delta2, ...)]
    Reverse cache: champion (as enemy) -> [(picker, delta2, ...)]
    """

    def __init__(self, db: Database) -> None:
        self.db = db
        self._matchups_cache: Dict[str, List[tuple]] = {}
        self._reverse_cache: Dict[str, List[tuple]] = {}
        self._cache_enabled = False
        self._cache_hits = 0  # Track cache hits for statistics
        self._cache_misses = 0  # Track cache misses for statistics

    def warm(self, champion_pool: List[str]) -> None:
        """
        Pre-load matchups for all champions in pool into cache (bidirectional).

        Loads BOTH:
        - Direct cache: champion as picker -> enemies
        - Reverse cache: champion as enemy -> pickers (for ban recommendations)

        Performance impact:
        - First call: ~20ms per champion (2x queries)
        - Reverse lookups: ~99% faster (0 SQL queries after warm-up)

        Args:
            champion_pool: List of champion names to cache matchups for
        """
        if not champion_pool:
            return

        print(f"[CACHE] Warming bidirectional cache for {len(champion_pool)} champions...")
        direct_cached = 0
        reverse_cached = 0

        for champion in champion_pool:
            # Direct cache: champion -> enemies
            matchups = self.db.get_champion_matchups_for_draft(champion)
            if matchups:
                self._matchups_cache[champion] = matchups
                direct_cached += 1

            # Reverse cache: champion as enemy -> pickers
            reverse_matchups = self.db.get_reverse_matchups_for_draft(champion)
            if reverse_matchups:
                self._reverse_cache[champion] = reverse_matchups
                reverse_cached += 1

        self._cache_enabled = True
        print(f"[CACHE] Direct cache: {direct_cached}/{len(champion_pool)} champions")
        print(f"[CACHE] Reverse cache: {reverse_cached}/{len(champion_pool)} champions")

    def clear(self) -> None:
        """
        Clear matchup caches (both direct and reverse) and disable caching.

        Should be called when exiting draft mode to free memory.
        """
        # Print statistics before clearing
        self.print_stats()

        direct_size = len(self._matchups_cache)
        reverse_size = len(self._reverse_cache)
        total_size = direct_size + reverse_size

        self._matchups_cache.clear()
        self._reverse_cache.clear()
        self._cache_enabled = False
        self._cache_hits = 0
        self._cache_misses = 0

        if total_size > 0:
            print(
                f"[CACHE] Cache cleared ({direct_size} direct + {reverse_size} reverse = {total_size} entries)"
            )

    def print_stats(self) -> None:
        """
        Print cache performance statistics (bidirectional cache).

        Shows stats for both direct and reverse cache.
        """
        total_queries = self._cache_hits + self._cache_misses
        if total_queries == 0:
            return

        hit_rate = (self._cache_hits / total_queries) * 100 if total_queries > 0 else 0
        direct_count = len(self._matchups_cache)
        reverse_count = len(self._reverse_cache)

        print(f"\n[CACHE] Performance Statistics:")
        print(f"  - Total queries: {total_queries}")
        print(f"  - Cache hits: {self._cache_hits} ({hit_rate:.1f}%)")
        print(f"  - Cache misses: {self._cache_misses}")
        print(f"  - Direct cache entries: {direct_count} champions")
        print(f"  - Reverse cache entries: {reverse_count} champions")
        print(f"  - Total cached: {direct_count + reverse_count} entries")

        # Estimated performance gain
        if self._cache_hits > 0:
            time_saved_ms = self._cache_hits * 10  # ~10ms per avoided SQL query
            print(f"  - Estimated time saved: ~{time_saved_ms}ms ({time_saved_ms/1000:.2f}s)")

    def get_matchups(self, champion: str) -> List[tuple]:
        """
        Get matchups from cache if available, otherwise fetch from database.

        Returns matchups in optimized format for draft:
        [(enemy_name, delta2, pickrate, games), ...]

        Args:
            champion: Champion name to get matchups for

        Returns:
            List of matchup tuples (4 elements for draft vs 6 for standard query)
        """
        # If cache is enabled and champion is in cache, use it
        if self._cache_enabled and champion in self._matchups_cache:
            self._cache_hits += 1
            return self._matchups_cache[champion]

        # Otherwise fall back to database (optimized query)
        self._cache_misses += 1
        return self.db.get_champion_matchups_for_draft(champion)

    def get_delta2(self, champion: str, enemy: str) -> Optional[float]:
        """
        Get delta2 for a specific matchup using bidirectional cache.

        Tries BOTH cache directions before falling back to SQL:
        1. Direct cache: champion -> enemy
        2. Reverse cache: enemy -> champion (inverted delta2)

        Performance:
        - Cache hit: ~0.01ms (instant lookup)
        - Cache miss: ~10ms (SQL fallback via db.get_matchup_delta2)

        Args:
            champion: Our champion name
            enemy: Enemy champion name

        Returns:
            Delta2 value if matchup found, None otherwise
        """
        # Try direct cache: champion -> enemy
        if self._cache_enabled and champion in self._matchups_cache:
            for matchup in self._matchups_cache[champion]:
                if matchup[0] == enemy:  # matchup[0] is enemy_name
                    self._cache_hits += 1
                    return matchup[1]  # matchup[1] is delta2

        # Try reverse cache: enemy -> champion (invert delta2)
        if self._cache_enabled and enemy in self._reverse_cache:
            for matchup in self._reverse_cache[enemy]:
                # In reverse cache, matchup[0] is the "picker" (our champion)
                if matchup[0] == champion:
                    self._cache_hits += 1
                    # Invert delta2: if Jax vs Darius = +3, then Darius vs Jax = -3
                    return -matchup[1]  # matchup[1] is delta2

        # Cache miss - fallback to SQL
        self._cache_misses += 1
        return self.db.get_matchup_delta2(champion, enemy)

    def get_matchups_for_draft(self, champion: str) -> List[Matchup]:
        """
        Get matchups for draft analysis (optimized with cache support).

        This method:
        1. Uses cache if enabled (99% faster after warm-up)
        2. Falls back to optimized DB query if cache miss
        3. Returns Matchup objects for compatibility with scoring methods

        Args:
            champion: Champion name to get matchups for

        Returns:
            List of Matchup objects with complete statistics
        """
        # Get from cache or DB (optimized 4-column format)
        draft_matchups = self.get_matchups(champion)

        # Convert to Matchup objects for scoring methods
        return self._convert_draft_matchups_to_standard(draft_matchups)

    def _convert_draft_matchups_to_standard(self, draft_matchups: List) -> List[Matchup]:
        """
        Convert draft format (4 cols) to Matchup objects for scoring methods.

        Draft format: MatchupDraft(enemy_name, delta2, pickrate, games)
        Standard format: Matchup(enemy_name, winrate, delta1, delta2, pickrate, games)

        Since winrate and delta1 are not used in draft calculations, we fill with dummy values:
        - winrate = 50.0 (neutral)
        - delta1 = 0.0 (neutral)

        Args:
            draft_matchups: List of MatchupDraft objects or tuples (4 elements)

        Returns:
            List of Matchup objects
        """
        standard_matchups = []
        for matchup in draft_matchups:
            if isinstance(matchup, MatchupDraft):
                # MatchupDraft object - use built-in to_matchup() method
                standard_matchups.append(matchup.to_matchup())
            elif isinstance(matchup, tuple) and len(matchup) == 4:
                # Draft format tuple: (enemy_name, delta2, pickrate, games)
                enemy_name, delta2, pickrate, games = matchup
                # Convert to Matchup object
                standard_matchup = Matchup(enemy_name, 50.0, 0.0, delta2, pickrate, games)
                standard_matchups.append(standard_matchup)
            elif isinstance(matchup, Matchup):
                # Already a Matchup object - pass through
                standard_matchups.append(matchup)
            elif isinstance(matchup, tuple) and len(matchup) == 6:
                # Legacy 6-tuple format - convert to Matchup
                standard_matchups.append(Matchup.from_tuple(matchup))
            else:
                # Unknown format - try to pass through
                standard_matchups.append(matchup)

        return standard_matchups
