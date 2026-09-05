"""Repair engine for missing matchup/synergy data (dette de code, TODO.md P4).

Extracted from scripts/repair_data.py : déplacement verbatim, aucun
changement de comportement. Suit le même principe que src/pipeline.py
(moteur dans src/, wrapper CLI mince dans scripts/).

CRITICAL SAFETY RULES:
- NEVER calls parse_all_champions() / parse_all_synergies() -- would DROP the table
- NEVER calls init_matchups_table() / init_synergies_table() -- would DROP the table
- Only calls clear_*_for_champion() + add_*_batch() per champion

DETECTION METHOD:
    Uses SQL LEFT JOIN between champions and the target table to find champions
    with zero rows.

LANE HANDLING:
    Reuses the same dynamic lane discovery as the nightly multi-lane pipeline
    (src/lane_discovery.py, src/multilane.py) instead of scraping an untagged
    default lane: missing champions are grouped by their actually-played
    lane(s) (>10% pickrate) and each (champion, lane) page is scraped and
    tagged accordingly, exactly like scripts/update_all.py. Champions whose
    lane discovery fails fall back to the untagged default lane, same as the
    nightly pipeline.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from threading import Lock, local
from typing import Callable, Dict, List, Optional, Tuple

from .constants import normalize_champion_name_for_url
from .db import Database
from .parser import Parser

# Thread-local storage: one Firefox driver per worker thread
_thread_local = local()


@dataclass(frozen=True)
class RepairTarget:
    """Everything that differs between a matchup repair and a synergy repair.

    The repair pipeline (detect -> discover lanes -> scrape in parallel ->
    clear once per champion -> insert per lane) is identical for both; only
    the table, the Parser method and the two Database write signatures change.
    """

    name: str  # "matchups" | "synergies"
    # Full literal SQL (never interpolated at call time -- keeps the query
    # constant and out of reach of any user input)
    missing_query: str
    peer: str  # "enemy" | "ally" -- the second champion of a row
    default_headless: bool
    scrape: Callable[[Parser, str, str, Optional[str]], list]
    clear: Callable[[Database, str, dict], None]
    insert: Callable[[Database, list, dict, Optional[str]], None]


MATCHUPS = RepairTarget(
    name="matchups",
    missing_query="""
        SELECT c.name
        FROM champions c
        LEFT JOIN matchups m ON m.champion = c.id
        GROUP BY c.id, c.name
        HAVING COUNT(m.id) = 0
        ORDER BY c.name
    """,
    peer="enemy",
    # GUI mode bypasses Cloudflare detection better on the matchup pages
    default_headless=False,
    scrape=lambda parser, patch, champion, lane: parser.get_champion_data_on_patch(
        patch, champion, lane
    ),
    clear=lambda db, champion, cache: db.clear_matchups_for_champion(champion, cache),
    insert=lambda db, batch, cache, lane: db.add_matchups_batch(batch, cache, lane=lane),
)

SYNERGIES = RepairTarget(
    name="synergies",
    missing_query="""
        SELECT c.name
        FROM champions c
        LEFT JOIN synergies s ON s.champion = c.id
        GROUP BY c.id, c.name
        HAVING COUNT(s.id) = 0
        ORDER BY c.name
    """,
    peer="ally",
    default_headless=True,
    scrape=lambda parser, patch, champion, lane: parser.get_champion_synergies_on_patch(
        patch, champion, lane
    ),
    clear=lambda db, champion, cache: db.clear_synergies_for_champion(champion),
    insert=lambda db, batch, cache, lane: db.add_synergies_batch(batch, lane=lane),
)

TARGETS = {target.name: target for target in (MATCHUPS, SYNERGIES)}


def detect_champions_without_data(db: Database, target: RepairTarget) -> List[str]:
    """Find all champions that have zero rows in the target table.

    Uses a LEFT JOIN so champions absent from the table are identified even
    if the table is empty or missing rows.

    Args:
        db: Connected Database instance
        target: Repair target (matchups or synergies)

    Returns:
        Sorted list of champion names with no data
    """
    cursor = db.connection.cursor()
    cursor.execute(target.missing_query)
    rows = cursor.fetchall()
    return [row[0] for row in rows]


def detect_empty_champion_scores(db: Database) -> bool:
    """Check whether the champion_scores table is empty.

    Args:
        db: Connected Database instance

    Returns:
        True if champion_scores has no rows (or does not exist)
    """
    try:
        cursor = db.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM champion_scores")
        count = cursor.fetchone()[0]
        return count == 0
    except Exception:
        return True


def _get_or_create_parser(headless: bool) -> Parser:
    """Get thread-local Parser instance, creating one on first access.

    Args:
        headless: Whether to run Firefox in headless mode

    Returns:
        Parser instance for the current thread
    """
    if not hasattr(_thread_local, "parser"):
        _thread_local.parser = Parser(headless=headless)
    return _thread_local.parser


def _scrape_champion(
    target: RepairTarget,
    champion: str,
    patch_version: str,
    headless: bool,
    lane: Optional[str],
) -> Tuple[str, Optional[str], list]:
    """Scrape data for a single (champion, lane) page.

    Retries up to 3 times on transient WebDriver / Timeout errors before
    giving up and returning an empty list.

    Args:
        target: Repair target (matchups or synergies)
        champion: Champion name (as stored in the DB, e.g. "AurelionSol")
        patch_version: Patch window string (e.g. "14")
        headless: Whether to run Firefox headless
        lane: Lane to scrape (top/jungle/middle/bottom/support), or None to
              scrape LoLalytics' default lane (lane discovery failure fallback)

    Returns:
        Tuple of (champion_name, lane, rows). rows contains tuples of
        (peer, winrate, delta1, delta2, pickrate, games).
        Returns empty list on failure.
    """
    from selenium.common.exceptions import WebDriverException, TimeoutException

    parser = _get_or_create_parser(headless)
    normalized = normalize_champion_name_for_url(champion)
    lane_label = lane or "default"

    for attempt in range(1, 4):
        try:
            rows = target.scrape(parser, patch_version, normalized, lane)
            return champion, lane, rows
        except (WebDriverException, TimeoutException) as exc:
            if attempt < 3:
                wait_secs = 2**attempt  # 2s, 4s
                logging.getLogger(__name__).warning(
                    f"Attempt {attempt}/3 failed for {champion} {target.name} ({lane_label}): {exc} "
                    f"-- retrying in {wait_secs}s"
                )
                time.sleep(wait_secs)
            else:
                logging.getLogger(__name__).error(
                    f"All 3 attempts failed for {champion} {target.name} ({lane_label}): {exc}"
                )
                return champion, lane, []
        except Exception as exc:
            logging.getLogger(__name__).error(
                f"Unexpected error scraping {champion} {target.name} ({lane_label}): {exc}"
            )
            return champion, lane, []

    return champion, lane, []  # unreachable but satisfies type checker


def repair_parallel(
    target: RepairTarget,
    db: Database,
    groups: Dict[Optional[str], List[str]],
    patch_version: str,
    max_workers: int,
    headless: bool,
    logger: logging.Logger,
) -> dict:
    """Re-scrape and insert rows for the given (lane -> champions) groups in parallel.

    Groups come from group_champions_by_lane(discover_lanes_for_champions(...)),
    the same helpers used by the nightly multi-lane pipeline (src/multilane.py),
    so a champion playing several lanes is scraped and tagged once per lane
    just like a full update_all.py run.

    For each (champion, lane) page this function:
    1. Scrapes data using a dedicated thread-local Firefox driver
    2. Clears existing (empty) rows for that champion, once per champion, via
       target.clear() (safe -- does NOT drop the table) -- done once even if
       the champion has several lanes, so a second lane's insert never wipes
       the first lane's freshly-written rows
    3. Inserts new rows via target.insert(lane=...) inside a shared lock

    NEVER calls parse_all_champions() / parse_all_synergies() or the init_*_table()
    helpers.

    Args:
        target: Repair target (matchups or synergies)
        db: Connected Database instance
        groups: Mapping lane (or None for the discovery-failure fallback) to
                the list of champions to scrape on that lane
        patch_version: Patch window string (e.g. "14")
        max_workers: Number of parallel Firefox workers
        headless: Whether to run Firefox headless
        logger: Logger instance

    Returns:
        dict with keys 'success', 'failed', 'total', 'duration' (champion-level counts)
    """
    db_lock = Lock()
    champion_cache = db.build_champion_cache()
    cleared_champions: set = set()

    all_champions = sorted({champ for champs in groups.values() for champ in champs})
    work_items = [(champ, lane) for lane, champs in groups.items() for champ in champs]

    success_champions: set = set()
    failed_pages = 0
    start_time = time.time()

    logger.info(
        f"Starting parallel {target.name} repair: {len(all_champions)} champions, "
        f"{len(work_items)} (champion, lane) pages, {max_workers} workers, headless={headless}"
    )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_scrape_champion, target, champ, patch_version, headless, lane): (
                champ,
                lane,
            )
            for champ, lane in work_items
        }

        for future in as_completed(futures):
            champion, lane = futures[future]
            lane_label = lane or "default"
            try:
                champ_name, champ_lane, rows = future.result(timeout=120)

                if not rows:
                    logger.warning(
                        f"No {target.name} data returned for {champ_name} ({lane_label}) "
                        "-- skipping insert"
                    )
                    failed_pages += 1
                    continue

                # Thread-safe DB write: clear old (empty) rows once per champion, then insert
                with db_lock:
                    if champ_name not in cleared_champions:
                        target.clear(db, champ_name, champion_cache)
                        cleared_champions.add(champ_name)

                    # Convert to batch format: [(champion, peer, wr, d1, d2, pick, games), ...]
                    batch = [
                        (champ_name, peer, winrate, d1, d2, pick, games)
                        for peer, winrate, d1, d2, pick, games in rows
                    ]
                    target.insert(db, batch, champion_cache, champ_lane)

                logger.info(
                    f"Repaired {champ_name} ({lane_label}): {len(rows)} {target.name} inserted"
                )
                success_champions.add(champ_name)

            except Exception as exc:
                logger.error(f"Failed to repair {champion} ({lane_label}): {exc}")
                failed_pages += 1

    duration = time.time() - start_time
    failed_champions = [c for c in all_champions if c not in success_champions]

    return {
        "success": len(success_champions),
        "failed": len(failed_champions),
        "total": len(all_champions),
        "duration": duration,
    }


def _cleanup_thread_parsers(parsers_registry: list, logger: logging.Logger) -> None:
    """Close all Parser instances tracked in the registry.

    Args:
        parsers_registry: List of Parser instances to close
        logger: Logger instance
    """
    for parser in parsers_registry:
        try:
            parser.close()
        except Exception as exc:
            logger.warning(f"Error closing parser during cleanup: {exc}")
    parsers_registry.clear()
