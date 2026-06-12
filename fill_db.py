"""Fill the local database with all matchups and synergies."""

import logging
import sys
import time
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

LOG_DIR = project_root / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "fill_db.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

from src.db import Database
from src.parallel_parser import ParallelParser
from src.config_constants import scraping_config
from src.constants import normalize_champion_name_for_url

DB_PATH = "data/db.db"
PATCH = "14"
MAX_WORKERS = scraping_config.DEFAULT_MAX_WORKERS  # 5 by default


def main():
    logger.info("=== fill_db.py starting ===")
    logger.info(
        "Patch: %s | Workers: %d | Headless: %s", PATCH, MAX_WORKERS, scraping_config.HEADLESS
    )

    db = Database(DB_PATH)
    db.connect()

    # Pre-check
    import sqlite3

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM champions")
    champs = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM matchups")
    m = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM synergies")
    s = c.fetchone()[0]
    conn.close()
    logger.info("DB state before: %d champions, %d matchups, %d synergies", champs, m, s)

    parser = ParallelParser(
        max_workers=MAX_WORKERS,
        patch_version=PATCH,
        headless=scraping_config.HEADLESS,
    )

    # ── Matchups ──────────────────────────────────────────────────────────────
    logger.info("--- Phase 1: Matchups ---")
    t0 = time.time()
    stats = parser.parse_all_champions(db, normalize_champion_name_for_url)
    duration = time.time() - t0
    logger.info(
        "Matchups done: %d/%d ok, %d failed, %.1f min",
        stats.get("success", 0),
        stats.get("total", 0),
        stats.get("failed", 0),
        duration / 60,
    )

    # ── Synergies ─────────────────────────────────────────────────────────────
    logger.info("--- Phase 2: Synergies ---")
    t0 = time.time()
    stats = parser.parse_all_synergies(db, normalize_champion_name_for_url)
    duration = time.time() - t0
    logger.info(
        "Synergies done: %d/%d ok, %d failed, %.1f min",
        stats.get("success", 0),
        stats.get("total", 0),
        stats.get("failed", 0),
        duration / 60,
    )

    # Post-check
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM matchups")
    m = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM synergies")
    s = c.fetchone()[0]
    conn.close()
    logger.info("DB state after: %d matchups, %d synergies", m, s)
    logger.info("=== fill_db.py complete ===")


if __name__ == "__main__":
    main()
