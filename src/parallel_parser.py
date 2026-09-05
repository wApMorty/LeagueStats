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

Ce module ne porte que l'état partagé et le cycle de vie de
``ParallelParser`` (dette de code, TODO.md P4). Les méthodes de scrape sont
réparties par mixin, chacune partageant ``self`` (même executor, même pool
de parsers, mêmes verrous) sans état dupliqué :
- ``parallel_parser_legacy.py`` (``_LegacyFullScrapeMixin``) — scrape complet
  mono-lane (``parse_all_champions``/``parse_all_synergies``).
- ``parallel_parser_roles.py`` (``_RoleScrapeMixin``) — scrape par rôle/lane,
  chemin actif du pipeline multi-lane (``parse_page_by_role``, SPEC-02).
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Lock, local
from typing import List, Optional, Tuple
import logging
import threading

from .parser import Parser
from .db import Database
from .parallel_parser_legacy import _LegacyFullScrapeMixin
from .parallel_parser_roles import _RoleScrapeMixin

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(threadName)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Thread-local storage for parser instances (one parser per thread)
thread_local = local()


class ParallelParser(_LegacyFullScrapeMixin, _RoleScrapeMixin):
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

    def _cleanup_existing_resources(self) -> None:
        """Shutdown the existing executor and close all parsers before creating a new one.

        This prevents resource leaks when parse_* methods are called multiple times on
        the same ParallelParser instance (e.g. parsing matchups then synergies sequentially).
        Without this, each call stacks a new ThreadPoolExecutor on top of the previous one,
        leaving zombie Firefox + geckodriver processes running.

        Thread-local safety note:
            After shutdown(wait=True), all threads of the old executor are guaranteed dead
            before this method returns. The new executor will therefore always create fresh
            threads that have no thread_local.parser attribute, so _get_parser() will
            correctly instantiate new Parser objects instead of reusing stale closed ones.
            There is no risk of a recycled thread picking up a closed parser from
            thread_local storage.
        """
        if self.executor is not None:
            logger.info("Shutting down existing executor before creating a new one...")
            self.executor.shutdown(wait=True)
            self.executor = None
            logger.info("Executor shut down")

        if self.parsers:
            logger.info(f"Closing {len(self.parsers)} existing parser(s)...")
            for parser in self.parsers:
                try:
                    parser.close()
                except Exception as e:
                    logger.error(f"Error closing parser during cleanup: {e}")
            self.parsers.clear()
            logger.info("All existing parsers closed and cleared")

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

    def _write_matchups_thread_safe(
        self, db: Database, champion: str, matchups: List[Tuple], lane: Optional[str] = None
    ) -> None:
        """Write matchup data to database with thread-safe locking.

        Args:
            db: Database instance
            champion: Champion name
            matchups: List of matchup tuples
            lane: Optional lane tag for the whole batch (multi-lane pipeline).
                  None = default/unknown lane (legacy behavior).
        """
        with self.db_lock:
            try:
                # Convert matchups to batch format: [(champion, enemy, winrate, d1, d2, pick, games), ...]
                matchup_batch = [
                    (champion, enemy, winrate, d1, d2, pick, games)
                    for enemy, winrate, d1, d2, pick, games in matchups
                ]

                # Use batch insert (much faster - single transaction)
                if not hasattr(self, "_champion_cache"):
                    self._champion_cache = db.build_champion_cache()

                db.add_matchups_batch(matchup_batch, self._champion_cache, lane=lane)
            except Exception as e:
                logger.error(f"Database write error for {champion}: {e}")

    def _write_synergies_thread_safe(
        self, db: Database, champion: str, synergies: List[Tuple], lane: Optional[str] = None
    ) -> None:
        """Write synergy data to database with thread-safe locking.

        Args:
            db: Database instance
            champion: Champion name
            synergies: List of synergy tuples (ally, winrate, delta1, delta2, pickrate, games)
            lane: Optional lane tag for the whole batch (multi-lane pipeline).
                  None = default/unknown lane (legacy behavior).
        """
        with self.db_lock:
            try:
                # Convert synergies to batch format: [(champion, ally, winrate, d1, d2, pick, games), ...]
                synergy_batch = [
                    (champion, ally, winrate, d1, d2, pick, games)
                    for ally, winrate, d1, d2, pick, games in synergies
                ]

                # Use batch insert (much faster - single transaction)
                if not hasattr(self, "_champion_cache"):
                    self._champion_cache = db.build_champion_cache()

                db.add_synergies_batch(synergy_batch, lane=lane)
            except Exception as e:
                logger.error(f"Database write error for {champion} synergies: {e}")

    def close(self) -> None:
        """Close all parser instances and clean up resources.

        This method should be called in a finally block to ensure proper cleanup
        of all webdriver instances and thread pool.
        """
        logger.info("Closing all parser instances...")

        # Shutdown thread pool
        if self.executor:
            self.executor.shutdown(wait=True)
            self.executor = None

        # Close all parser webdrivers
        for parser in self.parsers:
            try:
                parser.close()
            except Exception as e:
                logger.error(f"Error closing parser: {e}")

        self.parsers.clear()
        logger.info("All parsers closed successfully")
