"""Sync local SQLite database to PostgreSQL Neon.

This script reads champions, matchups, and synergies from the local SQLite database
and transfers them to PostgreSQL Neon. It's designed to be called via subprocess
after auto_update_db.py completes scraping.

Architecture:
    - Standalone CLI script (async main)
    - Reads from local SQLite (data/db.db)
    - Transfers to PostgreSQL Neon (delete + batch insert pattern)
    - Exit codes: 0 = success, 1 = failure

Usage:
    python scripts/sync_local_to_neon.py

Requirements:
    - DATABASE_URL environment variable must be set
    - Local SQLite database must exist at data/db.db
    - Minimum 100 champions required for validation
"""

import asyncio
import os
import sqlite3
import sys
import traceback
from pathlib import Path
from typing import Dict, List, Tuple
from sqlalchemy import text

# Add server directory to path for imports
project_root = Path(__file__).parent.parent
server_root = project_root / "server"
sys.path.insert(0, str(server_root))

# Load environment variables from server/.env before importing config
try:
    from dotenv import load_dotenv

    env_path = server_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    # python-dotenv not installed, rely on environment variables
    pass

# Set dummy DATABASE_URL if not present (to allow config.py import)
# Real validation happens in main_async()
_database_url_was_set = "DATABASE_URL" in os.environ
if not _database_url_was_set:
    os.environ["DATABASE_URL"] = "postgresql://dummy:dummy@localhost/dummy"

# Import server modules
try:
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    from src.db import Champion, Matchup, Synergy, get_session_maker
except ImportError as e:
    print(f"ERROR: Failed to import server modules: {e}", file=sys.stderr)
    print("Ensure server/src/ modules exist and dependencies are installed", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)

# Remove dummy DATABASE_URL if it was set
if not _database_url_was_set:
    del os.environ["DATABASE_URL"]


def read_sqlite_data(sqlite_path: str) -> Dict[str, List[Tuple]]:
    """Read champions, matchups, and synergies from SQLite database.

    Args:
        sqlite_path: Path to SQLite database file

    Returns:
        Dictionary with keys:
            - champions: List of (id, key, name, title) tuples
            - matchups: List of (champion, enemy, winrate, delta2, games, pickrate) tuples
            - synergies: List of (champion, ally, winrate, delta2, games, pickrate) tuples

    Raises:
        FileNotFoundError: If SQLite database doesn't exist
        sqlite3.Error: If database read fails
    """
    if not os.path.exists(sqlite_path):
        raise FileNotFoundError(f"SQLite database not found: {sqlite_path}")

    print(f"Reading SQLite database: {sqlite_path}")

    try:
        conn = sqlite3.connect(sqlite_path)
        cursor = conn.cursor()

        # Read champions (similar to scrape_and_update.py pattern)
        cursor.execute(
            """
            SELECT id, key, name, title
            FROM champions
            ORDER BY id
            """
        )
        champions = cursor.fetchall()
        print(f"  Champions: {len(champions)}")

        # Read matchups
        cursor.execute(
            """
            SELECT champion, enemy, winrate, delta2, games, pickrate
            FROM matchups
            """
        )
        matchups = cursor.fetchall()
        print(f"  Matchups: {len(matchups)}")

        # Read synergies
        cursor.execute(
            """
            SELECT champion, ally, winrate, delta2, games, pickrate
            FROM synergies
            """
        )
        synergies = cursor.fetchall()
        print(f"  Synergies: {len(synergies)}")

        conn.close()

        return {
            "champions": champions,
            "matchups": matchups,
            "synergies": synergies,
        }

    except sqlite3.Error as e:
        print(f"ERROR: SQLite read failed: {e}", file=sys.stderr)
        raise


