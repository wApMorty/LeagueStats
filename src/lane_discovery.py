"""Dynamic lane discovery for multi-lane scraping (Horizon 1).

LoLalytics renders the lane distribution of every champion server-side
(Qwik SSR): the raw HTML contains, for each lane, an ``<img alt="X lane">``
icon followed by the share of the champion's games on that lane
(e.g. ``75.1%``). This module fetches that HTML with plain ``requests``
(no Selenium, no JS rendering) and extracts the distribution.

Architecture decision (validated 2026-06-12, stored in claude-flow memory
``arch_decision_h1_lane_discovery_2026_06``): lanes to scrape are discovered
dynamically per champion, keeping only lanes above
``scraping_config.LANE_PICKRATE_THRESHOLD`` (>10%, per ROADMAP_2026.md H1).

If LoLalytics changes this DOM, see docs/runbook_scraping.md § Lane discovery.
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from .config_constants import scraping_config

logger = logging.getLogger(__name__)

# One lane entry in the SSR HTML looks like (whitespace/attributes vary):
#   <img ... alt="top lane" ...><div ...><!--qv ...-->75.1%<!--/qv--></div>
# The 0-600 char window prevents matching a percentage from another section.
LANE_SHARE_PATTERN = re.compile(
    r'alt="(top|jungle|middle|bottom|support) lane".{0,600}?>\s*([\d.]+)%',
    re.DOTALL,
)


class LaneDiscoveryError(Exception):
    """Raised when the lane distribution of a champion cannot be discovered."""


def parse_lane_distribution(html: str) -> Dict[str, float]:
    """Extract the lane distribution from a LoLalytics champion page HTML.

    Args:
        html: Raw HTML of https://lolalytics.com/lol/<champion>/build/

    Returns:
        Mapping lane -> share of the champion's games in percent,
        e.g. {"top": 75.1, "jungle": 22.0, ...}. First occurrence wins
        (the lane picker is the first lane-icon block on the page).
    """
    distribution: Dict[str, float] = {}
    for lane, share in LANE_SHARE_PATTERN.findall(html):
        if lane not in distribution:
            try:
                distribution[lane] = float(share)
            except ValueError:  # pragma: no cover - regex guarantees digits
                continue
    return distribution


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10), reraise=True)
def fetch_lane_distribution(
    champion: str, patch: str, session: Optional[requests.Session] = None
) -> Dict[str, float]:
    """Fetch and parse the lane distribution for one champion.

    Args:
        champion: URL-normalized champion name (e.g. "drmundo")
        patch: LoLalytics patch parameter (e.g. "14" for rolling 14 days)
        session: Optional shared requests.Session (connection pooling)

    Returns:
        Mapping lane -> share in percent.

    Raises:
        LaneDiscoveryError: HTTP error or no lane data found in the HTML
        requests.RequestException: network failure (after 3 retries)
    """
    url = f"https://lolalytics.com/lol/{champion}/build/?tier=diamond_plus&patch={patch}"
    http = session or requests
    response = http.get(
        url,
        headers={"User-Agent": scraping_config.LANE_DISCOVERY_USER_AGENT},
        timeout=scraping_config.LANE_DISCOVERY_TIMEOUT,
    )

    if response.status_code != 200:
        raise LaneDiscoveryError(f"HTTP {response.status_code} for {champion} ({url})")

    distribution = parse_lane_distribution(response.text)
    if not distribution:
        # DOM changed or page empty: loud failure, the runbook covers diagnosis
        raise LaneDiscoveryError(
            f"No lane distribution found in HTML for {champion} "
            f"({len(response.text)} bytes) - LoLalytics DOM may have changed, "
            f"see docs/runbook_scraping.md"
        )

    return distribution


def select_lanes(distribution: Dict[str, float], threshold: Optional[float] = None) -> List[str]:
    """Keep lanes above the pickrate threshold.

    The distribution sums to ~100% over 5 lanes, so the most-played lane is
    always >= 20% and the result is never empty for a valid distribution.

    Args:
        distribution: Mapping lane -> share in percent
        threshold: Minimum share (default: scraping_config.LANE_PICKRATE_THRESHOLD)

    Returns:
        Lanes sorted by descending share.
    """
    if threshold is None:
        threshold = scraping_config.LANE_PICKRATE_THRESHOLD

    selected = [lane for lane, share in distribution.items() if share > threshold]
    if not selected and distribution:
        # Degenerate distribution (e.g. data spread thin right after a patch):
        # fall back to the single most-played lane instead of scraping nothing.
        selected = [max(distribution, key=distribution.get)]

    return sorted(selected, key=lambda lane: distribution[lane], reverse=True)


def discover_lanes_for_champions(
    champions: List[str],
    patch: str,
    normalize_func,
    max_workers: Optional[int] = None,
) -> Dict[str, List[str]]:
    """Discover the lanes to scrape for every champion, in parallel.

    Args:
        champions: Champion names as stored in the database
        patch: LoLalytics patch parameter
        normalize_func: Champion name -> URL-normalized name
        max_workers: Thread count (default: scraping_config.LANE_DISCOVERY_MAX_WORKERS)

    Returns:
        Mapping champion name -> lanes to scrape (descending share).
        Champions whose discovery failed map to [] — the caller decides the
        fallback (scrape the default lane untagged).
    """
    if max_workers is None:
        max_workers = scraping_config.LANE_DISCOVERY_MAX_WORKERS

    results: Dict[str, List[str]] = {}
    failures = 0

    with requests.Session() as session:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    fetch_lane_distribution, normalize_func(champion), patch, session
                ): champion
                for champion in champions
            }
            for future in as_completed(futures):
                champion = futures[future]
                try:
                    distribution = future.result()
                    results[champion] = select_lanes(distribution)
                    logger.info(
                        "Lanes for %s: %s (distribution: %s)",
                        champion,
                        results[champion],
                        distribution,
                    )
                except Exception as e:
                    failures += 1
                    results[champion] = []
                    logger.error("Lane discovery failed for %s: %s", champion, e)

    logger.info(
        "Lane discovery completed: %d/%d champions, %d failures",
        len(champions) - failures,
        len(champions),
        failures,
    )
    return results
