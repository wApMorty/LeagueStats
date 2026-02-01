"""GitHub Actions automated scraping script for LeagueStats Coach.

This script performs daily automated scraping of League of Legends champion data
and updates the PostgreSQL database on Neon.

Architecture:
    1. Scraping Phase: Use ParallelParser with temporary SQLite in-memory database
    2. Transfer Phase: Read scraped data and write to PostgreSQL via SQLAlchemy async
    3. Monitoring: Detailed logs + Discord webhook notification on failure

Environment Variables:
    DATABASE_URL: PostgreSQL connection string (required)
    DISCORD_WEBHOOK_URL: Discord webhook for failure notifications (optional)

Usage:
    python server/scripts/scrape_and_update.py

Exit Codes:
    0: Success
    1: Critical failure
"""

import asyncio
import logging
import os
import sys
import time
import traceback
from typing import List, Dict, Tuple, Optional

import requests
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

# Validate required environment variables BEFORE importing server modules
# (server.src.db initializes AsyncSessionLocal at module level which needs DATABASE_URL)
if not os.environ.get("DATABASE_URL"):
    print("❌ ERROR: DATABASE_URL environment variable is not set")
    print("Please configure DATABASE_URL secret in GitHub Actions settings")
    sys.exit(1)

# Add project root to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.parallel_parser import ParallelParser
from src.db import Database
from src.constants import CHAMPIONS_LIST, normalize_champion_name_for_url
from server.src.db import Champion, Matchup, Synergy, get_session_maker
from server.src.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def send_discord_notification(error_msg: str) -> None:
    """Send Discord webhook notification on critical failure.

    Args:
        error_msg: Error message to send

    Notes:
        Only sends if DISCORD_WEBHOOK_URL environment variable is set.
        Failures to send notifications are logged but don't raise exceptions.
    """
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("DISCORD_WEBHOOK_URL not set - skipping notification")
        return

    payload = {
        "content": (
            "🚨 **GitHub Actions Scraping Failed**\n\n"
            f"```\n{error_msg}\n```\n\n"
            f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}"
        )
    }

    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Discord notification sent successfully")
    except Exception as e:
        logger.error(f"Failed to send Discord notification: {e}")


