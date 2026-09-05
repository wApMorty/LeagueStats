"""Champions table repository.

Extracted from src/db.py (dette de code, TODO.md P4) : déplacement verbatim,
aucun changement de comportement. ``Database`` reste la façade publique et
délègue ici ; les appels vers d'autres domaines (matchups, etc.) repassent
par ``self.db.<method>`` pour ne pas dupliquer la logique.
"""

from sqlite3 import Error
from typing import Dict

import requests

from ..constants import CHAMPIONS_LIST


class ChampionsRepository:
    """CRUD et requêtes sur la table ``champions``."""

    def __init__(self, db) -> None:
        self.db = db

    def init_champion_table(self) -> None:
        """Legacy method - use create_riot_champions_table() and update_champions_from_riot_api() instead."""
        print(
            "[WARNING] Using legacy init_champion_table(). Consider using Riot API integration instead."
        )
        self.db.execute_query("DROP TABLE IF EXISTS champions")
        # Reset auto-increment counter
        self.db.execute_query("DELETE FROM sqlite_sequence WHERE name='champions'")
        self.db.execute_query(
            "CREATE TABLE champions (id INTEGER PRIMARY KEY, champion TEXT NOT NULL)"
        )

        cursor = self.db.connection.cursor()
        try:
            for champ in CHAMPIONS_LIST:
                cursor.execute("INSERT INTO champions (champion) VALUES (?)", (champ,))
            self.db.connection.commit()
            print("Champions inserted successfully")
        except Error as e:
            print(f"The error '{e}' occurred")

    def get_champion_id(self, champion: str) -> int:
        """Get champion ID by name (for backward compatibility)."""
        cursor = self.db.connection.cursor()
        try:
            cursor.execute("SELECT id FROM champions WHERE name = ? COLLATE NOCASE", (champion,))
            # No commit needed for SELECT queries!
            result = cursor.fetchone()
            return result[0] if result else None
        except Error as e:
            print(f"The error '{e}' occurred")
            return None

    def get_champion_by_id(self, id: int) -> str:
        """Get champion name by ID."""
        cursor = self.db.connection.cursor()
        try:
            cursor.execute("SELECT name FROM champions WHERE id = ?", (id,))
            # No commit needed for SELECT queries!
            result = cursor.fetchone()
            return result[0] if result else None
        except Error as e:
            print(f"The error '{e}' occurred")
            return None

    def get_champion_base_winrate(self, champion_name: str) -> float:
        """Calculate champion base winrate from all matchup data using weighted average."""
        matchups = self.db.get_champion_matchups_by_name(
            champion_name
        )  # Returns Matchup objects by default
        if not matchups:
            return 50.0  # Default to 50% if no data

        total_weighted_winrate = 0.0
        total_weight = 0.0

        for matchup in matchups:
            # Use games as weight (more games = more reliable data)
            # Could also use pickrate or combination of both
            weight = matchup.games
            total_weighted_winrate += matchup.winrate * weight
            total_weight += weight

        if total_weight == 0:
            return 50.0

        base_winrate = total_weighted_winrate / total_weight
        return base_winrate

    # === RIOT API INTEGRATION ===

    def update_champions_from_riot_api(self) -> bool:
        """Update champion data from Riot Data Dragon API."""
        try:
            print("[INFO] Fetching latest champion data from Riot API...")

            # Get latest patch version
            version_url = "https://ddragon.leagueoflegends.com/api/versions.json"
            response = requests.get(version_url, timeout=10)
            if response.status_code != 200:
                print(f"[ERROR] Failed to get version info: {response.status_code}")
                return False

            latest_version = response.json()[0]
            print(f"[INFO] Using game version: {latest_version}")

            # Get champion data
            champion_url = (
                f"https://ddragon.leagueoflegends.com/cdn/{latest_version}/data/en_US/champion.json"
            )
            response = requests.get(champion_url, timeout=30)
            if response.status_code != 200:
                print(f"[ERROR] Failed to get champion data: {response.status_code}")
                return False

            champions_data = response.json()
            if "data" not in champions_data:
                print("[ERROR] Invalid champion data format")
                return False

            # Create backup of existing champions table
            cursor = self.db.connection.cursor()
            cursor.execute(
                "CREATE TABLE IF NOT EXISTS champions_backup AS SELECT * FROM champions WHERE 1=0"
            )
            cursor.execute("INSERT INTO champions_backup SELECT * FROM champions")

            # Clear existing champions AND matchups (to avoid orphaned references)
            cursor.execute("DELETE FROM matchups")  # Clear matchups first (foreign keys)
            cursor.execute("DELETE FROM champions")

            # Reset auto-increment counters (only if sqlite_sequence exists)
            try:
                cursor.execute("DELETE FROM sqlite_sequence WHERE name='champions'")
                cursor.execute("DELETE FROM sqlite_sequence WHERE name='matchups'")
            except Exception:
                # sqlite_sequence doesn't exist yet (no AUTOINCREMENT tables created)
                pass

            # Insert new champion data
            champions_inserted = 0
            for key, champ_data in champions_data["data"].items():
                try:
                    riot_id = int(champ_data["key"])
                    display_name = champ_data["name"]  # Keep for reference
                    title = champ_data.get("title", "")

                    # Use the key as name for consistency with constants.py
                    # This ensures champion names match our normalized format
                    cursor.execute(
                        """
                        INSERT INTO champions (id, key, name, title)
                        VALUES (?, ?, ?, ?)
                    """,
                        (riot_id, key, key, title),
                    )

                    champions_inserted += 1

                except (KeyError, ValueError) as e:
                    print(f"[WARNING] Error processing champion {key}: {e}")
                    continue

            self.db.connection.commit()

            # Verify insertion
            cursor.execute("SELECT COUNT(*) FROM champions")
            final_count = cursor.fetchone()[0]

            if final_count > 0:
                # Drop backup table
                cursor.execute("DROP TABLE champions_backup")
                print(f"[SUCCESS] Updated {champions_inserted} champions in database")
                return True
            else:
                # Restore from backup
                cursor.execute("DELETE FROM matchups")  # Clear orphaned matchups first
                cursor.execute("DELETE FROM champions")
                cursor.execute("DELETE FROM sqlite_sequence WHERE name='champions'")
                cursor.execute("DELETE FROM sqlite_sequence WHERE name='matchups'")
                cursor.execute("INSERT INTO champions SELECT * FROM champions_backup")
                cursor.execute("DROP TABLE champions_backup")
                self.db.connection.commit()
                print("[ERROR] No champions inserted, restored backup")
                return False

        except Exception as e:
            print(f"[ERROR] Error updating champions from Riot API: {e}")
            return False

    def create_riot_champions_table(self) -> bool:
        """Create/update champions table structure for Riot data."""
        try:
            cursor = self.db.connection.cursor()

            # Check if table exists and has the right structure
            cursor.execute("PRAGMA table_info(champions)")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]

            # If old structure, migrate
            if "key" not in column_names or "title" not in column_names:
                print("[INFO] Updating champions table structure...")

                # Create new table
                cursor.execute("""
                    CREATE TABLE champions_new (
                        id INTEGER PRIMARY KEY,
                        key TEXT,
                        name TEXT NOT NULL,
                        title TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Migrate existing data if any
                cursor.execute("SELECT COUNT(*) FROM champions")
                if cursor.fetchone()[0] > 0:
                    try:
                        cursor.execute("""
                            INSERT INTO champions_new (id, name)
                            SELECT id, name FROM champions
                        """)
                    except:
                        # If migration fails, that's ok - we'll update from Riot API anyway
                        pass

                # Replace old table
                cursor.execute("DROP TABLE champions")
                cursor.execute("ALTER TABLE champions_new RENAME TO champions")

            self.db.connection.commit()
            print("[INFO] Champions table structure verified")
            return True

        except Exception as e:
            print(f"[ERROR] Error creating champions table: {e}")
            return False

    def get_all_champion_names(self) -> Dict[int, str]:
        """Get mapping of all champion IDs to names."""
        try:
            cursor = self.db.connection.cursor()
            cursor.execute("SELECT id, name FROM champions")
            return dict(cursor.fetchall())
        except Exception as e:
            print(f"[ERROR] Error getting champion names: {e}")
            return {}

    # === PERFORMANCE OPTIMIZED METHODS ===

    def build_champion_cache(self) -> Dict[str, int]:
        """Build cache of champion name -> ID mappings for faster lookups."""
        try:
            cursor = self.db.connection.cursor()
            cursor.execute("SELECT name, id FROM champions")
            cache = {}

            # Get all champions once
            all_champions = cursor.fetchall()

            for name, champ_id in all_champions:
                # Add official name (exact case) - now these are Riot keys like "DrMundo"
                cache[name] = champ_id
                # Add lowercase version for flexible matching
                cache[name.lower()] = champ_id

            return cache
        except Exception as e:
            print(f"[ERROR] Error building champion cache: {e}")
            return {}

    # ========== Champion Lanes Methods (SPEC-04 B4) ==========

    def save_champion_lane_distribution(
        self, champion_id: int, distribution: Dict[str, float]
    ) -> None:
        """Upsert a champion's full lane distribution (champion_lanes table).

        Args:
            champion_id: Internal champion id (champions.id)
            distribution: lane -> share of the champion's games, in percent
                          (e.g. {"top": 75.1, "jungle": 22.0, ...}). No-op if empty.
        """
        if not distribution:
            return
        cursor = self.db.connection.cursor()
        try:
            cursor.executemany(
                """
                INSERT INTO champion_lanes (champion, lane, share) VALUES (?, ?, ?)
                ON CONFLICT(champion, lane) DO UPDATE SET share = excluded.share
                """,
                [(champion_id, lane, share) for lane, share in distribution.items()],
            )
            self.db.connection.commit()
        except Error as e:
            print(f"The error '{e}' occurred")

    def get_all_champion_lane_distributions(self) -> Dict[int, Dict[str, float]]:
        """All champion lane distributions, for role_inference.py's likelihood matrix.

        Loaded once (2 bulk queries, not one per champion) — meant to be cached
        by the caller at startup rather than re-read every draft tick (SPEC-04 §7).

        Champions absent from champion_lanes (not yet re-scraped since this
        table was introduced) fall back to their matchups games volume,
        normalized to 100% — an imperfect proxy (a matchup's game count isn't
        the champion's) but enough to bootstrap before the next full rescrape.

        Returns:
            championId -> {lane -> share%}. A champion with no data at all
            (new champion, no matchups either) is simply absent.
        """
        from ..config_constants import scraping_config

        distributions: Dict[int, Dict[str, float]] = {}
        cursor = self.db.connection.cursor()
        try:
            cursor.execute("SELECT champion, lane, share FROM champion_lanes")
            for champion_id, lane, share in cursor.fetchall():
                distributions.setdefault(champion_id, {})[lane] = share
        except Error as e:
            print(f"The error '{e}' occurred")

        try:
            cursor.execute(
                "SELECT champion, lane, SUM(games) FROM matchups WHERE lane != ? "
                "GROUP BY champion, lane",
                (scraping_config.DEFAULT_LANE,),
            )
            fallback_games: Dict[int, Dict[str, int]] = {}
            for champion_id, lane, games in cursor.fetchall():
                fallback_games.setdefault(champion_id, {})[lane] = games
        except Error as e:
            print(f"The error '{e}' occurred")
            fallback_games = {}

        for champion_id, lane_games in fallback_games.items():
            if champion_id in distributions:
                continue  # champion_lanes already has real data, don't override
            total = sum(lane_games.values())
            if total:
                distributions[champion_id] = {
                    lane: (games / total) * 100.0 for lane, games in lane_games.items()
                }

        return distributions
