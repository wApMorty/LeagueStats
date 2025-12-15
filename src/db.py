import sqlite3
from sqlite3 import Error
from typing import List, Optional, Dict
import requests
from .constants import CHAMPIONS_LIST

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
        self.connection.close()

    def create_database_indexes(self) -> None:
        """Create database indexes for performance optimization."""
        print("[INFO] Creating database indexes for performance optimization...")
        cursor = self.connection.cursor()

        try:
            # Check if tables exist before creating indexes
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('champions', 'matchups')")
            existing_tables = {row[0] for row in cursor.fetchall()}

            if 'champions' in existing_tables:
                # Index on champions.name for faster name lookups
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_champions_name ON champions(name)")
                print("[INFO]   - Created index: idx_champions_name")

            if 'matchups' in existing_tables:
                # Indexes on matchups table for faster queries
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_matchups_champion ON matchups(champion)")
                print("[INFO]   - Created index: idx_matchups_champion")

                cursor.execute("CREATE INDEX IF NOT EXISTS idx_matchups_enemy ON matchups(enemy)")
                print("[INFO]   - Created index: idx_matchups_enemy")

                cursor.execute("CREATE INDEX IF NOT EXISTS idx_matchups_pickrate ON matchups(pickrate)")
                print("[INFO]   - Created index: idx_matchups_pickrate")

                # Composite index for common query pattern (champion + pickrate filter)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_matchups_champion_pickrate ON matchups(champion, pickrate)")
                print("[INFO]   - Created index: idx_matchups_champion_pickrate")

                # Composite index for reverse lookups (enemy + pickrate)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_matchups_enemy_pickrate ON matchups(enemy, pickrate)")
                print("[INFO]   - Created index: idx_matchups_enemy_pickrate")

            self.connection.commit()
            print("[INFO] Database indexes created successfully")
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
        print("[WARNING] Using legacy init_champion_table(). Consider using Riot API integration instead.")
        self.execute_query("DROP TABLE IF EXISTS champions")
        # Reset auto-increment counter
        self.execute_query("DELETE FROM sqlite_sequence WHERE name='champions'")
        self.execute_query("CREATE TABLE champions (id INTEGER PRIMARY KEY, champion TEXT NOT NULL)")

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
        self.execute_query("""CREATE TABLE matchups (
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
        )""")
        # Create indexes for performance optimization
        self.create_database_indexes()

    def init_champion_scores_table(self) -> None:
        """Create or reset champion_scores table for tier list calculations."""
        self.execute_query("DROP TABLE IF EXISTS champion_scores")
        self.execute_query("""CREATE TABLE champion_scores (
            id INTEGER PRIMARY KEY,
            avg_delta2 REAL,
            variance REAL,
            coverage REAL,
            peak_impact REAL,
            volatility REAL,
            target_ratio REAL,
            FOREIGN KEY (id) REFERENCES champions(id) ON DELETE CASCADE
        )""")

    def add_matchup(self, champion: str, enemy: str, winrate: float, delta1: float, delta2: float, pickrate: float, games: int) -> None:
        champ_id = self.get_champion_id(champion)
        enemy_id = self.get_champion_id(enemy)
        if champ_id is None or enemy_id is None or winrate is None or delta1 is None or delta2 is None or pickrate is None or games is None :
            print(f"{champ_id}, {enemy_id}, {winrate}, {delta1}, {delta2}, {pickrate}, {games}")
            return
        cursor = self.connection.cursor()
        try:
            cursor.execute("INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (champ_id, enemy_id, winrate, delta1, delta2, pickrate, games))
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
            cursor.execute("SELECT * FROM matchups WHERE champion = ? AND pickrate > 0.5", (champion_id,))
            # No commit needed for SELECT queries!
            result = cursor.fetchall()
            # returns (enemy_id, winrate, delta1, delta2, pickrate, games)
            return [(elem[2], elem[3], elem[4], elem[5], elem[6], elem[7]) for elem in result]
        except Error as e:
            print(f"The error '{e}' occurred")
            return []
    
    def get_champion_matchups_by_name(self, champion_name: str) -> List[tuple]:
        """Get matchups for a champion by name with enemy names included."""
        champ_id = self.get_champion_id(champion_name)
        if champ_id is None:
            return []

        cursor = self.connection.cursor()
        try:
            # Join avec la table champions pour obtenir les noms des ennemis
            cursor.execute("""
                SELECT c.name, m.winrate, m.delta1, m.delta2, m.pickrate, m.games
                FROM matchups m
                JOIN champions c ON m.enemy = c.id
                WHERE m.champion = ? AND m.pickrate > 0.5
            """, (champ_id,))
            result = cursor.fetchall()
            # returns (enemy_name, winrate, delta1, delta2, pickrate, games)
            return result
        except Error as e:
            print(f"The error '{e}' occurred")
            return []
    
    def get_champion_base_winrate(self, champion_name: str) -> float:
        """Calculate champion base winrate from all matchup data using weighted average."""
        matchups = self.get_champion_matchups_by_name(champion_name)
        if not matchups:
            return 50.0  # Default to 50% if no data
        
        total_weighted_winrate = 0.0
        total_weight = 0.0
        
        for enemy_name, winrate, delta1, delta2, pickrate, games in matchups:
            # Use games as weight (more games = more reliable data)
            # Could also use pickrate or combination of both
            weight = games
            total_weighted_winrate += winrate * weight
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
            version_url = 'https://ddragon.leagueoflegends.com/api/versions.json'
            response = requests.get(version_url, timeout=10)
            if response.status_code != 200:
                print(f"[ERROR] Failed to get version info: {response.status_code}")
                return False
            
            latest_version = response.json()[0]
            print(f"[INFO] Using game version: {latest_version}")
            
            # Get champion data
            champion_url = f'https://ddragon.leagueoflegends.com/cdn/{latest_version}/data/en_US/champion.json'
            response = requests.get(champion_url, timeout=30)
            if response.status_code != 200:
                print(f"[ERROR] Failed to get champion data: {response.status_code}")
                return False
            
            champions_data = response.json()
            if 'data' not in champions_data:
                print("[ERROR] Invalid champion data format")
                return False
            
            # Create backup of existing champions table
            cursor = self.connection.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS champions_backup AS SELECT * FROM champions WHERE 1=0")
            cursor.execute("INSERT INTO champions_backup SELECT * FROM champions")
            
            # Clear existing champions AND matchups (to avoid orphaned references)
            cursor.execute("DELETE FROM matchups")  # Clear matchups first (foreign keys)
            cursor.execute("DELETE FROM champions")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='champions'")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='matchups'")
            
            # Insert new champion data
            champions_inserted = 0
            for key, champ_data in champions_data['data'].items():
                try:
                    riot_id = int(champ_data['key'])
                    display_name = champ_data['name']  # Keep for reference
                    title = champ_data.get('title', '')
                    
                    # Use the key as name for consistency with constants.py
                    # This ensures champion names match our normalized format
                    cursor.execute('''
                        INSERT INTO champions (id, key, name, title) 
                        VALUES (?, ?, ?, ?)
                    ''', (riot_id, key, key, title))
                    
                    champions_inserted += 1
                    
                except (KeyError, ValueError) as e:
                    print(f"[WARNING] Error processing champion {key}: {e}")
                    continue
            
            self.connection.commit()
            
            # Verify insertion
            cursor.execute('SELECT COUNT(*) FROM champions')
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
            if 'key' not in column_names or 'title' not in column_names:
                print("[INFO] Updating champions table structure...")
                
                # Create new table
                cursor.execute('''
                    CREATE TABLE champions_new (
                        id INTEGER PRIMARY KEY,
                        key TEXT,
                        name TEXT NOT NULL,
                        title TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Migrate existing data if any
                cursor.execute("SELECT COUNT(*) FROM champions")
                if cursor.fetchone()[0] > 0:
                    try:
                        cursor.execute('''
                            INSERT INTO champions_new (id, name) 
                            SELECT id, name FROM champions
                        ''')
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
            cursor.execute('SELECT id, name FROM champions')
            return dict(cursor.fetchall())
        except Exception as e:
            print(f"[ERROR] Error getting champion names: {e}")
            return {}
    
    # === PERFORMANCE OPTIMIZED METHODS ===
    
    def build_champion_cache(self) -> Dict[str, int]:
        """Build cache of champion name -> ID mappings for faster lookups."""
        try:
            cursor = self.connection.cursor()
            cursor.execute('SELECT name, id FROM champions')
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
    
    def add_matchups_batch(self, matchup_data: List[tuple], champion_cache: Dict[str, int] = None) -> int:
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
                
                if champ_id and enemy_id and all(x is not None for x in [winrate, delta1, delta2, pickrate, games]):
                    batch_data.append((champ_id, enemy_id, winrate, delta1, delta2, pickrate, games))
                else:
                    skipped += 1
                    if self.connection.total_changes % 100 == 0:  # Occasional debug
                        print(f"[DEBUG] Skipped matchup: {champion} vs {enemy} (missing data or IDs)")
            
            if not batch_data:
                print(f"[WARNING] No valid matchups to insert from {len(matchup_data)} provided")
                return 0
            
            # Single transaction with batch insert (much faster!)
            cursor.executemany('''
                INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', batch_data)
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
    
    def clear_matchups_for_champion(self, champion_name: str, champion_cache: Dict[str, int] = None) -> bool:
        """Clear existing matchups for a champion before inserting new data."""
        try:
            if champion_cache is None:
                champ_id = self.get_champion_id(champion_name)
            else:
                champ_id = champion_cache.get(champion_name) or champion_cache.get(champion_name.lower())
            
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
        
        Optimized for reverse lookup approach - avoids loading all matchups.
        
        Args:
            champion_name: Name of our champion
            enemy_name: Name of enemy champion
            
        Returns:
            delta2 value if matchup exists with sufficient data, None otherwise
        """
        try:
            cursor = self.connection.cursor()
            
            # Direct SQL join to get delta2 for specific matchup
            cursor.execute("""
                SELECT m.delta2, m.pickrate, m.games
                FROM matchups m
                JOIN champions c1 ON m.champion = c1.id  
                JOIN champions c2 ON m.enemy = c2.id
                WHERE c1.name = ? COLLATE NOCASE 
                AND c2.name = ? COLLATE NOCASE
                AND m.pickrate >= 0.5
                AND m.games >= 200
            """, (champion_name, enemy_name))
            
            result = cursor.fetchone()
            
            if result:
                delta2, pickrate, games = result
                return float(delta2)
            else:
                return None

        except Exception as e:
            if hasattr(self, 'verbose') and self.verbose:
                print(f"[DEBUG] Error getting matchup {champion_name} vs {enemy_name}: {e}")
            return None

    # ========== Champion Scores Methods ==========

    def save_champion_scores(self, champion_id: int, avg_delta2: float, variance: float,
                            coverage: float, peak_impact: float, volatility: float,
                            target_ratio: float) -> None:
        """Save or update champion scores in the database."""
        cursor = self.connection.cursor()
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO champion_scores
                (id, avg_delta2, variance, coverage, peak_impact, volatility, target_ratio)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (champion_id, avg_delta2, variance, coverage, peak_impact, volatility, target_ratio))
            self.connection.commit()
        except Error as e:
            print(f"Error saving champion scores for ID {champion_id}: {e}")

    def get_champion_scores(self, champion_id: int) -> Optional[Dict[str, float]]:
        """Get champion scores by champion ID."""
        cursor = self.connection.cursor()
        try:
            cursor.execute("""
                SELECT avg_delta2, variance, coverage, peak_impact, volatility, target_ratio
                FROM champion_scores WHERE id = ?
            """, (champion_id,))
            result = cursor.fetchone()

            if result:
                return {
                    'avg_delta2': result[0],
                    'variance': result[1],
                    'coverage': result[2],
                    'peak_impact': result[3],
                    'volatility': result[4],
                    'target_ratio': result[5]
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
            cursor.execute("""
                SELECT c.name, cs.avg_delta2, cs.variance, cs.coverage,
                       cs.peak_impact, cs.volatility, cs.target_ratio
                FROM champion_scores cs
                JOIN champions c ON cs.id = c.id
                ORDER BY c.name
            """)
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