def scrape_to_temp_database() -> Tuple[Database, int, int, int]:
    """Scrape champion data to temporary in-memory SQLite database.

    Returns:
        Tuple of (temp_db, champions_scraped, matchups_scraped, synergies_scraped)

    Raises:
        Exception: If scraping fails critically
    """
    logger.info("=== Phase 1: Scraping to Temporary Database ===")

    # Create in-memory SQLite database
    temp_db = Database(":memory:")
    temp_db.connect()

    # Initialize tables with Riot API-compatible schema
    logger.info("Initializing temporary database tables...")

    # Create champions table with Riot API schema (avoid migration issues)
    cursor = temp_db.connection.cursor()
    cursor.execute("""
        CREATE TABLE champions (
            id INTEGER PRIMARY KEY,
            key TEXT,
            name TEXT NOT NULL,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    temp_db.connection.commit()
    logger.info("Champions table created with Riot API schema")

    temp_db.init_matchups_table()
    temp_db.init_synergies_table()

    # Configure parser for GitHub Actions (5 workers, headless mode)
    logger.info("Starting parallel scraping (5 workers, headless mode)...")
    parser = ParallelParser(max_workers=5, headless=True)

    try:
        # Parse all champions (list is retrieved automatically from Riot API)
        logger.info("Starting scraping (champions retrieved from Riot API)...")

        start_time = time.time()
        # Pass normalize function, NOT a list (parse_all_champions gets list from Riot API)
        stats = parser.parse_all_champions(temp_db, normalize_champion_name_for_url)
        duration = time.time() - start_time

        logger.info(f"Scraping stats: {stats}")

        # Get statistics
        cursor = temp_db.connection.cursor()

        cursor.execute("SELECT COUNT(*) FROM champions")
        champions_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM matchups")
        matchups_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM synergies")
        synergies_count = cursor.fetchone()[0]

        logger.info(f"Scraping completed in {duration:.2f}s")
        logger.info(f"  Champions: {champions_count}")
        logger.info(f"  Matchups: {matchups_count}")
        logger.info(f"  Synergies: {synergies_count}")

        return temp_db, champions_count, matchups_count, synergies_count

    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        parser.close()
        temp_db.close()
        raise
    finally:
        parser.close()


async def transfer_to_postgresql(
    temp_db: Database, session_maker: async_sessionmaker[AsyncSession]
) -> Dict[str, int]:
    """Transfer scraped data from SQLite to PostgreSQL.

    Args:
        temp_db: Temporary SQLite database with scraped data
        session_maker: SQLAlchemy async session maker

    Returns:
        Dictionary with counts of transferred records

    Raises:
        Exception: If transfer fails
    """
    logger.info("=== Phase 2: Transferring to PostgreSQL ===")

    cursor = temp_db.connection.cursor()
    stats = {"champions": 0, "matchups": 0, "synergies": 0}

    async with session_maker() as session:
        try:
            # Clear existing data (fresh update strategy)
            logger.info("Clearing existing data...")
            await session.execute(delete(Synergy))
            await session.execute(delete(Matchup))
            await session.execute(delete(Champion))
            await session.commit()
            logger.info("Existing data cleared")

            # Transfer Champions
            logger.info("Transferring champions...")
            # Note: ParallelParser.parse_all_champions() creates table with 'name' column (Riot API schema)
            # not 'champion' column (old schema from init_champion_table())
            cursor.execute("SELECT id, name FROM champions ORDER BY id")
            champions_data = cursor.fetchall()

            champion_objects = [
                Champion(
                    id=row[0],
                    name=row[1],
                    lolalytics_id=row[1].lower().replace(" ", ""),  # Generate lolalytics_id
                )
                for row in champions_data
            ]
            session.add_all(champion_objects)
            await session.flush()  # Get IDs without committing
            stats["champions"] = len(champion_objects)
            logger.info(f"  Transferred {stats['champions']} champions")

            # Transfer Matchups
            logger.info("Transferring matchups...")
            cursor.execute("SELECT champion, enemy, winrate, delta2, games, pickrate FROM matchups")
            matchups_data = cursor.fetchall()

            matchup_objects = [
                Matchup(
                    champion_id=row[0],
                    enemy_id=row[1],
                    winrate=row[2],
                    delta2=row[3],
                    games=row[4],
                    pickrate=row[5],
                )
                for row in matchups_data
            ]
            session.add_all(matchup_objects)
            await session.flush()
            stats["matchups"] = len(matchup_objects)
            logger.info(f"  Transferred {stats['matchups']} matchups")

            # Transfer Synergies
            logger.info("Transferring synergies...")
            cursor.execute("SELECT champion, ally, winrate, delta2, games, pickrate FROM synergies")
            synergies_data = cursor.fetchall()

            synergy_objects = [
                Synergy(
                    champion_id=row[0],
                    ally_id=row[1],
                    winrate=row[2],
                    delta2=row[3],
                    games=row[4],
                    pickrate=row[5],
                )
                for row in synergies_data
            ]
            session.add_all(synergy_objects)
            await session.flush()
            stats["synergies"] = len(synergy_objects)
            logger.info(f"  Transferred {stats['synergies']} synergies")

            # Commit all changes atomically
            await session.commit()
            logger.info("Transfer committed successfully")

            return stats

        except Exception as e:
            await session.rollback()
            logger.error(f"Transfer failed, rolled back: {e}")
            raise


async def main_async() -> int:
    """Main async function orchestrating scraping and database update.

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    logger.info("🚀 Starting GitHub Actions Automated Scraping")
    logger.info(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")

    overall_start = time.time()

    try:
        # Validate environment
        if not os.getenv("DATABASE_URL"):
            raise ValueError("DATABASE_URL environment variable not set")

        # Phase 1: Scrape to temporary database
        temp_db, champs_count, matchups_count, synergies_count = scrape_to_temp_database()

        # Validation: Ensure minimum data scraped
        if champs_count < 100:  # Expect 171 champions
            raise ValueError(
                f"Too few champions scraped ({champs_count}). Expected ~171. Data may be incomplete."
            )

        # Phase 2: Transfer to PostgreSQL
        session_maker = get_session_maker()
        transfer_stats = await transfer_to_postgresql(temp_db, session_maker)

        # Cleanup
        temp_db.close()

        # Summary
        overall_duration = time.time() - overall_start
        logger.info("=" * 60)
        logger.info("✅ Scraping and Update Completed Successfully")
        logger.info(f"Total Duration: {overall_duration:.2f}s")
        logger.info(f"Champions: {transfer_stats['champions']}")
        logger.info(f"Matchups: {transfer_stats['matchups']}")
        logger.info(f"Synergies: {transfer_stats['synergies']}")
        logger.info("=" * 60)

        return 0

    except Exception as e:
        error_msg = f"Critical failure: {str(e)}\n\n{traceback.format_exc()}"
        logger.error(error_msg)

        # Send Discord notification
        send_discord_notification(error_msg)

        return 1


def main() -> None:
    """Entry point for the script."""
    exit_code = asyncio.run(main_async())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
