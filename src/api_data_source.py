"""
API Data Source implementation - HTTP client for FastAPI backend.

This module provides an adapter that fetches champion statistics from a remote
FastAPI backend instead of local SQLite database. It includes:
- HTTP client with retry logic (exponential backoff)
- Intelligent caching for bulk endpoints
- Timeout handling
- Error logging

Design Pattern: Adapter Pattern (Remote Proxy)
- Wraps httpx HTTP client
- Maps DataSource methods to API endpoints
- Caches bulk data for performance
- Graceful error handling

Author: @pj35
Created: 2026-02-06
Sprint: 2 - API Integration (Adapter Pattern Implementation)
"""

import logging
from typing import List, Optional, Dict, Union, Tuple

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .data_source import DataSource
from .config_constants import api_config
from .models import Matchup, MatchupDraft, Synergy

# Configure logging
logger = logging.getLogger(__name__)


class APIDataSource(DataSource):
    """
    Adapter for remote API access via FastAPI backend.

    This data source fetches champion statistics from a remote HTTP API instead
    of a local database. It includes retry logic, caching, and timeout handling
    for robust network operations.

    Attributes:
        _base_url: Base URL of FastAPI backend
        _timeout: Request timeout in seconds
        _client: httpx.Client for synchronous requests
        _matchups_cache: In-memory cache for bulk matchups
        _synergies_cache: In-memory cache for bulk synergies
        _champion_cache: In-memory cache for champion name->ID mappings

    Example:
        >>> data_source = APIDataSource()
        >>> data_source.connect()  # Warmup cache
        >>> champion_id = data_source.get_champion_id("Jinx")
        >>> data_source.close()
    """

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[int] = None) -> None:
        """
        Initialize API data source.

        Args:
            base_url: Base URL of FastAPI backend (default: from api_config)
            timeout: Request timeout in seconds (default: from api_config)
        """
        self._base_url = base_url or api_config.BASE_URL
        self._timeout = timeout or api_config.TIMEOUT
        self._client = None

        # In-memory caches (loaded on connect)
        self._matchups_cache: Dict[Tuple[str, str], float] = {}
        self._synergies_cache: Dict[Tuple[str, str], float] = {}
        self._champion_cache: Dict[str, int] = {}
        self._champion_names_cache: Dict[int, str] = {}

    # ==================== Connection Management ====================

    def connect(self) -> None:
        """
        Establish HTTP client and warm up caches.

        Loads bulk endpoints (champions, matchups, synergies) into memory
        for fast lookups during runtime.
        """
        self._client = httpx.Client(base_url=self._base_url, timeout=self._timeout)
        logger.info(f"[API] Connected to {self._base_url}")

        # Warm up caches with bulk endpoints
        try:
            self._warm_up_caches()
        except Exception as e:
            logger.warning(f"[API] Cache warmup failed (non-critical): {e}")

    def close(self) -> None:
        """Close HTTP client connection."""
        if self._client is not None:
            self._client.close()
            logger.info("[API] Connection closed")

    def _warm_up_caches(self) -> None:
        """
        Pre-load bulk data into memory caches for performance.

        This method is called on connect() to populate:
        - Champion name -> ID mappings
        - All matchups (champion, enemy) -> delta2
        - All synergies (champion, ally) -> delta2
        """
        logger.info("[API] Warming up caches...")

        # Load champion cache
        self._champion_cache = self.build_champion_cache()
        logger.info(f"[API] Cached {len(self._champion_cache)} champion mappings")

        # Load matchups bulk
        self._matchups_cache = self.get_all_matchups_bulk()
        logger.info(f"[API] Cached {len(self._matchups_cache)} matchups")

        # Load synergies bulk
        self._synergies_cache = self.get_all_synergies_bulk()
        logger.info(f"[API] Cached {len(self._synergies_cache)} synergies")

    @retry(
        stop=stop_after_attempt(api_config.RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=api_config.RETRY_BACKOFF, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=True,
    )
    def _get(self, endpoint: str, **params) -> httpx.Response:
        """
        Make HTTP GET request with retry logic.

        Args:
            endpoint: API endpoint (e.g., "/api/champions")
            **params: Query parameters

        Returns:
            httpx.Response object

        Raises:
            httpx.HTTPError: On HTTP errors after retries exhausted
        """
        response = self._client.get(endpoint, params=params)
        response.raise_for_status()  # Raise on 4xx/5xx
        return response

    # ==================== Champion Queries ====================

    def get_champion_id(self, champion: str) -> Optional[int]:
        """Get champion ID by name (uses cache)."""
        # Try cache first (case-insensitive)
        champion_id = self._champion_cache.get(champion) or self._champion_cache.get(
            champion.lower()
        )
        if champion_id is not None:
            return champion_id

        # Fallback: Query API (no name filtering on API side, filter client-side)
        try:
            response = self._get("/api/champions")
            data = response.json()
            champions = data.get("champions", [])  # Extract wrapped list

            # Filter by name (case-insensitive)
            matching = [c for c in champions if c["name"].lower() == champion.lower()]
            if matching:
                return matching[0]["id"]
            return None
        except Exception as e:
            logger.error(f"[API] Error getting champion ID for {champion}: {e}")
            raise

    def get_champion_by_id(self, id: int) -> Optional[str]:
        """Get champion name by ID (uses cache)."""
        # Try cache first
        if id in self._champion_names_cache:
            return self._champion_names_cache[id]

        # Fallback: Query API
        try:
            response = self._get(f"/api/champions/{id}")
            data = response.json()
            return data.get("name")
        except Exception as e:
            logger.error(f"[API] Error getting champion by ID {id}: {e}")
            raise

    def get_all_champion_names(self) -> Dict[int, str]:
        """Get mapping of all champion IDs to names."""
        try:
            response = self._get("/api/champions")
            data = response.json()
            champions = data.get("champions", [])  # Extract wrapped list
            mapping = {champ["id"]: champ["name"] for champ in champions}
            self._champion_names_cache = mapping  # Update cache
            return mapping
        except Exception as e:
            logger.error(f"[API] Error getting all champion names: {e}")
            raise

    def build_champion_cache(self) -> Dict[str, int]:
        """Build cache of champion name -> ID mappings."""
        try:
            response = self._get("/api/champions")
            data = response.json()
            champions = data.get("champions", [])  # Extract wrapped list
            cache = {}
            for champ in champions:
                name = champ["name"]
                champ_id = champ["id"]
                # Add official name (exact case)
                cache[name] = champ_id
                # Add lowercase version for flexible matching
                cache[name.lower()] = champ_id
            return cache
        except Exception as e:
            logger.error(f"[API] Error building champion cache: {e}")
            raise

    # ==================== Matchup Queries ====================

    def get_champion_matchups_by_name(
        self, champion_name: str, as_dataclass: bool = True
    ) -> Union[List[Matchup], List[tuple]]:
        """Get matchups for a champion by name."""
        champion_id = self.get_champion_id(champion_name)
        if champion_id is None:
            return []

        try:
            response = self._get(f"/api/champions/{champion_id}/matchups")
            data = response.json()
            matchups = data.get("matchups", [])  # Extract wrapped list

            if as_dataclass:
                return [
                    Matchup(
                        enemy_name=m["enemy_name"],
                        winrate=m["winrate"],
                        delta1=m["delta1"],
                        delta2=m["delta2"],
                        pickrate=m["pickrate"],
                        games=m["games"],
                    )
                    for m in matchups
                ]
            else:
                return [
                    (
                        m["enemy_name"],
                        m["winrate"],
                        m["delta1"],
                        m["delta2"],
                        m["pickrate"],
                        m["games"],
                    )
                    for m in matchups
                ]
        except Exception as e:
            logger.error(f"[API] Error getting matchups for {champion_name}: {e}")
            raise

    def get_champion_matchups_for_draft(
        self, champion_name: str, as_dataclass: bool = True
    ) -> Union[List[MatchupDraft], List[tuple]]:
        """Get optimized matchups for draft analysis (4 columns)."""
        champion_id = self.get_champion_id(champion_name)
        if champion_id is None:
            return []

        try:
            # Use same endpoint but only extract needed fields
            response = self._get(f"/api/champions/{champion_id}/matchups")
            data = response.json()
            matchups = data.get("matchups", [])  # Extract wrapped list

            if as_dataclass:
                return [
                    MatchupDraft(
                        enemy_name=m["enemy_name"],
                        delta2=m["delta2"],
                        pickrate=m["pickrate"],
                        games=m["games"],
                    )
                    for m in matchups
                ]
            else:
                return [(m["enemy_name"], m["delta2"], m["pickrate"], m["games"]) for m in matchups]
        except Exception as e:
            logger.error(f"[API] Error getting draft matchups for {champion_name}: {e}")
            raise

    def get_matchup_delta2(self, champion_name: str, enemy_name: str) -> Optional[float]:
        """Get delta2 value for specific matchup (uses cache)."""
        # Check cache first (case-insensitive)
        key = (champion_name.lower(), enemy_name.lower())
        if key in self._matchups_cache:
            return self._matchups_cache[key]

        # Fallback: Query API
        champion_id = self.get_champion_id(champion_name)
        enemy_id = self.get_champion_id(enemy_name)

        if champion_id is None or enemy_id is None:
            return None

        try:
            response = self._get(
                f"/api/matchups/delta2", champion_id=champion_id, enemy_id=enemy_id
            )
            data = response.json()
            return data.get("delta2")
        except Exception as e:
            logger.error(f"[API] Error getting matchup delta2 {champion_name} vs {enemy_name}: {e}")
            raise

    def get_all_matchups_bulk(self) -> Dict[Tuple[str, str], float]:
        """Load ALL valid matchups in single query for caching."""
        try:
            response = self._get("/api/matchups/bulk")
            data = response.json()
            matchups_dict = data.get(
                "matchups", {}
            )  # Extract wrapped dict {champion_id: [matchups]}

            cache = {}
            # Build reverse lookup from champion ID to name using existing cache
            id_to_name = {v: k for k, v in self._champion_cache.items() if k == k.capitalize()}

            # Iterate over all champions' matchups
            for champion_id_str, matchups_list in matchups_dict.items():
                champion_id = int(champion_id_str)
                champion_name = id_to_name.get(champion_id, "")

                if not champion_name:
                    # Skip if champion not in cache (shouldn't happen)
                    logger.warning(f"[API] Champion ID {champion_id} not found in cache")
                    continue

                for matchup in matchups_list:
                    enemy_name = matchup["enemy_name"]
                    delta2 = matchup["delta2"]
                    # Normalize to lowercase for case-insensitive lookup
                    key = (champion_name.lower(), enemy_name.lower())
                    cache[key] = float(delta2)

            return cache
        except Exception as e:
            logger.error(f"[API] Error loading bulk matchups: {e}")
            raise

    def get_champion_base_winrate(self, champion_name: str) -> float:
        """Calculate champion base winrate (weighted average of matchups)."""
        matchups = self.get_champion_matchups_by_name(champion_name, as_dataclass=True)
        if not matchups:
            return 50.0  # Default

        total_weighted_winrate = 0.0
        total_weight = 0.0

        for matchup in matchups:
            weight = matchup.games
            total_weighted_winrate += matchup.winrate * weight
            total_weight += weight

        if total_weight == 0:
            return 50.0

        return total_weighted_winrate / total_weight

    # ==================== Synergy Queries ====================

    def get_champion_synergies_by_name(
        self, champion_name: str, as_dataclass: bool = True
    ) -> Union[List[Synergy], List[tuple]]:
        """Get synergies for a champion by name."""
        champion_id = self.get_champion_id(champion_name)
        if champion_id is None:
            return []

        try:
            response = self._get(f"/api/champions/{champion_id}/synergies")
            data = response.json()
            synergies = data.get("synergies", [])  # Extract wrapped list

            if as_dataclass:
                return [
                    Synergy(
                        ally_name=s["ally_name"],
                        winrate=s["winrate"],
                        delta1=s.get("delta1", 0.0),  # delta1 might be missing in SynergyResponse
                        delta2=s["delta2"],
                        pickrate=s["pickrate"],
                        games=s["games"],
                    )
                    for s in synergies
                ]
            else:
                return [
                    (
                        s["ally_name"],
                        s["winrate"],
                        s.get("delta1", 0.0),
                        s["delta2"],
                        s["pickrate"],
                        s["games"],
                    )
                    for s in synergies
                ]
        except Exception as e:
            logger.error(f"[API] Error getting synergies for {champion_name}: {e}")
            raise

    def get_synergy_delta2(self, champion_name: str, ally_name: str) -> Optional[float]:
        """Get delta2 value for specific synergy (uses cache)."""
        # Check cache first (case-insensitive)
        key = (champion_name.lower(), ally_name.lower())
        if key in self._synergies_cache:
            return self._synergies_cache[key]

        # Fallback: Query API
        champion_id = self.get_champion_id(champion_name)
        ally_id = self.get_champion_id(ally_name)

        if champion_id is None or ally_id is None:
            return None

        try:
            response = self._get(f"/api/synergies/delta2", champion_id=champion_id, ally_id=ally_id)
            data = response.json()
            return data.get("delta2")
        except Exception as e:
            logger.error(
                f"[API] Error getting synergy delta2 {champion_name} with {ally_name}: {e}"
            )
            raise

    def get_all_synergies_bulk(self) -> Dict[Tuple[str, str], float]:
        """Load ALL valid synergies in single query for caching."""
        try:
            response = self._get("/api/synergies/bulk")
            data = response.json()
            synergies_dict = data.get(
                "synergies", {}
            )  # Extract wrapped dict {champion_id: [synergies]}

            cache = {}
            # Build reverse lookup from champion ID to name using existing cache
            id_to_name = {v: k for k, v in self._champion_cache.items() if k == k.capitalize()}

            # Iterate over all champions' synergies
            for champion_id_str, synergies_list in synergies_dict.items():
                champion_id = int(champion_id_str)
                champion_name = id_to_name.get(champion_id, "")

                if not champion_name:
                    # Skip if champion not in cache (shouldn't happen)
                    logger.warning(f"[API] Champion ID {champion_id} not found in cache")
                    continue

                for synergy in synergies_list:
                    ally_name = synergy["ally_name"]
                    delta2 = synergy["delta2"]
                    # Normalize to lowercase for case-insensitive lookup
                    key = (champion_name.lower(), ally_name.lower())
                    cache[key] = float(delta2)

            return cache
        except Exception as e:
            logger.error(f"[API] Error loading bulk synergies: {e}")
            raise

    # ==================== Champion Scores ====================

    def get_champion_scores_by_name(self, champion_name: str) -> Optional[Dict[str, float]]:
        """Get champion scores by champion name."""
        champion_id = self.get_champion_id(champion_name)
        if champion_id is None:
            return None

        try:
            response = self._get(f"/api/champions/{champion_id}/scores")
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None  # Champion has no scores
            logger.error(f"[API] Error getting scores for {champion_name}: {e}")
            raise
        except Exception as e:
            logger.error(f"[API] Error getting scores for {champion_name}: {e}")
            raise

    def get_all_champion_scores(self) -> List[tuple]:
        """Get all champion scores with champion names."""
        try:
            response = self._get("/api/champion-scores")
            scores = response.json()

            return [
                (
                    s["champion_name"],
                    s["avg_delta2"],
                    s["variance"],
                    s["coverage"],
                    s["peak_impact"],
                    s["volatility"],
                    s["target_ratio"],
                )
                for s in scores
            ]
        except Exception as e:
            logger.error(f"[API] Error getting all champion scores: {e}")
            raise

    def champion_scores_table_exists(self) -> bool:
        """Check if champion_scores data exists."""
        try:
            response = self._get("/api/champion-scores")
            scores = response.json()
            return len(scores) > 0
        except Exception:
            return False

    # ==================== Ban Recommendations ====================

    def get_pool_ban_recommendations(self, pool_name: str, limit: int = 5) -> List[tuple]:
        """Get pre-calculated ban recommendations for a champion pool."""
        try:
            response = self._get(f"/api/pools/{pool_name}/ban-recommendations", limit=limit)
            bans = response.json()

            return [
                (
                    b["enemy_champion"],
                    b["threat_score"],
                    b["best_response_delta2"],
                    b["best_response_champion"],
                    b["matchups_count"],
                )
                for b in bans
            ]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []  # Pool has no recommendations
            logger.error(f"[API] Error getting ban recommendations for {pool_name}: {e}")
            raise
        except Exception as e:
            logger.error(f"[API] Error getting ban recommendations for {pool_name}: {e}")
            raise

    def pool_has_ban_recommendations(self, pool_name: str) -> bool:
        """Check if a pool has pre-calculated ban recommendations."""
        bans = self.get_pool_ban_recommendations(pool_name, limit=1)
        return len(bans) > 0
