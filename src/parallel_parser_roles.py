"""Per-role/lane scrape mixin for ParallelParser (dette de code, TODO.md P4).

Extracted from src/parallel_parser.py : déplacement verbatim, aucun
changement de comportement. Chemin actif du pipeline multi-lane
(``src/multilane.py`` appelle ``parse_page_by_role``, SPEC-02 — une seule
visite de page par champion pour matchups + synergies).
``parse_champions_by_role``/``parse_synergies_by_role`` (paire séquentielle
pré-SPEC-02) restent testés mais ne sont plus appelés par le pipeline actif.

Mixin plutôt que composition : partage ``self.executor``/``self.db_lock``/
``self.parsers`` et les méthodes ``_get_parser()``,
``_write_matchups_thread_safe()``, ``_write_synergies_thread_safe()``,
``_cleanup_existing_resources()`` avec le reste de ``ParallelParser`` (défini
dans parallel_parser.py), sans dupliquer cet état partagé ni le re-câbler.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from typing import List, Optional, Tuple

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from tqdm import tqdm
from selenium.common.exceptions import WebDriverException, TimeoutException

from .db import Database
from .cloudflare_detector import CloudflareException
from .utils.console import is_headless_mode as _is_headless_mode

logger = logging.getLogger(__name__)


class _RoleScrapeMixin:
    """parse_champions_by_role / parse_synergies_by_role / parse_page_by_role."""

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((WebDriverException, TimeoutException, CloudflareException)),
        reraise=True,
    )
    def _scrape_champion_page_with_retry(
        self,
        champion: str,
        lane: Optional[str],
        normalize_func,
        include_synergies: bool,
    ) -> Tuple[str, List[Tuple], List[Tuple]]:
        """Scrape matchups + synergies from a single page visit, with retry (SPEC-02).

        Uses exponential backoff: 2s, 4s, 8s (max 10s) between retries.
        Retries up to 3 times on WebDriverException, TimeoutException or
        CloudflareException.

        Args:
            champion: Champion name to scrape
            lane: Lane name or None
            normalize_func: Function to normalize champion name for URL
            include_synergies: Also read the synergies tab off the same page

        Returns:
            (champion, matchups, synergies) tuple. Both lists are empty if the
            page never rendered; synergies alone is empty if only that tab
            failed (matchups are never lost, see get_champion_page_data).

        Raises:
            WebDriverException: After 3 failed attempts
            TimeoutException: After 3 failed attempts
            CloudflareException: After 3 failed attempts
        """
        parser = self._get_parser()

        try:
            normalized_champion = normalize_func(champion)
            matchups, synergies = parser.get_champion_page_data(
                self.patch_version, normalized_champion, lane, include_synergies=include_synergies
            )
            logger.info(
                f"Successfully scraped {champion} ({lane or 'default'}, patch {self.patch_version}): "
                f"{len(matchups)} matchups, {len(synergies)} synergies"
            )
            return champion, matchups, synergies
        except (WebDriverException, TimeoutException, CloudflareException) as e:
            logger.warning(f"Retry triggered for {champion} ({lane or 'default'}): {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error scraping {champion} ({lane or 'default'}): {e}")
            return champion, [], []

    def parse_champions_by_role(
        self,
        db: Database,
        champion_list: List[str],
        lane: Optional[str],
        normalize_func,
        init_tables: bool = True,
    ) -> dict:
        """Parse champions for a specific role/lane in parallel.

        Matchups are tagged with the lane in the database (multi-lane pipeline,
        Horizon 1). With lane=None, the LoLalytics default lane is scraped and
        rows are stored untagged.

        Args:
            db: Database instance (must be connected)
            champion_list: List of champion names for this role
            lane: Lane name (top, jungle, middle, bottom, support) or None
            normalize_func: Function to normalize champion names for URLs
            init_tables: If True (legacy default), refresh champions from the
                Riot API and DROP+recreate the matchups table. MUST be False
                when called once per lane in the multi-lane pipeline, otherwise
                each lane wipes the previous one.

        Returns:
            dict: Statistics with keys 'success', 'failed', 'total', 'duration'
        """
        import time

        start_time = time.time()

        lane_label = lane or "default"
        logger.info(
            f"Starting parallel scraping of {len(champion_list)} champions for {lane_label}"
        )

        if init_tables:
            # Initialize database tables (use Alembic-compatible schema)
            # Note: init_champion_table() is deprecated and breaks Alembic migrations
            # Use Riot API integration instead to populate champions table
            if not db.create_riot_champions_table():
                logger.warning("Failed to create/update champions table schema")

            # Always update champions from Riot API to ensure new champions are included
            logger.info("Updating champions from Riot API...")
            db.update_champions_from_riot_api()

            db.init_matchups_table()

        # Close any existing executor/parsers before creating a new thread pool
        self._cleanup_existing_resources()

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
                    f"Successfully scraped {champion} ({lane_label}, patch {self.patch_version}): {len(matchups)} matchups"
                )
                return champion, matchups
            except Exception as e:
                logger.error(f"Error scraping {champion} ({lane_label}): {e}")
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
            logger.info(f"Headless mode detected - tqdm progress bar disabled for {lane_label}")

        with tqdm(
            total=len(champion_list),
            desc=f"Scraping {lane_label}",
            unit="champ",
            disable=disable_tqdm,
        ) as pbar:
            for future in as_completed(futures):
                champion = futures[future]
                try:
                    champ_name, matchups = future.result()
                    self._write_matchups_thread_safe(db, champ_name, matchups, lane=lane)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to scrape {champion} ({lane_label}): {e}")
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

    def parse_synergies_by_role(
        self,
        db: Database,
        champion_list: List[str],
        lane: Optional[str],
        normalize_func,
        init_tables: bool = True,
    ) -> dict:
        """Parse champion synergies for a specific role/lane in parallel.

        Synergies are tagged with the lane in the database (multi-lane
        pipeline, Horizon 1). With lane=None, the LoLalytics default lane is
        scraped and rows are stored untagged.

        Args:
            db: Database instance (must be connected)
            champion_list: List of champion names for this role
            lane: Lane name (top, jungle, middle, bottom, support) or None
            normalize_func: Function to normalize champion names for URLs
            init_tables: If True (legacy default), DROP+recreate the synergies
                table. MUST be False when called once per lane in the
                multi-lane pipeline, otherwise each lane wipes the previous one.

        Returns:
            dict: Statistics with keys 'success', 'failed', 'total', 'duration'
        """
        import time

        start_time = time.time()

        lane_label = lane or "default"
        logger.info(
            f"Starting parallel scraping of synergies for {len(champion_list)} champions for {lane_label}"
        )

        if init_tables:
            # Initialize synergies table
            db.init_synergies_table()

        # Close any existing executor/parsers before creating a new thread pool
        self._cleanup_existing_resources()

        # Create thread pool and submit tasks
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)

        # Modified worker function that includes lane parameter
        def scrape_synergies_with_lane(champion):
            parser = self._get_parser()
            try:
                normalized_champion = normalize_func(champion)
                synergies = parser.get_champion_synergies_on_patch(
                    self.patch_version, normalized_champion, lane
                )
                logger.info(
                    f"Successfully scraped synergies for {champion} ({lane_label}, patch {self.patch_version}): {len(synergies)} allies"
                )
                return champion, synergies
            except Exception as e:
                logger.error(f"Error scraping synergies for {champion} ({lane_label}): {e}")
                return champion, []

        futures = {
            self.executor.submit(scrape_synergies_with_lane, champion): champion
            for champion in champion_list
        }

        # Track progress with tqdm
        success_count = 0
        failed_count = 0

        # Disable tqdm in headless mode (pythonw.exe, Task Scheduler)
        disable_tqdm = _is_headless_mode()
        if disable_tqdm:
            logger.info(
                f"Headless mode detected - tqdm progress bar disabled for {lane_label} synergies"
            )

        with tqdm(
            total=len(champion_list),
            desc=f"Scraping {lane_label} synergies",
            unit="champ",
            disable=disable_tqdm,
        ) as pbar:
            for future in as_completed(futures):
                champion = futures[future]
                try:
                    champ_name, synergies = future.result()
                    self._write_synergies_thread_safe(db, champ_name, synergies, lane=lane)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to scrape synergies for {champion} ({lane_label}): {e}")
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
            f"Scraping {lane} synergies completed: {success_count}/{len(champion_list)} succeeded, "
            f"{failed_count} failed, duration: {duration:.1f}s ({duration/60:.1f}min)"
        )

        return stats

    def parse_page_by_role(
        self,
        db: Database,
        champion_list: List[str],
        lane: Optional[str],
        normalize_func,
        include_matchups: bool = True,
        include_synergies: bool = True,
        init_tables: bool = False,
    ) -> dict:
        """Scrape matchups + synergies for one lane group from a single page
        visit per champion (SPEC-02), replacing the sequential
        parse_champions_by_role + parse_synergies_by_role pair.

        Each champion's page is loaded once; get_champion_page_data() reads
        the matchups carousel and, if requested, clicks over to the synergies
        one. A champion whose synergies tab fails still has its matchups
        written and is only added to ``synergies_missing`` (SPEC-02 §3.4):
        the shared page load must never cause an already-scraped matchup to
        be dropped.

        Args:
            db: Database instance (must be connected)
            champion_list: List of champion names for this role
            lane: Lane name (top, jungle, middle, bottom, support) or None
            normalize_func: Function to normalize champion names for URLs
            include_matchups: Persist the matchups read off the page.
                Matchups are always fetched regardless of this flag (they are
                free on this page visit and gate whether the champion
                succeeded), but are only written to the DB when True.
            include_synergies: Also read (and persist) the synergies tab.
            init_tables: If True, refresh champions from the Riot API and
                DROP+recreate the matchups/synergies tables. MUST be False
                when called once per lane in the multi-lane pipeline,
                otherwise each lane wipes the previous one.

        Returns:
            dict: Statistics with keys 'success', 'failed', 'total', 'lane',
                'duration', 'synergies_missing' (champions whose matchups
                were written but whose synergies tab never rendered).
        """
        import time

        start_time = time.time()

        lane_label = lane or "default"
        logger.info(
            f"Starting single-pass scraping of {len(champion_list)} champions for {lane_label}"
        )

        if init_tables:
            # Initialize database tables (use Alembic-compatible schema)
            if not db.create_riot_champions_table():
                logger.warning("Failed to create/update champions table schema")

            logger.info("Updating champions from Riot API...")
            db.update_champions_from_riot_api()

            if include_matchups:
                db.init_matchups_table()
            if include_synergies:
                db.init_synergies_table()

        # Close any existing executor/parsers before creating a new thread pool
        self._cleanup_existing_resources()

        # Create thread pool and submit tasks
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        futures = {
            self.executor.submit(
                self._scrape_champion_page_with_retry,
                champion,
                lane,
                normalize_func,
                include_synergies,
            ): champion
            for champion in champion_list
        }

        # Track progress with tqdm
        success_count = 0
        failed_count = 0
        synergies_missing: List[str] = []

        # Disable tqdm in headless mode (pythonw.exe, Task Scheduler)
        disable_tqdm = _is_headless_mode()
        if disable_tqdm:
            logger.info(f"Headless mode detected - tqdm progress bar disabled for {lane_label}")

        with tqdm(
            total=len(champion_list),
            desc=f"Scraping {lane_label}",
            unit="champ",
            disable=disable_tqdm,
        ) as pbar:
            for future in as_completed(futures):
                champion = futures[future]
                try:
                    champ_name, matchups, synergies = future.result()
                    if not matchups:
                        logger.error(f"No matchups for {champion} ({lane_label}): marking failed")
                        failed_count += 1
                        continue

                    if include_matchups:
                        self._write_matchups_thread_safe(db, champ_name, matchups, lane=lane)

                    if include_synergies:
                        if synergies:
                            self._write_synergies_thread_safe(db, champ_name, synergies, lane=lane)
                        else:
                            synergies_missing.append(champ_name)
                            logger.warning(
                                f"Synergies missing for {champ_name} ({lane_label}): "
                                "matchups kept, flagged for targeted repair"
                            )

                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to scrape {champion} ({lane_label}): {e}")
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
            "synergies_missing": synergies_missing,
        }

        logger.info(
            f"Scraping {lane} completed: {success_count}/{len(champion_list)} succeeded, "
            f"{failed_count} failed, {len(synergies_missing)} missing synergies, "
            f"duration: {duration:.1f}s ({duration/60:.1f}min)"
        )

        return stats
