"""Migration script: SQLite -> PostgreSQL data transfer.

This script migrates data from the legacy SQLite database (client/data/db.db)
to the new PostgreSQL database (Neon).

Steps:
1. Connect to SQLite database (read-only)
2. Extract all champions, matchups, synergies
3. Connect to PostgreSQL database (async)
4. Insert data in batches for performance
5. Verify data integrity (counts match)

Usage:
    python scripts/migrate_sqlite_to_postgres.py

Requirements:
    - SQLite database exists at ../data/db.db
    - PostgreSQL connection configured in .env (DATABASE_URL)
    - Alembic migrations already executed (tables exist)

Expected data volumes:
    - Champions: 172
    - Matchups: 36,000+
    - Synergies: 30,000+
"""

import sqlite3
import asyncio
import sys
from pathlib import Path
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

# Add parent directory to path to import src module
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db import AsyncSessionLocal, Champion, Matchup, Synergy, get_engine
from src.config import settings


# SQLite database path (relative to server directory)
SQLITE_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db.db"

# Batch size for bulk inserts (optimize for Neon serverless)
BATCH_SIZE = 1000


def extract_sqlite_data() -> tuple[list, list, list]:
    """Extract all data from SQLite database.

    Returns:
        Tuple of (champions, matchups, synergies) lists
    """
    print(f"[INFO] Connecting to SQLite database: {SQLITE_DB_PATH}")

    if not SQLITE_DB_PATH.exists():
        print(f"[ERROR] ERROR: SQLite database not found at {SQLITE_DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(str(SQLITE_DB_PATH))
    conn.row_factory = sqlite3.Row  # Access columns by name
    cursor = conn.cursor()

    # Extract champions
    print("[INFO] Extracting champions...")
    cursor.execute("SELECT id, key, name, title FROM champions ORDER BY id")
    champions_raw = cursor.fetchall()
    # Convert to dict and map columns correctly
    # SQLite has: id, key, name, title
    # PostgreSQL expects: id, name, lolalytics_id
    # Map: id->id, key->lolalytics_id, name->name
    champions = [
        {"id": row["id"], "name": row["name"], "lolalytics_id": row["key"]}
        for row in champions_raw
    ]
    print(f"[OK] Extracted {len(champions)} champions")

    # Extract matchups
    print("[INFO] Extracting matchups...")
    cursor.execute("""
        SELECT champion, enemy, winrate, delta2, games, pickrate,
               ROW_NUMBER() OVER (PARTITION BY champion, enemy ORDER BY games DESC) as rn
        FROM matchups
    """)
    matchups_raw = cursor.fetchall()
    # Map column names to PostgreSQL schema and deduplicate
    # SQLite has: champion, enemy
    # PostgreSQL expects: champion_id, enemy_id
    # Keep only the row with highest games (rn = 1) for each (champion, enemy) pair
    matchups = [
        {
            "champion_id": row["champion"],
            "enemy_id": row["enemy"],
            "winrate": row["winrate"],
            "delta2": row["delta2"],
            "games": row["games"],
            "pickrate": row["pickrate"]
        }
        for row in matchups_raw
        if row["rn"] == 1  # Only keep the first row (highest games)
    ]
    print(f"[OK] Extracted {len(matchups)} matchups (after deduplication)")

    # Extract synergies
    print("[INFO] Extracting synergies...")
    cursor.execute("""
        SELECT champion, ally, winrate, delta2, games, pickrate,
               ROW_NUMBER() OVER (PARTITION BY champion, ally ORDER BY games DESC) as rn
        FROM synergies
    """)
    synergies_raw = cursor.fetchall()
    # Map column names to PostgreSQL schema and deduplicate
    # SQLite has: champion, ally
    # PostgreSQL expects: champion_id, ally_id
    # Keep only the row with highest games (rn = 1) for each (champion, ally) pair
    synergies = [
        {
            "champion_id": row["champion"],
            "ally_id": row["ally"],
            "winrate": row["winrate"],
            "delta2": row["delta2"],
            "games": row["games"],
            "pickrate": row["pickrate"]
        }
        for row in synergies_raw
        if row["rn"] == 1  # Only keep the first row (highest games)
    ]
    print(f"[OK] Extracted {len(synergies)} synergies (after deduplication)")

    conn.close()
    return champions, matchups, synergies


async def insert_champions(session: AsyncSession, champions: list) -> None:
    """Insert champions into PostgreSQL.

    Args:
        session: Async database session
        champions: List of champion dicts (id, name, lolalytics_id)
    """
    print(f"  Inserting {len(champions)} champions into PostgreSQL...")

    # Insert in batches
    for i in range(0, len(champions), BATCH_SIZE):
        batch = champions[i:i + BATCH_SIZE]
        champion_objects = [
            Champion(
                id=c["id"],
                name=c["name"],
                lolalytics_id=c["lolalytics_id"]
            )
            for c in batch
        ]
        session.add_all(champion_objects)
        await session.flush()

    await session.commit()
    print(f"[OK] Inserted {len(champions)} champions")


async def insert_matchups(session: AsyncSession, matchups: list) -> None:
    """Insert matchups into PostgreSQL.

    Args:
        session: Async database session
        matchups: List of matchup dicts
    """
    print(f"  Inserting {len(matchups)} matchups into PostgreSQL...")

    # Insert in batches for performance
    for i in range(0, len(matchups), BATCH_SIZE):
        batch = matchups[i:i + BATCH_SIZE]
        matchup_objects = [
            Matchup(
                champion_id=m["champion_id"],
                enemy_id=m["enemy_id"],
                winrate=m["winrate"],
                delta2=m["delta2"],
                games=m["games"],
                pickrate=m["pickrate"]
            )
            for m in batch
        ]
        session.add_all(matchup_objects)
        await session.flush()

        if (i // BATCH_SIZE + 1) % 10 == 0:
            print(f"  Progress: {i + len(batch)}/{len(matchups)} matchups...")

    await session.commit()
    print(f"[OK] Inserted {len(matchups)} matchups")


async def insert_synergies(session: AsyncSession, synergies: list) -> None:
    """Insert synergies into PostgreSQL.

    Args:
        session: Async database session
        synergies: List of synergy dicts
    """
    print(f"  Inserting {len(synergies)} synergies into PostgreSQL...")

    # Insert in batches
    for i in range(0, len(synergies), BATCH_SIZE):
        batch = synergies[i:i + BATCH_SIZE]
        synergy_objects = [
            Synergy(
                champion_id=s["champion_id"],
                ally_id=s["ally_id"],
                winrate=s["winrate"],
                delta2=s["delta2"],
                games=s["games"],
                pickrate=s["pickrate"]
            )
            for s in batch
        ]
        session.add_all(synergy_objects)
        await session.flush()

        if (i // BATCH_SIZE + 1) % 10 == 0:
            print(f"  Progress: {i + len(batch)}/{len(synergies)} synergies...")

    await session.commit()
    print(f"[OK] Inserted {len(synergies)} synergies")


async def verify_data_integrity(expected_counts: dict) -> bool:
    """Verify that data was migrated correctly.

    Args:
        expected_counts: Dict with expected counts (champions, matchups, synergies)

    Returns:
        True if all counts match, False otherwise
    """
    print("\n  Verifying data integrity...")

    async with AsyncSessionLocal() as session:
        # Count champions
        result = await session.execute(select(func.count()).select_from(Champion))
        champion_count = result.scalar()

        # Count matchups
        result = await session.execute(select(func.count()).select_from(Matchup))
        matchup_count = result.scalar()

        # Count synergies
        result = await session.execute(select(func.count()).select_from(Synergy))
        synergy_count = result.scalar()

    # Verify counts
    success = True

    if champion_count == expected_counts["champions"]:
        print(f"[OK] Champions: {champion_count} (expected {expected_counts['champions']})")
    else:
        print(f"[ERROR] Champions: {champion_count} (expected {expected_counts['champions']})")
        success = False

    if matchup_count == expected_counts["matchups"]:
        print(f"[OK] Matchups: {matchup_count} (expected {expected_counts['matchups']})")
    else:
        print(f"[ERROR] Matchups: {matchup_count} (expected {expected_counts['matchups']})")
        success = False

    if synergy_count == expected_counts["synergies"]:
        print(f"[OK] Synergies: {synergy_count} (expected {expected_counts['synergies']})")
    else:
        print(f"[ERROR] Synergies: {synergy_count} (expected {expected_counts['synergies']})")
        success = False

    return success


async def main() -> None:
    """Main migration workflow."""
    print("=" * 80)
    print("LeagueStats Coach - SQLite -> PostgreSQL Data Migration")
    print("=" * 80)
    print()

    # Step 1: Extract data from SQLite
    champions, matchups, synergies = extract_sqlite_data()

    # Step 2: Connect to PostgreSQL
    print(f"\n[CONNECT] Connecting to PostgreSQL: {settings.database_url[:30]}...")
    engine = get_engine()

    try:
        # Test connection
        async with AsyncSessionLocal() as session:
            await session.execute(select(1))
        print("[OK] PostgreSQL connection successful")
    except Exception as e:
        print(f"[ERROR] ERROR: Could not connect to PostgreSQL: {e}")
        sys.exit(1)

    # Step 3: Insert data
    print("\n  Starting data migration...")
    async with AsyncSessionLocal() as session:
        await insert_champions(session, champions)
        await insert_matchups(session, matchups)
        await insert_synergies(session, synergies)

    # Step 4: Verify data integrity
    expected_counts = {
        "champions": len(champions),
        "matchups": len(matchups),
        "synergies": len(synergies)
    }

    success = await verify_data_integrity(expected_counts)

    # Summary
    print("\n" + "=" * 80)
    if success:
        print("[OK] Migration completed successfully!")
    else:
        print("[ERROR] Migration completed with errors (data integrity check failed)")
    print("=" * 80)

    # Cleanup
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
