"""Parallel web scraping for champion matchup data.

This module provides high-performance parallel scraping capabilities using
ThreadPoolExecutor to dramatically reduce data collection time.

Performance:
    Sequential scraping: 30-60 minutes for 171 champions
    Parallel scraping: 6-8 minutes (80% improvement)

Features:
    - ThreadPoolExecutor with configurable worker count
    - Automatic retry with exponential backoff (tenacity)
    - Thread-safe database writes
    - Progress tracking with tqdm
    - Graceful error handling and logging

Usage:
    from src.parallel_parser import ParallelParser
    from src.db import Database

    db = Database("data/db.db")
    parallel_parser = ParallelParser(max_workers=10)

    try:
        parallel_parser.parse_all_champions(db, champion_list)
    finally:
        parallel_parser.close()
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, local, current_thread
from time import sleep
from typing import List, Optional, Tuple
import logging
import threading
import sys

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from tqdm import tqdm
from selenium.common.exceptions import WebDriverException, TimeoutException

from .parser import Parser
from .db import Database
from .config_constants import scraping_config

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(threadName)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Thread-local storage for parser instances (one parser per thread)
thread_local = local()


def _is_headless_mode() -> bool:
    """
    Detect if running in headless mode (pythonw.exe, Task Scheduler, etc.).

    In headless mode, sys.stdout is None, so tqdm progress bars should be disabled
    to avoid crashes.

    Returns:
        True if stdout is not available (headless mode), False otherwise
    """
    return sys.stdout is None or not hasattr(sys.stdout, "write")


class ParallelParser:
    """High-performance parallel web scraper for champion matchup data.

    Attributes:
        max_workers (int): Number of concurrent scraping threads
        parsers (List[Parser]): Pool of Parser instances (one per thread)
        db_lock (Lock): Thread-safe lock for database writes
        executor (ThreadPoolExecutor): Thread pool for parallel execution
    """

    def __init__(self, max_workers: int = 10, patch_version: str = None, headless: bool = False):
        """Initialize parallel parser with worker pool.

        Args:
            max_workers: Number of concurrent threads (default: 10)
                        Recommended range: 8-12 for optimal I/O performance
            patch_version: Optional patch version (e.g. "15.24"). If None, uses config.CURRENT_PATCH
            headless: If True, run Firefox in headless mode (no GUI).
                     Essential for Task Scheduler, pythonw.exe, or CI/CD.
                     Default: False (normal GUI mode).
        """
        from .config import config

        self.max_workers = max_workers
        self.patch_version = patch_version or config.CURRENT_PATCH
        self.headless = headless
        self.parsers: List[Parser] = []
        self.db_lock = Lock()
        self.executor: Optional[ThreadPoolExecutor] = None

        logger.info(
            f"ParallelParser initialized with {max_workers} workers, patch={self.patch_version}, headless={headless}"
        )

    def _get_parser(self) -> Parser:
        """Get or create a Parser instance for current thread.

        Uses thread-local storage to ensure ONE parser per thread, not per champion.
        This prevents creating multiple Firefox windows per thread.

        Returns:
            Parser: Thread-local parser instance with dedicated webdriver
        """
        # Check if this thread already has a parser
        if not hasattr(thread_local, "parser"):
            # Create new parser for this thread (first time only)
            thread_local.parser = Parser(headless=self.headless)
            self.parsers.append(thread_local.parser)
            logger.info(
                f"Created new parser for {threading.current_thread().name} (headless={self.headless})"
            )

        return thread_local.parser

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((WebDriverException, TimeoutException)),
        reraise=True,
    )
    def _scrape_champion_with_retry(
        self, champion: str, normalize_func
    ) -> List[Tuple[str, float, float, float, float, int]]:
        """Scrape champion data with automatic retry on failure.

        Uses exponential backoff: 2s, 4s, 8s (max 10s) between retries.
        Retries up to 3 times on WebDriverException or TimeoutException.

        Args:
            champion: Champion name to scrape
            normalize_func: Function to normalize champion name for URL

        Returns:
            List of matchup tuples: (enemy, winrate, delta1, delta2, pickrate, games)

        Raises:
            WebDriverException: After 3 failed attempts
            TimeoutException: After 3 failed attempts
        """
        parser = self._get_parser()

        try:
            normalized_champion = normalize_func(champion)
            matchups = parser.get_champion_data_on_patch(self.patch_version, normalized_champion)
            logger.info(
                f"Successfully scraped {champion} (patch {self.patch_version}): {len(matchups)} matchups"
            )
            return champion, matchups
        except (WebDriverException, TimeoutException) as e:
            logger.warning(f"Retry triggered for {champion}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error scraping {champion}: {e}")
            return champion, []

    def _write_matchups_thread_safe(
        self, db: Database, champion: str, matchups: List[Tuple]
    ) -> None:
        """Write matchup data to database with thread-safe locking.

        Args:
            db: Database instance
            champion: Champion name
            matchups: List of matchup tuples
        """
        with self.db_lock:
            try:
                for matchup in matchups:
                    enemy, winrate, d1, d2, pick, games = matchup
                    db.add_matchup(champion, enemy, winrate, d1, d2, pick, games)
            except Exception as e:
                logger.error(f"Database write error for {champion}: {e}")

    def _scrape_champion_synergies_with_retry(
        self, champion: str, normalize_func
    ) -> List[Tuple[str, float, float, float, float, int]]:
        """Scrape champion synergies with automatic retry on failure.

        Uses exponential backoff: 2s, 4s, 8s (max 10s) between retries.
        Retries up to 3 times on WebDriverException or TimeoutException.

        Args:
            champion: Champion name to scrape
            normalize_func: Function to normalize champion name for URL

        Returns:
            List of synergy tuples: (ally, winrate, delta1, delta2, pickrate, games)

        Raises:
            WebDriverException: After 3 failed attempts
            TimeoutException: After 3 failed attempts
        """
        parser = self._get_parser()

        try:
            normalized_champion = normalize_func(champion)
            synergies = parser.get_champion_synergies_on_patch(
                self.patch_version, normalized_champion
            )
            logger.info(
                f"Successfully scraped synergies for {champion} (patch {self.patch_version}): {len(synergies)} allies"
            )
            return champion, synergies
        except (WebDriverException, TimeoutException) as e:
            logger.warning(f"Retry triggered for {champion} synergies: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error scraping {champion} synergies: {e}")
            return champion, []

    def _write_synergies_thread_safe(
        self, db: Database, champion: str, synergies: List[Tuple]
    ) -> None:
        """Write synergy data to database with thread-safe locking.

        Args:
            db: Database instance
            champion: Champion name
            synergies: List of synergy tuples (ally, winrate, delta1, delta2, pickrate, games)
        """
        with self.db_lock:
            try:
                for synergy in synergies:
                    ally, winrate, d1, d2, pick, games = synergy
                    db.add_synergy(champion, ally, winrate, d1, d2, pick, games)
            except Exception as e:
                logger.error(f"Database write error for {champion} synergies: {e}")

    def parse_all_synergies(self, db: Database, normalize_func) -> dict:
        """Parse all champion synergies in parallel with progress tracking.

        Similar to parse_all_champions() but parses synergies (WITH allies)
        instead of matchups (AGAINST enemies).

        Args:
            db: Database instance (must be connected)
            normalize_func: Function to normalize champion names for URLs

        Returns:
            dict: Statistics with keys 'success', 'failed', 'total', 'duration'

        Example:
            >>> from src.parallel_parser import ParallelParser
            >>> from src.db import Database
            >>> from src.parser import normalize_champion_name_for_url
            >>> db = Database("data/db.db")
            >>> db.connect()
            >>> parser = ParallelParser(max_workers=10)
            >>> stats = parser.parse_all_synergies(db, normalize_champion_name_for_url)
            >>> print(f"{stats['success']}/{stats['total']} champions parsed")
        """
        import time

        start_time = time.time()

        # Initialize synergies table (drop + recreate with indexes)
        db.init_synergies_table()

        # Get champion list from database (populated by Riot API)
        champion_names = list(db.get_all_champion_names().values())
        logger.info(f"Starting parallel scraping of synergies for {len(champion_names)} champions")

        # Create thread pool and submit tasks
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        futures = {
            self.executor.submit(
                self._scrape_champion_synergies_with_retry, champion, normalize_func
            ): champion
            for champion in champion_names
        }

        # Track progress with tqdm
        success_count = 0
        failed_count = 0
        total_champions = len(champion_names)

        # Disable tqdm in headless mode (pythonw.exe, Task Scheduler)
        disable_tqdm = _is_headless_mode()
        if disable_tqdm:
            logger.info("Headless mode detected - tqdm progress bar disabled")

        with tqdm(
            total=total_champions,
            desc="Scraping synergies",
            unit="champ",
            disable=disable_tqdm,
        ) as pbar:
            for future in as_completed(futures):
                champion = futures[future]
                try:
                    champ_name, synergies = future.result()
                    self._write_synergies_thread_safe(db, champ_name, synergies)
                    success_count += 1
                except Exception as e:
                    logger.error(
                        f"Failed to scrape synergies for {champion} after retries: {type(e).__name__}: {e}"
                    )
                    # Log first failure with full traceback for debugging
                    if failed_count == 0:
                        import traceback

                        logger.error(f"First failure traceback:\n{traceback.format_exc()}")
                    failed_count += 1
                finally:
                    pbar.update(1)

        duration = time.time() - start_time

        stats = {
            "success": success_count,
            "failed": failed_count,
            "total": total_champions,
            "duration": duration,
        }

        logger.info(
            f"Synergy scraping completed: {success_count}/{total_champions} succeeded, "
            f"{failed_count} failed, duration: {duration:.1f}s ({duration/60:.1f}min)"
        )

        return stats

    def parse_all_champions(self, db: Database, normalize_func) -> dict:
        """Parse all champions in parallel with progress tracking.

        Champions list is dynamically retrieved from Riot API, ensuring
        new champions are automatically included without code updates.

        Args:
            db: Database instance (must be connected)
            normalize_func: Function to normalize champion names for URLs

        Returns:
            dict: Statistics with keys 'success', 'failed', 'total', 'duration'
        """
        import time

        start_time = time.time()

        # Initialize database tables (use Alembic-compatible schema)
        # Note: init_champion_table() is deprecated and breaks Alembic migrations
        # Use Riot API integration instead to populate champions table
        if not db.create_riot_champions_table():
            logger.warning("Failed to create/update champions table schema")

        # Always update champions from Riot API to ensure new champions (like Zaahen) are included
        logger.info("Updating champions from Riot API...")
        db.update_champions_from_riot_api()

        db.init_matchups_table()

        # Get champion list dynamically from database (populated by Riot API)
        champion_names = list(db.get_all_champion_names().values())
        logger.info(f"Starting parallel scraping of {len(champion_names)} champions from Riot API")

        # Create thread pool and submit tasks
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        futures = {
            self.executor.submit(
                self._scrape_champion_with_retry, champion, normalize_func
            ): champion
            for champion in champion_names
        }

        # Track progress with tqdm
        success_count = 0
        failed_count = 0
        total_champions = len(champion_names)

        # Disable tqdm in headless mode (pythonw.exe, Task Scheduler)
        # to avoid AttributeError: 'NoneType' object has no attribute 'write'
        disable_tqdm = _is_headless_mode()
        if disable_tqdm:
            logger.info("Headless mode detected - tqdm progress bar disabled")

        with tqdm(
            total=total_champions, desc="Scraping champions", unit="champ", disable=disable_tqdm
        ) as pbar:
            for future in as_completed(futures):
                champion = futures[future]
                try:
                    champ_name, matchups = future.result()
                    self._write_matchups_thread_safe(db, champ_name, matchups)
                    success_count += 1
                except Exception as e:
                    logger.error(
                        f"Failed to scrape {champion} after retries: {type(e).__name__}: {e}"
                    )
                    # Log first failure with full traceback for debugging
                    if failed_count == 0:
                        import traceback

                        logger.error(f"First failure traceback:\n{traceback.format_exc()}")
                    failed_count += 1
                finally:
                    pbar.update(1)

        duration = time.time() - start_time

        stats = {
            "success": success_count,
            "failed": failed_count,
            "total": total_champions,
            "duration": duration,
        }

        logger.info(
            f"Scraping completed: {success_count}/{total_champions} succeeded, "
            f"{failed_count} failed, duration: {duration:.1f}s ({duration/60:.1f}min)"
        )

        # Pre-calculate ban recommendations for custom pools
        logger.info("Pre-calculating ban recommendations for custom pools...")
        try:
            from src.assistant import Assistant

            assistant = Assistant(db, verbose=False)
            ban_results = assistant.precalculate_all_custom_pool_bans()

            total_pools = len(ban_results)
            successful_pools = sum(1 for count in ban_results.values() if count > 0)
            total_bans = sum(ban_results.values())

            logger.info(
                f"Ban pre-calculation completed: {successful_pools}/{total_pools} pools, "
                f"{total_bans} total recommendations"
            )

            stats["ban_precalc"] = {
                "pools_processed": total_pools,
                "pools_successful": successful_pools,
                "total_recommendations": total_bans,
            }
        except Exception as e:
            logger.error(f"Failed to pre-calculate ban recommendations: {e}")
            import traceback

            traceback.print_exc()

        return stats

    def parse_champions_by_role(
        self, db: Database, champion_list: List[str], lane: str, normalize_func
    ) -> dict:
        """Parse champions for a specific role/lane in parallel.

        Args:
            db: Database instance (must be connected)
            champion_list: List of champion names for this role
            lane: Lane name (top, jungle, middle, bottom, support)
            normalize_func: Function to normalize champion names for URLs

        Returns:
            dict: Statistics with keys 'success', 'failed', 'total', 'duration'
        """
        import time

        start_time = time.time()

        logger.info(f"Starting parallel scraping of {len(champion_list)} champions for {lane}")

        # Initialize database tables (use Alembic-compatible schema)
        # Note: init_champion_table() is deprecated and breaks Alembic migrations
        # Use Riot API integration instead to populate champions table
        if not db.create_riot_champions_table():
            logger.warning("Failed to create/update champions table schema")

        # Always update champions from Riot API to ensure new champions (like Zaahen) are included
        logger.info("Updating champions from Riot API...")
        db.update_champions_from_riot_api()

        db.init_matchups_table()

        # Create thread pool and submit tasks
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)

        # Modified worker function that includes lane parameter
        def scrape_with_lane(champion):
            parser = self._get_parser()
            try:
                normalized_champion = normalize_func(champion)
                matchups = parser.get_champion_data_on_patch(
                    self.patch_version, normalized_champion, lane
                )
                logger.info(
                    f"Successfully scraped {champion} ({lane}, patch {self.patch_version}): {len(matchups)} matchups"
                )
                return champion, matchups
            except Exception as e:
                logger.error(f"Error scraping {champion} ({lane}): {e}")
                return champion, []

        futures = {
            self.executor.submit(scrape_with_lane, champion): champion for champion in champion_list
        }

        # Track progress with tqdm
        success_count = 0
        failed_count = 0

        # Disable tqdm in headless mode (pythonw.exe, Task Scheduler)
        disable_tqdm = _is_headless_mode()
        if disable_tqdm:
            logger.info(f"Headless mode detected - tqdm progress bar disabled for {lane}")

        with tqdm(
            total=len(champion_list), desc=f"Scraping {lane}", unit="champ", disable=disable_tqdm
        ) as pbar:
            for future in as_completed(futures):
                champion = futures[future]
                try:
                    champ_name, matchups = future.result()
                    self._write_matchups_thread_safe(db, champ_name, matchups)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to scrape {champion} ({lane}): {e}")
                    failed_count += 1
                finally:
                    pbar.update(1)

        duration = time.time() - start_time

        stats = {
            "success": success_count,
            "failed": failed_count,
            "total": len(champion_list),
            "lane": lane,
            "duration": duration,
        }

        logger.info(
            f"Scraping {lane} completed: {success_count}/{len(champion_list)} succeeded, "
            f"{failed_count} failed, duration: {duration:.1f}s ({duration/60:.1f}min)"
        )

        return stats

    def close(self) -> None:
        """Close all parser instances and clean up resources.

        This method should be called in a finally block to ensure proper cleanup
        of all webdriver instances and thread pool.
        """
        logger.info("Closing all parser instances...")

        # Shutdown thread pool
        if self.executor:
            self.executor.shutdown(wait=True)

        # Close all parser webdrivers
        for parser in self.parsers:
            try:
                parser.close()
            except Exception as e:
                logger.error(f"Error closing parser: {e}")

        self.parsers.clear()
        logger.info("All parsers closed successfully")