async def transfer_to_neon(
    data: Dict[str, List[Tuple]], session_maker: async_sessionmaker[AsyncSession]
) -> Dict[str, int]:
    """Transfer data to PostgreSQL Neon (atomic transaction).

    Uses the delete cascade + batch insert pattern from scrape_and_update.py.
    All operations are atomic within a single transaction.

    Args:
        data: Dictionary with champions, matchups, synergies data
        session_maker: SQLAlchemy async session maker

    Returns:
        Dictionary with counts of transferred records:
            - champions: Number of champions transferred
            - matchups: Number of matchups transferred
            - synergies: Number of synergies transferred

    Raises:
        Exception: If transfer fails (transaction will be rolled back)
    """
    print("Transferring to PostgreSQL Neon...")

    async with session_maker() as session:
        try:
            # Clear existing data using TRUNCATE (faster and more reliable than DELETE)
            # TRUNCATE automatically cascades to dependent tables via ON DELETE CASCADE
            print("  Clearing existing data...")
            await session.execute(
                text("TRUNCATE TABLE champions, matchups, synergies RESTART IDENTITY CASCADE")
            )
            await session.commit()
            print("  Existing data cleared")

            # Transfer Champions
            # Pattern from scrape_and_update.py lines 204-221
            print("  Transferring champions...")
            champion_objects = [
                Champion(
                    id=row[0],
                    name=row[2],  # name column
                    lolalytics_id=(
                        row[2].lower().replace(" ", "").replace("'", "")
                    ),  # Generate lolalytics_id
                )
                for row in data["champions"]
            ]
            session.add_all(champion_objects)
            await session.flush()  # Get IDs without committing
            print(f"    {len(champion_objects)} champions")

            # Transfer Matchups (all entries, including multi-lane duplicates)
            # Multi-lane support: Same matchup can exist across Top, Jungle, Mid, Support lanes
            print("  Transferring matchups...")
            matchup_objects = [
                Matchup(
                    champion_id=row[0],
                    enemy_id=row[1],
                    winrate=row[2],
                    delta2=row[3],
                    games=row[4],
                    pickrate=row[5],
                )
                for row in data["matchups"]
            ]
            session.add_all(matchup_objects)
            await session.flush()
            print(f"    {len(matchup_objects)} matchups")

            # Transfer Synergies (all entries, including multi-lane duplicates)
            # Multi-lane support: Same synergy can exist across multiple lanes
            print("  Transferring synergies...")
            synergy_objects = [
                Synergy(
                    champion_id=row[0],
                    ally_id=row[1],
                    winrate=row[2],
                    delta2=row[3],
                    games=row[4],
                    pickrate=row[5],
                )
                for row in data["synergies"]
            ]
            session.add_all(synergy_objects)
            await session.flush()
            print(f"    {len(synergy_objects)} synergies")

            # Commit all changes atomically
            # Pattern from scrape_and_update.py line 266
            await session.commit()
            print("  Transfer committed successfully")

            return {
                "champions": len(champion_objects),
                "matchups": len(matchup_objects),
                "synergies": len(synergy_objects),
            }

        except Exception as e:
            print(f"ERROR: Transfer failed: {e}", file=sys.stderr)
            await session.rollback()
            raise


async def main_async() -> int:
    """Main async function for syncing SQLite to Neon.

    Returns:
        Exit code: 0 = success, 1 = failure
    """
    try:
        # 1. Validate DATABASE_URL
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            print("ERROR: DATABASE_URL environment variable not configured", file=sys.stderr)
            print("Set DATABASE_URL in .env or environment", file=sys.stderr)
            return 1

        print("=" * 80)
        print("SQLite to PostgreSQL Neon Sync")
        print("=" * 80)

        # 2. Read SQLite data
        sqlite_path = project_root / "data" / "db.db"
        data = read_sqlite_data(str(sqlite_path))

        # 3. Validate data
        if len(data["champions"]) < 100:
            print(
                f"ERROR: Only {len(data['champions'])} champions found (expected 100+)",
                file=sys.stderr,
            )
            print("SQLite database may be incomplete or corrupted", file=sys.stderr)
            return 1

        # 4. Transfer to Neon
        session_maker = get_session_maker()
        stats = await transfer_to_neon(data, session_maker)

        # 5. Success
        print("=" * 80)
        print("SUCCESS: Sync completed")
        print(f"  Champions: {stats['champions']}")
        print(f"  Matchups: {stats['matchups']}")
        print(f"  Synergies: {stats['synergies']}")
        print("=" * 80)

        return 0

    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    except Exception as e:
        print(f"FATAL: Unexpected error during sync", file=sys.stderr)
        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1


def main() -> int:
    """Main entry point (synchronous wrapper).

    Returns:
        Exit code: 0 = success, 1 = failure
    """
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
