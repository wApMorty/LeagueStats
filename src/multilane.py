"""Multi-lane scraping orchestration (Horizon 1 — ROADMAP_2026.md §3 H1.2).

Pipeline:
    1. Refresh champions from the Riot API, reset matchups/synergies tables
    2. Discover the lanes played by each champion (>10% of its games),
       via cheap HTTP requests (src/lane_discovery.py)
    3. Scrape matchups then synergies once per (lane, champions) group,
       tagging every row with its lane (migration b7e41c9a3f02)

Champions whose lane discovery failed fall back to the legacy behavior:
their LoLalytics default lane is scraped and stored untagged (lane=NULL).
"""

import logging
from typing import Dict, List, Optional

from .config_constants import scraping_config
from .db import Database
from .lane_discovery import discover_lanes_for_champions
from .parallel_parser import ParallelParser

logger = logging.getLogger(__name__)


def group_champions_by_lane(lane_map: Dict[str, List[str]]) -> Dict[Optional[str], List[str]]:
    """Invert champion->lanes into lane->champions for batched scraping.

    Champions with no discovered lanes (discovery failure) are grouped under
    the None key (= scrape default lane, store untagged).

    Lane order follows scraping_config.LANES for deterministic runs.
    """
    groups: Dict[Optional[str], List[str]] = {lane: [] for lane in scraping_config.LANES}
    groups[None] = []

    for champion, lanes in lane_map.items():
        if not lanes:
            groups[None].append(champion)
        else:
            for lane in lanes:
                if lane in groups:
                    groups[lane].append(champion)
                else:  # pragma: no cover - discovery only emits known lanes
                    logger.warning("Unknown lane '%s' for %s, skipping", lane, champion)

    return {lane: sorted(champs) for lane, champs in groups.items() if champs}


def scrape_all_multilane(
    db: Database,
    parser: ParallelParser,
    normalize_func,
    include_synergies: bool = True,
) -> dict:
    """Run the full multi-lane scrape: discovery, matchups, synergies.

    Args:
        db: Connected Database instance
        parser: Configured ParallelParser (workers, patch, headless)
        normalize_func: Champion name -> URL-normalized name
        include_synergies: Also scrape synergies (default True)

    Returns:
        Aggregated statistics::

            {
                "lane_map": {champion: [lanes]},
                "discovery_failures": [champions],
                "pages_total": int,
                "matchups": {lane_label: stats_dict},
                "synergies": {lane_label: stats_dict},
                "success": int, "failed": int, "total": int,
            }
    """
    # ── 1. Schema/reference data: once for the whole run ────────────────────
    if not db.create_riot_champions_table():
        logger.warning("Failed to create/update champions table schema")
    logger.info("Updating champions from Riot API...")
    db.update_champions_from_riot_api()
    db.init_matchups_table()
    if include_synergies:
        db.init_synergies_table()

    champions = list(db.get_all_champion_names().values())
    logger.info("Multi-lane scrape starting for %d champions", len(champions))

    # ── 2. Lane discovery (cheap HTTP, parallel) ─────────────────────────────
    lane_map = discover_lanes_for_champions(champions, parser.patch_version, normalize_func)
    discovery_failures = sorted(champ for champ, lanes in lane_map.items() if not lanes)
    if discovery_failures:
        logger.warning(
            "Lane discovery failed for %d champion(s) (default-lane fallback): %s",
            len(discovery_failures),
            ", ".join(discovery_failures),
        )

    groups = group_champions_by_lane(lane_map)
    pages_per_phase = sum(len(champs) for champs in groups.values())
    logger.info(
        "Scrape plan: %d (champion, lane) pages per phase — %s",
        pages_per_phase,
        {lane or "default": len(champs) for lane, champs in groups.items()},
    )

    stats: dict = {
        "lane_map": lane_map,
        "discovery_failures": discovery_failures,
        "pages_total": pages_per_phase * (2 if include_synergies else 1),
        "matchups": {},
        "synergies": {},
    }

    # ── 3. Matchups, one parallel pass per lane group ────────────────────────
    for lane, champs in groups.items():
        stats["matchups"][lane or "default"] = parser.parse_champions_by_role(
            db, champs, lane, normalize_func, init_tables=False
        )

    # ── 4. Synergies, same groups ────────────────────────────────────────────
    if include_synergies:
        for lane, champs in groups.items():
            stats["synergies"][lane or "default"] = parser.parse_synergies_by_role(
                db, champs, lane, normalize_func, init_tables=False
            )

    # ── 5. Aggregated counters ───────────────────────────────────────────────
    all_phase_stats = list(stats["matchups"].values()) + list(stats["synergies"].values())
    stats["success"] = sum(s.get("success", 0) for s in all_phase_stats)
    stats["failed"] = sum(s.get("failed", 0) for s in all_phase_stats)
    stats["total"] = sum(s.get("total", 0) for s in all_phase_stats)

    logger.info(
        "Multi-lane scrape completed: %d/%d pages ok, %d failed",
        stats["success"],
        stats["total"],
        stats["failed"],
    )
    return stats
