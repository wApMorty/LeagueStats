"""Legacy full-scrape mixin for ParallelParser (dette de code, TODO.md P4).

Extracted from src/parallel_parser.py : déplacement verbatim, aucun
changement de comportement. Scrape la lane par défaut LoLalytics pour TOUS
les champions en une seule passe — chemin utilisé par
``scripts/auto_update_db.py`` (ancien orchestrateur, superseded par
``scripts/update_all.py``/``src/pipeline.py``) et
``src/ui/data_update_ui.py``. Le pipeline multi-lane actif passe par
``parallel_parser_roles.py`` (``parse_page_by_role``, via ``src/multilane.py``).

Mixin plutôt que composition : partage ``self.executor``/``self.db_lock``/
``self._champion_cache``/``self.parsers`` et les méthodes ``_get_parser()``,
``_write_matchups_thread_safe()``, ``_cleanup_existing_resources()`` avec le
reste de ``ParallelParser`` (défini dans parallel_parser.py), sans dupliquer
cet état partagé ni le re-câbler.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from typing import List, Tuple

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from tqdm import tqdm
from selenium.common.exceptions import WebDriverException, TimeoutException

from .db import Database
from .cloudflare_detector import CloudflareException
from .utils.console import is_headless_mode as _is_headless_mode

logger = logging.getLogger(__name__)


class _LegacyFullScrapeMixin:
    """parse_all_champions / parse_all_synergies — scrape mono-lane complet."""

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((WebDriverException, TimeoutException, CloudflareException)),
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
            CloudflareException: After 3 failed attempts
        """
        parser = self._get_parser()

        try:
            normalized_champion = normalize_func(champion)
            matchups = parser.get_champion_data_on_patch(self.patch_version, normalized_champion)
            logger.info(
                f"Successfully scraped {champion} (patch {self.patch_version}): {len(matchups)} matchups"
            )
            return champion, matchups
        except (WebDriverException, TimeoutException, CloudflareException) as e:
            logger.warning(f"Retry triggered for {champion}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error scraping {champion}: {e}")
            return champion, []

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((WebDriverException, TimeoutException, CloudflareException)),
        reraise=True,
    )
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
            CloudflareException: After 3 failed attempts
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
        except (WebDriverException, TimeoutException, CloudflareException) as e:
            logger.warning(f"Retry triggered for {champion} synergies: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error scraping {champion} synergies: {e}")
            return champion, []

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

        # Build champion cache once for all workers
        self._champion_cache = db.build_champion_cache()
        logger.info("Champion cache built for batch operations")

        # Get champion list from database (populated by Riot API)
        champion_names = list(db.get_all_champion_names().values())
        logger.info(f"Starting parallel scraping of synergies for {len(champion_names)} champions")

        # Close any existing executor/parsers before creating a new thread pool
        self._cleanup_existing_resources()

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

        # Build champion cache once for all workers
        self._champion_cache = db.build_champion_cache()
        logger.info("Champion cache built for batch operations")

        # Get champion list dynamically from database (populated by Riot API)
        champion_names = list(db.get_all_champion_names().values())
        logger.info(f"Starting parallel scraping of {len(champion_names)} champions from Riot API")

        # Close any existing executor/parsers before creating a new thread pool
        self._cleanup_existing_resources()

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
