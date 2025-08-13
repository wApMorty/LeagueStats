import sqlite3
from sqlite3 import Error
from typing import List, Optional, Dict
import requests
from constants import CHAMPIONS_LIST

class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self.connection = None

    def connect(self) -> None:
        try:
            self.connection = sqlite3.connect(self.path)
            print("Connection to SQLite DB successful")
        except Error as e:
            print(f"The error '{e}' occurred")

    def close(self) -> None:
        self.connection.close()

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
        self.execute_query("DROP TABLE IF EXISTS champions")
        self.execute_query("CREATE TABLE champions (id INTEGER PRIMARY KEY, champion TEXT NOT NULL)")
        
        for champ in CHAMPIONS_LIST:
            self.execute_query(f"INSERT INTO champions (champion) VALUES ('{champ}')")

    def init_matchups_table(self) -> None:
        self.execute_query("DROP TABLE IF EXISTS matchups")
        self.execute_query("CREATE TABLE matchups (id INTEGER PRIMARY KEY, champion INTEGER NOT NULL, enemy INTEGER NOT NULL, winrate REAL NOT NULL, delta1 REAL NOT NULL, delta2 REAL NOT NULL, pickrate REAL NOT NULL, games INTEGER NOT NULL)")

    def add_matchup(self, champion: str, enemy: str, winrate: float, delta1: float, delta2: float, pickrate: float, games: int) -> None:
        champ_id = self.get_champion_id(champion)
        enemy_id = self.get_champion_id(enemy)
        if champ_id is None or enemy_id is None or winrate is None or delta1 is None or delta2 is None or pickrate is None or games is None :
            print(f"{champ_id}, {enemy_id}, {winrate}, {delta1}, {delta2}, {pickrate}, {games}")
            return
        self.execute_query(f"INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games) VALUES ({champ_id}, {enemy_id}, {winrate}, {delta1}, {delta2}, {pickrate}, {games})")

    def get_champion_id(self, champion: str) -> int:
        """Get champion ID by name (for backward compatibility)."""
        cursor = self.connection.cursor()
        try:
            cursor.execute(f"SELECT id FROM champions WHERE name = '{champion}' COLLATE NOCASE")
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
            cursor.execute(f"SELECT name FROM champions WHERE id = {id}")
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
            cursor.execute(f"SELECT * FROM matchups WHERE champion = {champion_id} AND pickrate > 0.5")
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
            cursor.execute(f"""
                SELECT c.name, m.winrate, m.delta1, m.delta2, m.pickrate, m.games 
                FROM matchups m
                JOIN champions c ON m.enemy = c.id
                WHERE m.champion = {champ_id} AND m.pickrate > 0.5
            """)
            result = cursor.fetchall()
            # returns (enemy_name, winrate, delta1, delta2, pickrate, games)
            return result
        except Error as e:
            print(f"The error '{e}' occurred")
            return []
    
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
            
            # Clear existing champions
            cursor.execute("DELETE FROM champions")
            
            # Insert new champion data
            champions_inserted = 0
            for key, champ_data in champions_data['data'].items():
                try:
                    riot_id = int(champ_data['key'])
                    name = champ_data['name']
                    title = champ_data.get('title', '')
                    
                    cursor.execute('''
                        INSERT INTO champions (id, key, name, title) 
                        VALUES (?, ?, ?, ?)
                    ''', (riot_id, key, name, title))
                    
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
                cursor.execute("DELETE FROM champions")
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
            
            # Web scraping name -> Riot official name mapping
            web_to_riot_mapping = {
                # Common format differences
                'ksante': "K'Sante",
                'drmundo': "Dr. Mundo", 
                'chogath': "Cho'Gath",
                'leesin': "Lee Sin",
                'jarvaniv': "Jarvan IV",
                'xinzhao': "Xin Zhao",
                'khazix': "Kha'Zix",
                'masteryi': "Master Yi",
                'reksai': "Rek'Sai",
                'belveth': "Bel'Veth",
                'nunu': "Nunu & Willump",
                'twistedfate': "Twisted Fate",
                'aurelionsol': "Aurelion Sol", 
                'velkoz': "Vel'Koz",
                'kaisa': "Kai'Sa",
                'missfortune': "Miss Fortune",
                'kogmaw': "Kog'Maw",
                'renata': "Renata Glasc",
                'tahmkench': "Tahm Kench",
                'leblanc': "LeBlanc",
                'wukong': "Wukong",  # Sometimes called MonkeyKing in old data
                'monkeyking': "Wukong",
                
                # Additional mappings that might be needed
                'fiddlesticks': "Fiddlesticks",
                'mundo': "Dr. Mundo",
                'yi': "Master Yi",
                'tf': "Twisted Fate",
                'asol': "Aurelion Sol",
                'mf': "Miss Fortune",
                'tk': "Tahm Kench",
                'lb': "LeBlanc",
                'j4': "Jarvan IV",
                'xin': "Xin Zhao",
                'rg': "Renata Glasc",
                'nunu': "Nunu & Willump",
                'willump': "Nunu & Willump",
            }
            
            # Get all champions once
            all_champions = cursor.fetchall()
            
            for name, champ_id in all_champions:
                # Add official name (exact case)
                cache[name] = champ_id
                # Add lowercase version
                cache[name.lower()] = champ_id
                # Add version without spaces/punctuation for web matching
                clean_name = name.replace(" ", "").replace("'", "").replace(".", "").lower()
                cache[clean_name] = champ_id
            
            # Add web mapping
            for web_name, riot_name in web_to_riot_mapping.items():
                # Find the ID for the riot name
                for name, champ_id in all_champions:
                    if name == riot_name:
                        cache[web_name] = champ_id
                        cache[web_name.lower()] = champ_id
                        break
            
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