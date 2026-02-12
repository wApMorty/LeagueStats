import sqlite3
from sqlite3 import Error
from typing import List, Optional, Dict, Union, Tuple
import requests
from .constants import CHAMPIONS_LIST
from .models import Matchup, MatchupDraft, Synergy


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self.connection = None

    def connect(self) -> None:
        try:
            self.connection = sqlite3.connect(self.path)
            # Enable foreign key constraints
            self.connection.execute("PRAGMA foreign_keys = ON")
            print("Connection to SQLite DB successful")
            # Ensure indexes exist for optimal performance (only if tables exist)
            try:
                self.create_database_indexes()
            except Error:
                # Tables might not exist yet, indexes will be created when tables are initialized
                pass
        except Error as e:
            print(f"The error '{e}' occurred")

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()

    def create_database_indexes(self) -> None:
        """Create database indexes for performance optimization."""
        cursor = self.connection.cursor()

        try:
            # Get existing indexes
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
            existing_indexes = {row[0] for row in cursor.fetchall()}

            # Check if tables exist before creating indexes
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('champions', 'matchups')"
            )
            existing_tables = {row[0] for row in cursor.fetchall()}

            created_indexes = []

            if "champions" in existing_tables:
                # Index on champions.name for faster name lookups
                if "idx_champions_name" not in existing_indexes:
                    cursor.execute("CREATE INDEX idx_champions_name ON champions(name)")
                    created_indexes.append("idx_champions_name")

            if "matchups" in existing_tables:
                # Indexes on matchups table for faster queries
                if "idx_matchups_champion" not in existing_indexes:
                    cursor.execute("CREATE INDEX idx_matchups_champion ON matchups(champion)")
                    created_indexes.append("idx_matchups_champion")

                if "idx_matchups_enemy" not in existing_indexes:
                    cursor.execute("CREATE INDEX idx_matchups_enemy ON matchups(enemy)")
                    created_indexes.append("idx_matchups_enemy")

                if "idx_matchups_pickrate" not in existing_indexes:
                    cursor.execute("CREATE INDEX idx_matchups_pickrate ON matchups(pickrate)")
                    created_indexes.append("idx_matchups_pickrate")

                # Composite index for common query pattern (champion + pickrate filter)
                if "idx_matchups_champion_pickrate" not in existing_indexes:
                    cursor.execute(
                        "CREATE INDEX idx_matchups_champion_pickrate ON matchups(champion, pickrate)"
                    )
                    created_indexes.append("idx_matchups_champion_pickrate")

                # Composite index for reverse lookups (enemy + pickrate)
                if "idx_matchups_enemy_pickrate" not in existing_indexes:
                    cursor.execute(
                        "CREATE INDEX idx_matchups_enemy_pickrate ON matchups(enemy, pickrate)"
                    )
                    created_indexes.append("idx_matchups_enemy_pickrate")

            self.connection.commit()

            # Only log if indexes were actually created
            if created_indexes:
                print("[INFO] Created database indexes for performance optimization:")
                for idx_name in created_indexes:
                    print(f"[INFO]   - {idx_name}")

        except Error as e:
            print(f"[WARNING] Error creating indexes: {e}")

    def execute_query(self, query: str, commit: bool = True) -> None:
        cursor = self.connection.cursor()
        try:
            cursor.execute(query)
            if commit:
                self.connection.commit()
            print(f"Query executed successfully : {query}")
        except Error as e:
            print(f"The error '{e}' occurred")

    def init_champion_table(self) -> None:
        """Legacy method - use create_riot_champions_table() and update_champions_from_riot_api() instead."""
        print(
            "[WARNING] Using legacy init_champion_table(). Consider using Riot API integration instead."
        )
        self.execute_query("DROP TABLE IF EXISTS champions")
        # Reset auto-increment counter
        self.execute_query("DELETE FROM sqlite_sequence WHERE name='champions'")
        self.execute_query(
            "CREATE TABLE champions (id INTEGER PRIMARY KEY, champion TEXT NOT NULL)"
        )

        cursor = self.connection.cursor()
        try:
            for champ in CHAMPIONS_LIST:
                cursor.execute("INSERT INTO champions (champion) VALUES (?)", (champ,))
            self.connection.commit()
            print("Champions inserted successfully")
        except Error as e:
            print(f"The error '{e}' occurred")

    def init_matchups_table(self) -> None:
        self.execute_query("DROP TABLE IF EXISTS matchups")
        self.execute_query(
            """CREATE TABLE matchups (
            id INTEGER PRIMARY KEY,
            champion INTEGER NOT NULL,
            enemy INTEGER NOT NULL,
            winrate REAL NOT NULL,
            delta1 REAL NOT NULL,
            delta2 REAL NOT NULL,
            pickrate REAL NOT NULL,
            games INTEGER NOT NULL,
            FOREIGN KEY (champion) REFERENCES champions(id) ON DELETE CASCADE,
            FOREIGN KEY (enemy) REFERENCES champions(id) ON DELETE CASCADE
        )"""
        )
        # Create indexes for performance optimization
        self.create_database_indexes()

    def init_synergies_table(self) -> None:
        """Create or reset synergies table for champion synergy data.

        Drops existing synergies table and recreates it with proper schema
        and indexes. Structure mirrors matchups table but stores synergies
        WITH allies instead of matchups AGAINST enemies.
        """
        self.execute_query("DROP TABLE IF EXISTS synergies")
        self.execute_query(
            """CREATE TABLE synergies (
            id INTEGER PRIMARY KEY,
            champion INTEGER NOT NULL,
            ally INTEGER NOT NULL,
            winrate REAL NOT NULL,
            delta1 REAL NOT NULL,
            delta2 REAL NOT NULL,
            pickrate REAL NOT NULL,
            games INTEGER NOT NULL,
            FOREIGN KEY (champion) REFERENCES champions(id) ON DELETE CASCADE,
            FOREIGN KEY (ally) REFERENCES champions(id) ON DELETE CASCADE
        )"""
        )
        # Create indexes for performance optimization
        cursor = self.connection.cursor()
        cursor.execute("CREATE INDEX idx_synergies_champion ON synergies(champion)")
        cursor.execute("CREATE INDEX idx_synergies_ally ON synergies(ally)")
        cursor.execute("CREATE INDEX idx_synergies_pickrate ON synergies(pickrate)")
        cursor.execute(
            "CREATE INDEX idx_synergies_champion_pickrate ON synergies(champion, pickrate)"
        )
        cursor.execute("CREATE INDEX idx_synergies_ally_pickrate ON synergies(ally, pickrate)")

    def init_champion_scores_table(self) -> None:
        """Create or reset champion_scores table for tier list calculations."""
        self.execute_query("DROP TABLE IF EXISTS champion_scores")
        self.execute_query(
            """CREATE TABLE champion_scores (
            id INTEGER PRIMARY KEY,
            avg_delta2 REAL,
            variance REAL,
            coverage REAL,
            peak_impact REAL,
            volatility REAL,
            target_ratio REAL,
            FOREIGN KEY (id) REFERENCES champions(id) ON DELETE CASCADE
        )"""
        )

    def add_matchup(
        self,
        champion: str,
        enemy: str,
        winrate: float,
        delta1: float,
        delta2: float,
        pickrate: float,
        games: int,
    ) -> None:
        champ_id = self.get_champion_id(champion)
        enemy_id = self.get_champion_id(enemy)
        if (
            champ_id is None
            or enemy_id is None
            or winrate is None
            or delta1 is None
            or delta2 is None
            or pickrate is None
            or games is None
        ):
            print(f"{champ_id}, {enemy_id}, {winrate}, {delta1}, {delta2}, {pickrate}, {games}")
            return
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                "INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (champ_id, enemy_id, winrate, delta1, delta2, pickrate, games),
            )
            self.connection.commit()
            print(f"Query executed successfully : INSERT INTO matchups")
        except Error as e:
            print(f"The error '{e}' occurred")

    def get_champion_id(self, champion: str) -> int:
        """Get champion ID by name (for backward compatibility)."""
        cursor = self.connection.cursor()
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
        cursor = self.connection.cursor()
        try:
            cursor.execute("SELECT name FROM champions WHERE id = ?", (id,))
            # No commit needed for SELECT queries!
            result = cursor.fetchone()
            return result[0] if result else None
        except Error as e:
            print(f"The error '{e}' occurred")
            return None

    def get_champion_matchups(self, champion_id: int) -> List[tuple]:
        """Get matchups for a champion by Riot ID."""
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                "SELECT * FROM matchups WHERE champion = ? AND pickrate > 0.5", (champion_id,)
            )
            # No commit needed for SELECT queries!
            result = cursor.fetchall()
            # returns (enemy_id, winrate, delta1, delta2, pickrate, games)
            return [(elem[2], elem[3], elem[4], elem[5], elem[6], elem[7]) for elem in result]
        except Error as e:
            print(f"The error '{e}' occurred")
            return []

    def get_champion_matchups_by_name(
        self, champion_name: str, as_dataclass: bool = True
    ) -> Union[List[Matchup], List[tuple]]:
        """Get matchups for a champion by name with enemy names included.

        Args:
            champion_name: Name of the champion to get matchups for
            as_dataclass: If True, return Matchup objects. If False, return tuples.
                         Default True for new code. Use False for backward compatibility.

        Returns:
            List of Matchup objects or tuples (enemy_name, winrate, delta1, delta2, pickrate, games)

        Example:
            >>> # New way (dataclass - readable attributes)
            >>> matchups = db.get_champion_matchups_by_name("Jinx")
            >>> for m in matchups:
            ...     print(f"{m.enemy_name}: {m.winrate}% WR, {m.delta2} delta2")

            >>> # Old way (tuples - for backward compatibility)
            >>> matchups = db.get_champion_matchups_by_name("Jinx", as_dataclass=False)
            >>> for m in matchups:
            ...     print(f"{m[0]}: {m[1]}% WR, {m[3]} delta2")
        """
        champ_id = self.get_champion_id(champion_name)
        if champ_id is None:
            return []

        cursor = self.connection.cursor()
        try:
            # Join avec la table champions pour obtenir les noms des ennemis
            cursor.execute(
                """
                SELECT c.name, m.winrate, m.delta1, m.delta2, m.pickrate, m.games
                FROM matchups m
                JOIN champions c ON m.enemy = c.id
                WHERE m.champion = ? AND m.pickrate > 0.5
            """,
                (champ_id,),
            )
            result = cursor.fetchall()

            # Convert to dataclasses if requested (default)
            if as_dataclass:
                return [Matchup.from_tuple(row) for row in result]
            else:
                # Backward compatibility: return tuples
                return result
        except Error as e:
            print(f"The error '{e}' occurred")
            return []

    def get_champion_base_winrate(self, champion_name: str) -> float:
        """Calculate champion base winrate from all matchup data using weighted average."""
        matchups = self.get_champion_matchups_by_name(
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
            cursor = self.connection.cursor()
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

            self.connection.commit()

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
                self.connection.commit()
                print("[ERROR] No champions inserted, restored backup")
                return False

        except Exception as e:
            print(f"[ERROR] Error updating champions from Riot API: {e}")
            return False

    def create_riot_champions_table(self) -> bool:
        """Create/update champions table structure for Riot data."""
        try:
            cursor = self.connection.cursor()

            # Check if table exists and has the right structure
            cursor.execute("PRAGMA table_info(champions)")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]

            # If old structure, migrate
            if "key" not in column_names or "title" not in column_names:
                print("[INFO] Updating champions table structure...")

                # Create new table
                cursor.execute(
                    """
                    CREATE TABLE champions_new (
                        id INTEGER PRIMARY KEY,
                        key TEXT,
                        name TEXT NOT NULL,
                        title TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
                )

                # Migrate existing data if any
                cursor.execute("SELECT COUNT(*) FROM champions")
                if cursor.fetchone()[0] > 0:
                    try:
                        cursor.execute(
                            """
                            INSERT INTO champions_new (id, name) 
                            SELECT id, name FROM champions
                        """
                        )
                    except:
                        # If migration fails, that's ok - we'll update from Riot API anyway
                        pass

                # Replace old table
                cursor.execute("DROP TABLE champions")
                cursor.execute("ALTER TABLE champions_new RENAME TO champions")

            self.connection.commit()
            print("[INFO] Champions table structure verified")
            return True

        except Exception as e:
            print(f"[ERROR] Error creating champions table: {e}")
            return False

    def get_all_champion_names(self) -> Dict[int, str]:
        """Get mapping of all champion IDs to names."""
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT id, name FROM champions")
            return dict(cursor.fetchall())
        except Exception as e:
            print(f"[ERROR] Error getting champion names: {e}")
            return {}

    # === PERFORMANCE OPTIMIZED METHODS ===

    def build_champion_cache(self) -> Dict[str, int]:
        """Build cache of champion name -> ID mappings for faster lookups."""
        try:
            cursor = self.connection.cursor()
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

    def get_champion_matchups_for_draft(
        self, champion_name: str, as_dataclass: bool = True
    ) -> Union[List[MatchupDraft], List[tuple]]:
        """
        Optimized query for draft analysis - returns only the columns needed for draft calculations.

        This method returns 4 columns instead of 6 (33% reduction):
        - enemy_name (str): Enemy champion name
        - delta2 (float): Delta2 performance metric
        - pickrate (float): Matchup pickrate percentage
        - games (int): Number of games in sample

        Columns NOT included (not used in draft):
        - winrate: Only used in avg_winrate() which is never called during draft
        - delta1: Only used in legacy generate_by_delta1() tier list method

        Args:
            champion_name: Name of the champion to get matchups for
            as_dataclass: If True, return MatchupDraft objects. If False, return tuples.
                         Default True for new code. Use False for backward compatibility.

        Returns:
            List of MatchupDraft objects or tuples: [(enemy_name, delta2, pickrate, games), ...]
            Empty list if champion not found or no matchups

        Example:
            >>> # New way (dataclass - readable attributes)
            >>> matchups = db.get_champion_matchups_for_draft("Jinx")
            >>> for m in matchups:
            ...     print(f"{m.enemy_name}: {m.delta2} delta2, {m.games} games")

            >>> # Old way (tuples - for backward compatibility)
            >>> matchups = db.get_champion_matchups_for_draft("Jinx", as_dataclass=False)
            >>> for m in matchups:
            ...     print(f"{m[0]}: {m[1]} delta2, {m[3]} games")
        """
        champ_id = self.get_champion_id(champion_name)
        if champ_id is None:
            return []

        cursor = self.connection.cursor()
        try:
            # Optimized query: only 4 columns needed for draft analysis
            cursor.execute(
                """
                SELECT c.name, m.delta2, m.pickrate, m.games
                FROM matchups m
                JOIN champions c ON m.enemy = c.id
                WHERE m.champion = ? AND m.pickrate > 0.5
            """,
                (champ_id,),
            )
            result = cursor.fetchall()

            # Convert to dataclasses if requested (default)
            if as_dataclass:
                return [MatchupDraft.from_tuple(row) for row in result]
            else:
                # Backward compatibility: return tuples
                return result
        except Error as e:
            print(f"The error '{e}' occurred")
            return []

    def add_matchups_batch(
        self, matchup_data: List[tuple], champion_cache: Dict[str, int] = None
    ) -> int:
        """
        Add multiple matchups in a single transaction for much better performance.

        Args:
            matchup_data: List of tuples (champion_name, enemy_name, winrate, delta1, delta2, pickrate, games)
            champion_cache: Optional pre-built cache of champion name->ID mappings

        Returns:
            Number of matchups successfully inserted
        """
        if not matchup_data:
            return 0

        # Build cache if not provided
        if champion_cache is None:
            champion_cache = self.build_champion_cache()

        try:
            cursor = self.connection.cursor()

            # Prepare data for batch insert
            batch_data = []
            skipped = 0

            for champion, enemy, winrate, delta1, delta2, pickrate, games in matchup_data:
                # Get IDs from cache (much faster than individual queries)
                champ_id = champion_cache.get(champion) or champion_cache.get(champion.lower())
                enemy_id = champion_cache.get(enemy) or champion_cache.get(enemy.lower())

                if (
                    champ_id
                    and enemy_id
                    and all(x is not None for x in [winrate, delta1, delta2, pickrate, games])
                ):
                    batch_data.append(
                        (champ_id, enemy_id, winrate, delta1, delta2, pickrate, games)
                    )
                else:
                    skipped += 1
                    if self.connection.total_changes % 100 == 0:  # Occasional debug
                        print(
                            f"[DEBUG] Skipped matchup: {champion} vs {enemy} (missing data or IDs)"
                        )

            if not batch_data:
                print(f"[WARNING] No valid matchups to insert from {len(matchup_data)} provided")
                return 0

            # Single transaction with batch insert (much faster!)
            cursor.executemany(
                """
                INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                batch_data,
            )
            self.connection.commit()

            inserted = len(batch_data)
            if skipped > 0:
                print(f"[INFO] Inserted {inserted} matchups, skipped {skipped}")

            return inserted

        except Exception as e:
            try:
                self.connection.rollback()
            except:
                pass
            print(f"[ERROR] Batch insert failed: {e}")
            return 0

    def clear_matchups_for_champion(
        self, champion_name: str, champion_cache: Dict[str, int] = None
    ) -> bool:
        """Clear existing matchups for a champion before inserting new data."""
        try:
            if champion_cache is None:
                champ_id = self.get_champion_id(champion_name)
            else:
                champ_id = champion_cache.get(champion_name) or champion_cache.get(
                    champion_name.lower()
                )

            if not champ_id:
                print(f"[WARNING] Champion not found: {champion_name}")
                return False

            cursor = self.connection.cursor()
            cursor.execute("DELETE FROM matchups WHERE champion = ?", (champ_id,))
            deleted = cursor.rowcount

            if deleted > 0:
                print(f"[INFO] Cleared {deleted} existing matchups for {champion_name}")

            return True

        except Exception as e:
            print(f"[ERROR] Error clearing matchups for {champion_name}: {e}")
            return False

    def get_matchup_delta2(self, champion_name: str, enemy_name: str) -> Optional[float]:
        """
        Get delta2 value for a specific matchup using direct SQL query.

        Aggregates multi-lane matchup data using weighted average by games.
        Optimized for reverse lookup approach - avoids loading all matchups.

        Args:
            champion_name: Name of our champion
            enemy_name: Name of enemy champion

        Returns:
            Weighted average delta2 value if matchup exists with sufficient data, None otherwise
        """
        try:
            cursor = self.connection.cursor()

            # Direct SQL join - aggregation done in Python for consistency
            cursor.execute(
                """
                SELECT m.delta2, m.games
                FROM matchups m
                JOIN champions c1 ON m.champion = c1.id
                JOIN champions c2 ON m.enemy = c2.id
                WHERE c1.name = ? COLLATE NOCASE
                AND c2.name = ? COLLATE NOCASE
                AND m.pickrate >= 0.5
                AND m.games >= 200
            """,
                (champion_name, enemy_name),
            )

            rows = cursor.fetchall()
            if not rows:
                return None

            # Python aggregation: weighted average by games
            # Formula: SUM(delta2 * games) / SUM(games)
            total_weighted = sum(row[0] * row[1] for row in rows)
            total_games = sum(row[1] for row in rows)

            return total_weighted / total_games if total_games > 0 else None

        except Exception as e:
            # Always log database errors - these are unexpected and need visibility
            print(f"[ERROR] Database error getting matchup {champion_name} vs {enemy_name}: {e}")
            return None

    def get_all_matchups_bulk(self) -> dict:
        """
        Load ALL valid matchups in a single SQL query for caching.

        Returns dict mapping (champion_name, enemy_name) -> delta2 value.
        Only includes matchups meeting quality thresholds (pickrate >= 0.5%, games >= 200).

        This is much faster than calling get_matchup_delta2() repeatedly.
        Use this for bulk operations like holistic optimizer.

        Returns:
            Dict with keys as tuples (champion_name, enemy_name) and values as delta2 floats
        """
        try:
            cursor = self.connection.cursor()

            # Load all valid matchups in one query
            cursor.execute(
                """
                SELECT c1.name, c2.name, m.delta2
                FROM matchups m
                JOIN champions c1 ON m.champion = c1.id
                JOIN champions c2 ON m.enemy = c2.id
                WHERE m.pickrate >= 0.5
                AND m.games >= 200
            """
            )

            # Build cache dictionary
            matchup_cache = {}
            for champion_name, enemy_name, delta2 in cursor.fetchall():
                # Normalize to lowercase for case-insensitive lookup
                key = (champion_name.lower(), enemy_name.lower())
                matchup_cache[key] = float(delta2)

            return matchup_cache

        except Exception as e:
            print(f"[ERROR] Failed to load bulk matchups: {e}")
            return {}

    # ========== Synergies Methods ==========

    def add_synergy(
        self,
        champion: str,
        ally: str,
        winrate: float,
        delta1: float,
        delta2: float,
        pickrate: float,
        games: int,
    ) -> None:
        """Add synergy data between champion and ally.

        Args:
            champion: Name of the champion
            ally: Name of the allied champion
            winrate: Win rate percentage with this ally (0.0-100.0)
            delta1: First performance delta metric
            delta2: Second performance delta metric
            pickrate: Pick rate percentage of this ally combination
            games: Number of games with this synergy
        """
        champ_id = self.get_champion_id(champion)
        ally_id = self.get_champion_id(ally)
        if (
            champ_id is None
            or ally_id is None
            or winrate is None
            or delta1 is None
            or delta2 is None
            or pickrate is None
            or games is None
        ):
            print(
                f"[WARNING] Invalid synergy data: {champ_id}, {ally_id}, {winrate}, {delta1}, {delta2}, {pickrate}, {games}"
            )
            return
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                "INSERT INTO synergies (champion, ally, winrate, delta1, delta2, pickrate, games) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (champ_id, ally_id, winrate, delta1, delta2, pickrate, games),
            )
            self.connection.commit()
            print(f"Query executed successfully : INSERT INTO synergies")
        except Error as e:
            print(f"The error '{e}' occurred")

    def get_champion_synergies_by_name(
        self, champion_name: str, as_dataclass: bool = True
    ) -> Union[List["Synergy"], List[tuple]]:
        """Get synergies for a champion by name with ally names included.

        Args:
            champion_name: Name of the champion to get synergies for
            as_dataclass: If True, return Synergy objects. If False, return tuples.
                         Default True for new code. Use False for backward compatibility.

        Returns:
            List of Synergy objects or tuples (ally_name, winrate, delta1, delta2, pickrate, games)

        Example:
            >>> # New way (dataclass - readable attributes)
            >>> synergies = db.get_champion_synergies_by_name("Yasuo")
            >>> for s in synergies:
            ...     print(f"With {s.ally_name}: {s.winrate}% WR, {s.delta2} delta2")

            >>> # Old way (tuples - for backward compatibility)
            >>> synergies = db.get_champion_synergies_by_name("Yasuo", as_dataclass=False)
            >>> for s in synergies:
            ...     print(f"With {s[0]}: {s[1]}% WR, {s[3]} delta2")
        """
        champ_id = self.get_champion_id(champion_name)
        if champ_id is None:
            return []

        cursor = self.connection.cursor()
        try:
            # Join avec la table champions pour obtenir les noms des alliés
            cursor.execute(
                """
                SELECT c.name, s.winrate, s.delta1, s.delta2, s.pickrate, s.games
                FROM synergies s
                JOIN champions c ON s.ally = c.id
                WHERE s.champion = ? AND s.pickrate > 0.5
            """,
                (champ_id,),
            )
            result = cursor.fetchall()

            # Convert to dataclasses if requested (default)
            if as_dataclass:
                return [Synergy.from_tuple(row) for row in result]
            else:
                # Backward compatibility: return tuples
                return result

        except Error as e:
            print(f"The error '{e}' occurred")
            return []

    def add_synergies_batch(
        self, synergies: List[Tuple[str, str, float, float, float, float, int]]
    ) -> None:
        """Batch insert synergies for performance.

        Args:
            synergies: List of tuples (champion, ally, winrate, delta1, delta2, pickrate, games)
        """
        cursor = self.connection.cursor()
        try:
            # Convert champion/ally names to IDs
            synergy_data = []
            for champion, ally, winrate, delta1, delta2, pickrate, games in synergies:
                champ_id = self.get_champion_id(champion)
                ally_id = self.get_champion_id(ally)
                if champ_id and ally_id:
                    synergy_data.append(
                        (champ_id, ally_id, winrate, delta1, delta2, pickrate, games)
                    )

            # Batch insert
            cursor.executemany(
                "INSERT INTO synergies (champion, ally, winrate, delta1, delta2, pickrate, games) VALUES (?, ?, ?, ?, ?, ?, ?)",
                synergy_data,
            )
            self.connection.commit()
            print(f"Batch insert successful: {len(synergy_data)} synergies added")
        except Error as e:
            print(f"The error '{e}' occurred during batch synergy insert")

    def clear_synergies_for_champion(self, champion_name: str) -> None:
        """Clear all synergies for a specific champion.

        Used before re-parsing champion synergies to avoid duplicates.

        Args:
            champion_name: Name of the champion to clear synergies for
        """
        champ_id = self.get_champion_id(champion_name)
        if champ_id is None:
            print(f"[WARNING] Champion '{champion_name}' not found, cannot clear synergies")
            return

        cursor = self.connection.cursor()
        try:
            cursor.execute("DELETE FROM synergies WHERE champion = ?", (champ_id,))
            self.connection.commit()
            deleted = cursor.rowcount
            print(f"Deleted {deleted} synergies for {champion_name}")
        except Error as e:
            print(f"The error '{e}' occurred")

    def get_synergy_delta2(self, champion_name: str, ally_name: str) -> Optional[float]:
        """Get delta2 value for a specific champion-ally synergy.

        Args:
            champion_name: Name of the champion
            ally_name: Name of the allied champion

        Returns:
            delta2 value if synergy exists, None otherwise
        """
        champ_id = self.get_champion_id(champion_name)
        ally_id = self.get_champion_id(ally_name)

        if champ_id is None or ally_id is None:
            return None

        try:
            cursor = self.connection.cursor()
            cursor.execute(
                """
                SELECT delta2
                FROM synergies
                WHERE champion = ? AND ally = ?
                AND pickrate >= 0.5
                AND games >= 200
            """,
                (champ_id, ally_id),
            )

            result = cursor.fetchone()
            if result:
                return float(result[0])
            else:
                return None

        except Exception as e:
            print(f"[ERROR] Database error getting synergy {champion_name} with {ally_name}: {e}")
            return None

    def get_all_synergies_bulk(self) -> dict:
        """Load ALL valid synergies in a single SQL query for caching.

        Returns dict mapping (champion_name, ally_name) -> delta2 value.
        Only includes synergies meeting quality thresholds (pickrate >= 0.5%, games >= 200).

        This is much faster than calling get_synergy_delta2() repeatedly.
        Use this for bulk operations like draft optimization.

        Returns:
            Dict with keys as tuples (champion_name, ally_name) and values as delta2 floats
        """
        try:
            cursor = self.connection.cursor()

            # Load all valid synergies in one query
            cursor.execute(
                """
                SELECT c1.name, c2.name, s.delta2
                FROM synergies s
                JOIN champions c1 ON s.champion = c1.id
                JOIN champions c2 ON s.ally = c2.id
                WHERE s.pickrate >= 0.5
                AND s.games >= 200
            """
            )

            # Build cache dictionary
            synergy_cache = {}
            for champion_name, ally_name, delta2 in cursor.fetchall():
                # Normalize to lowercase for case-insensitive lookup
                key = (champion_name.lower(), ally_name.lower())
                synergy_cache[key] = float(delta2)

            return synergy_cache

        except Exception as e:
            print(f"[ERROR] Failed to load bulk synergies: {e}")
            return {}

    # ========== Champion Scores Methods ==========

    def save_champion_scores(
        self,
        champion_id: int,
        avg_delta2: float,
        variance: float,
        coverage: float,
        peak_impact: float,
        volatility: float,
        target_ratio: float,
    ) -> None:
        """Save or update champion scores in the database."""
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                """
                INSERT OR REPLACE INTO champion_scores
                (id, avg_delta2, variance, coverage, peak_impact, volatility, target_ratio)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    champion_id,
                    avg_delta2,
                    variance,
                    coverage,
                    peak_impact,
                    volatility,
                    target_ratio,
                ),
            )
            self.connection.commit()
        except Error as e:
            print(f"Error saving champion scores for ID {champion_id}: {e}")

    def get_champion_scores(self, champion_id: int) -> Optional[Dict[str, float]]:
        """Get champion scores by champion ID."""
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                """
                SELECT avg_delta2, variance, coverage, peak_impact, volatility, target_ratio
                FROM champion_scores WHERE id = ?
            """,
                (champion_id,),
            )
            result = cursor.fetchone()

            if result:
                return {
                    "avg_delta2": result[0],
                    "variance": result[1],
                    "coverage": result[2],
                    "peak_impact": result[3],
                    "volatility": result[4],
                    "target_ratio": result[5],
                }
            return None
        except Error as e:
            print(f"Error getting champion scores for ID {champion_id}: {e}")
            return None

    def get_champion_scores_by_name(self, champion_name: str) -> Optional[Dict[str, float]]:
        """Get champion scores by champion name."""
        champion_id = self.get_champion_id(champion_name)
        if champion_id is None:
            return None
        return self.get_champion_scores(champion_id)

    def get_all_champion_scores(self) -> List[tuple]:
        """Get all champion scores with champion names."""
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                """
                SELECT c.name, cs.avg_delta2, cs.variance, cs.coverage,
                       cs.peak_impact, cs.volatility, cs.target_ratio
                FROM champion_scores cs
                JOIN champions c ON cs.id = c.id
                ORDER BY c.name
            """
            )
            return cursor.fetchall()
        except Error as e:
            print(f"Error getting all champion scores: {e}")
            return []

    def champion_scores_table_exists(self) -> bool:
        """Check if champion_scores table exists and has data."""
        cursor = self.connection.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM champion_scores")
            count = cursor.fetchone()[0]
            return count > 0
        except Error:
            return False

    # ========== Pool Ban Recommendations Methods ==========

    def init_pool_ban_recommendations_table(self) -> None:
        """Create or reset pool_ban_recommendations table for pre-calculated bans."""
        self.execute_query("DROP TABLE IF EXISTS pool_ban_recommendations")
        self.execute_query(
            """CREATE TABLE pool_ban_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pool_name TEXT NOT NULL,
            enemy_champion TEXT NOT NULL,
            threat_score REAL NOT NULL,
            best_response_delta2 REAL NOT NULL,
            best_response_champion TEXT NOT NULL,
            matchups_count INTEGER NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(pool_name, enemy_champion)
        )"""
        )

        # Create indexes for fast lookups
        cursor = self.connection.cursor()
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_pool_bans_pool ON pool_ban_recommendations(pool_name)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_pool_bans_threat ON pool_ban_recommendations(pool_name, threat_score DESC)"
        )
        self.connection.commit()
        print("[INFO] Created pool_ban_recommendations table with indexes")

    def save_pool_ban_recommendations(self, pool_name: str, ban_data: List[tuple]) -> int:
        """
        Save pre-calculated ban recommendations for a champion pool.

        Args:
            pool_name: Name of the champion pool
            ban_data: List of tuples (enemy_champion, threat_score, best_response_delta2,
                                      best_response_champion, matchups_count)

        Returns:
            Number of ban recommendations saved
        """
        if not ban_data:
            return 0

        try:
            cursor = self.connection.cursor()

            # Delete existing recommendations for this pool
            cursor.execute("DELETE FROM pool_ban_recommendations WHERE pool_name = ?", (pool_name,))

            # Insert new recommendations
            cursor.executemany(
                """
                INSERT INTO pool_ban_recommendations
                (pool_name, enemy_champion, threat_score, best_response_delta2,
                 best_response_champion, matchups_count)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                [
                    (pool_name, enemy, threat, delta2, response, count)
                    for enemy, threat, delta2, response, count in ban_data
                ],
            )

            self.connection.commit()
            return len(ban_data)

        except Exception as e:
            print(f"[ERROR] Failed to save ban recommendations for {pool_name}: {e}")
            try:
                self.connection.rollback()
            except:
                pass
            return 0

    def get_pool_ban_recommendations(self, pool_name: str, limit: int = 5) -> List[tuple]:
        """
        Get pre-calculated ban recommendations for a champion pool.

        Args:
            pool_name: Name of the champion pool
            limit: Maximum number of recommendations to return

        Returns:
            List of tuples (enemy_champion, threat_score, best_response_delta2,
                           best_response_champion, matchups_count)
            Sorted by threat_score descending
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                """
                SELECT enemy_champion, threat_score, best_response_delta2,
                       best_response_champion, matchups_count
                FROM pool_ban_recommendations
                WHERE pool_name = ?
                ORDER BY threat_score DESC
                LIMIT ?
                """,
                (pool_name, limit),
            )

            return cursor.fetchall()

        except Error as e:
            print(f"[ERROR] Failed to get ban recommendations for {pool_name}: {e}")
            return []

    def pool_has_ban_recommendations(self, pool_name: str) -> bool:
        """Check if a pool has pre-calculated ban recommendations."""
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                """
                SELECT COUNT(*) FROM pool_ban_recommendations
                WHERE pool_name = ?
                """,
                (pool_name,),
            )
            count = cursor.fetchone()[0]
            return count > 0
        except Error:
            return False

    def clear_pool_ban_recommendations(self, pool_name: str = None) -> int:
        """
        Clear ban recommendations for a pool or all pools.

        Args:
            pool_name: Pool name to clear, or None to clear all

        Returns:
            Number of recommendations deleted
        """
        cursor = self.connection.cursor()
        try:
            if pool_name:
                cursor.execute(
                    "DELETE FROM pool_ban_recommendations WHERE pool_name = ?", (pool_name,)
                )
            else:
                cursor.execute("DELETE FROM pool_ban_recommendations")

            deleted = cursor.rowcount
            self.connection.commit()
            return deleted

        except Error as e:
            print(f"[ERROR] Failed to clear ban recommendations: {e}")
            return 0
