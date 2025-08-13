#!/usr/bin/env python3
"""
League of Legends Coach - Unified Application
Multi-purpose tool for champion analysis, draft coaching, and data management
"""

import sys
import os
import argparse

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.draft_monitor import DraftMonitor
from src.db import Database
from src.parser import Parser
from src.assistant import Assistant
from src.constants import TOP_SOLOQ_POOL

def print_banner():
    """Print application banner."""
    banner = """
==================================================================
                      LEAGUE OF LEGENDS COACH                         
                                                                  
  Complete toolkit for champion analysis and draft assistance     
  - Real-time draft monitoring                                   
  - Champion data management                                       
  - Statistical analysis and tier lists                           
==================================================================
"""
    print(banner)

def print_main_menu():
    """Print the main menu options."""
    menu = """
MAIN MENU:
  1. Real-time Draft Coach     - Monitor champion select and get live recommendations
  2. Update Champion Data      - Fetch latest champions from Riot API
  3. Parse Match Statistics    - Scrape matchup data (SoloQ Pool or All Champions)
  4. Champion Analysis         - Run tier lists and statistical analysis
  5. Optimal Team Builder      - Find best champion combinations
  6. Exit

Choose an option (1-6): """
    return input(menu).strip()

def print_requirements():
    """Print system requirements."""
    print("[REQUIREMENTS]:")
    print("  [OK] League of Legends client must be running")
    print("  [OK] Python packages: requests, psutil")
    print("  [OK] Champion statistics database (db.db)")
    print()

def check_dependencies():
    """Check if required dependencies are available."""
    missing_deps = []
    
    try:
        import requests
    except ImportError:
        missing_deps.append("requests")
    
    try:
        import psutil
    except ImportError:
        missing_deps.append("psutil")
    
    if missing_deps:
        print("[ERROR] MISSING DEPENDENCIES:")
        for dep in missing_deps:
            print(f"  - {dep}")
        print(f"\nInstall with: pip install {' '.join(missing_deps)}")
        return False
    
    return True

def check_database():
    """Check if database file exists."""
    db_path = "db.db"
    if not os.path.exists(db_path):
        print("[ERROR] DATABASE NOT FOUND:")
        print(f"  - Missing: {db_path}")
        print("  - Run data parsing first: python main.py")
        return False
    
    return True

# === MENU FUNCTIONS ===

def run_draft_coach(verbose=False):
    """Run the real-time draft coach."""
    print("[INFO] Starting Real-time Draft Coach...")
    print("Make sure League of Legends client is running and start a game!")
    print("Press Ctrl+C to stop monitoring.\n")
    
    try:
        monitor = DraftMonitor(verbose=verbose, auto_select_pool=False)
        monitor.start_monitoring()
    except KeyboardInterrupt:
        print("\n[INFO] Draft Coach stopped by user")
    except Exception as e:
        print(f"[ERROR] Draft coach error: {e}")
        if verbose:
            import traceback
            traceback.print_exc()

def update_champion_data():
    """Update champion data from Riot API."""
    print("[INFO] Updating champion data from Riot API...")
    
    try:
        db = Database("db.db")
        db.connect()
        
        # Ensure table structure is correct
        if not db.create_riot_champions_table():
            print("[ERROR] Failed to create/update champions table")
            return
        
        # Update from Riot API
        if db.update_champions_from_riot_api():
            # Show some stats
            champion_names = db.get_all_champion_names()
            print(f"[SUCCESS] Updated {len(champion_names)} champions in database")
        else:
            print("[ERROR] Failed to update champion data")
        
        db.close()
    except Exception as e:
        print(f"[ERROR] Update error: {e}")

def parse_match_statistics():
    """Parse match statistics from web sources with submenu."""
    print("[INFO] Match Statistics Parser")
    print("\nParsing options:")
    print("1. Parse SoloQ Pool only       - Fast (~1 min, recommended)")
    print("2. Parse All Champions         - Comprehensive (~30+ min)")
    print("3. Back to main menu")
    
    choice = input("\nChoose option (1-3): ").strip()
    
    if choice == "1":
        parse_champion_pool()
    elif choice == "2":
        parse_all_champions()
    elif choice == "3":
        return
    else:
        print("[ERROR] Invalid option")

def parse_champion_pool():
    """Parse match statistics for SoloQ pool only."""
    print("[INFO] Parsing SoloQ Pool statistics...")
    print("This will take approximately 1-2 minutes...")
    
    try:
        from src.config import config
        db = Database(config.DATABASE_PATH if 'config' in globals() else "db.db")
        parser = Parser()
        
        db.connect()
        
        # Ensure champions are up to date
        cursor = db.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM champions")
        champion_count = cursor.fetchone()[0]
        
        if champion_count == 0:
            print("[INFO] No champions found, updating from Riot API first...")
            db.create_riot_champions_table()
            db.update_champions_from_riot_api()
        
        # Initialize matchups table
        db.init_matchups_table()
        
        # Build champion cache once for much better performance
        print("[INFO] Building champion cache for fast lookups...")
        champion_cache = db.build_champion_cache()
        print(f"[INFO] Cached {len(champion_cache)//2} champions")  # Divided by 2 because we store both cases
        
        print(f"[INFO] Parsing {len(TOP_SOLOQ_POOL)} champions from Top SoloQ pool...")
        total_inserted = 0
        processed = 0
        
        for champion in TOP_SOLOQ_POOL:
            processed += 1
            print(f"  [{processed}/{len(TOP_SOLOQ_POOL)}] Processing {champion}...")
            
            try:
                # Collect all matchups for this champion
                matchup_data = []
                raw_matchups = parser.get_champion_data(champion.lower(), "top")
                
                for matchup in raw_matchups:
                    enemy, winrate, d1, d2, pick, games = matchup
                    matchup_data.append((champion, enemy, winrate, d1, d2, pick, games))
                
                if matchup_data:
                    # Batch insert all matchups for this champion
                    # (table was already cleared by init_matchups_table above)
                    inserted = db.add_matchups_batch(matchup_data, champion_cache)
                    total_inserted += inserted
                    print(f"    → Inserted {inserted} matchups")
                else:
                    print(f"    → No matchups found")
                    
            except Exception as e:
                print(f"  [WARNING] Error processing {champion}: {e}")
        
        parser.close()
        db.close()
        print(f"[SUCCESS] SoloQ Pool statistics updated! ({processed} champions, {total_inserted} total matchups)")
        
    except Exception as e:
        print(f"[ERROR] Parsing error: {e}")

def parse_all_champions():
    """Parse match statistics for all champions."""
    print("[WARNING] Parsing ALL champions will take 30+ minutes!")
    confirm = input("Are you sure you want to continue? (y/N): ").strip().lower()
    
    if confirm != 'y':
        print("[INFO] Cancelled by user")
        return
    
    print("[INFO] Parsing ALL champion statistics...")
    print("This will take approximately 30-60 minutes...")
    
    try:
        from src.constants import CHAMPIONS_LIST
        from src.config import config
        db = Database(config.DATABASE_PATH if 'config' in globals() else "db.db")
        parser = Parser()
        
        db.connect()
        
        # Ensure champions are up to date
        cursor = db.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM champions")
        champion_count = cursor.fetchone()[0]
        
        if champion_count == 0:
            print("[INFO] No champions found, updating from Riot API first...")
            db.create_riot_champions_table()
            db.update_champions_from_riot_api()
        
        # Initialize tables
        db.init_matchups_table()
        
        # Build champion cache once for much better performance
        print("[INFO] Building champion cache for fast lookups...")
        champion_cache = db.build_champion_cache()
        print(f"[INFO] Cached {len(champion_cache)//2} champions")
        
        print(f"[INFO] Parsing {len(CHAMPIONS_LIST)} champions...")
        total_inserted = 0
        processed = 0
        
        for champion in CHAMPIONS_LIST:
            processed += 1
            print(f"  [{processed}/{len(CHAMPIONS_LIST)}] Processing {champion}...")
            
            try:
                # Collect all matchups for this champion
                matchup_data = []
                raw_matchups = parser.get_champion_data(champion.lower())
                
                for matchup in raw_matchups:
                    enemy, winrate, d1, d2, pick, games = matchup
                    matchup_data.append((champion, enemy, winrate, d1, d2, pick, games))
                
                if matchup_data:
                    # Batch insert all matchups for this champion
                    # (table was already cleared by init_matchups_table above)
                    inserted = db.add_matchups_batch(matchup_data, champion_cache)
                    total_inserted += inserted
                    print(f"    → Inserted {inserted} matchups")
                else:
                    print(f"    → No matchups found")
                    
            except Exception as e:
                print(f"  [WARNING] Error processing {champion}: {e}")
        
        parser.close()
        db.close()
        print(f"[SUCCESS] All champion statistics updated! ({processed} champions, {total_inserted} total matchups)")
        
    except Exception as e:
        print(f"[ERROR] Parsing error: {e}")

def run_champion_analysis():
    """Run champion analysis and tier lists."""
    print("[INFO] Running champion analysis...")
    
    try:
        ast = Assistant()
        
        print("\n=== COMPETITIVE DRAFT ANALYSIS ===")
        ast.competitive_draft(3)
        
        ast.close()
        print("\n[SUCCESS] Analysis completed!")
        
    except Exception as e:
        print(f"[ERROR] Analysis error: {e}")

def run_optimal_team_builder():
    """Run optimal team building tools."""
    print("[INFO] Optimal Team Builder")
    print("\nAvailable options:")
    print("1. Find optimal trio from pool")
    print("2. Find optimal duo for specific champion")
    
    choice = input("Choose option (1-2): ").strip()
    
    try:
        ast = Assistant()
        
        # Let user select which extended champion pool to use for analysis
        selected_pool = ast.select_extended_champion_pool()
        
        if choice == "1":
            print(f"\n=== OPTIMAL TRIO FROM {selected_pool[0] if selected_pool else 'SELECTED'} POOL ===")
            result = ast.optimal_trio_from_pool(selected_pool)
            blind, counter1, counter2, score = result
            print(f"\nFINAL RESULT:")
            print(f"Blind Pick: {blind}")
            print(f"Counterpicks: {counter1}, {counter2}")
            print(f"Total Score: {score:.2f}")
            
        elif choice == "2":
            champion = input("Enter champion name: ").strip()
            if champion:
                print(f"\n=== OPTIMAL DUO FOR {champion.upper()} ===")
                ast.optimal_duo_for_champion(champion, selected_pool)
            else:
                print("[ERROR] No champion name provided")
        else:
            print("[ERROR] Invalid option")
        
        ast.close()
        
    except Exception as e:
        print(f"[ERROR] Team builder error: {e}")

def main():
    """Main application entry point with unified menu."""
    parser = argparse.ArgumentParser(
        description="League of Legends Coach - Complete toolkit for champion analysis and draft assistance"
    )
    parser.add_argument(
        "--no-banner",
        action="store_true",
        help="Skip banner display"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--direct-coach",
        action="store_true",
        help="Skip menu and go directly to draft coach (legacy mode)"
    )
    
    args = parser.parse_args()
    
    # Legacy direct coach mode
    if args.direct_coach:
        if not args.no_banner:
            print_banner()
            print_requirements()
        
        # Check dependencies and database
        if not check_dependencies() or not check_database():
            sys.exit(1)
        
        run_draft_coach(args.verbose)
        return
    
    # Main menu mode
    while True:
        if not args.no_banner:
            print_banner()
            args.no_banner = True  # Only show banner once
        
        try:
            choice = print_main_menu()
            
            if choice == "1":
                # Check requirements for draft coach
                if not check_dependencies() or not check_database():
                    input("\nPress Enter to return to menu...")
                    continue
                run_draft_coach(args.verbose)
                
            elif choice == "2":
                update_champion_data()
                input("\nPress Enter to return to menu...")
                
            elif choice == "3":
                parse_match_statistics()
                input("\nPress Enter to return to menu...")
                
            elif choice == "4":
                if not check_database():
                    input("\nPress Enter to return to menu...")
                    continue
                run_champion_analysis()
                input("\nPress Enter to return to menu...")
                
            elif choice == "5":
                if not check_database():
                    input("\nPress Enter to return to menu...")
                    continue
                run_optimal_team_builder()
                input("\nPress Enter to return to menu...")
                
            elif choice == "6":
                print("\nGoodbye!")
                break
                
            else:
                print("\n[ERROR] Invalid option. Please choose 1-6.")
                input("Press Enter to continue...")
                
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\n[ERROR] Unexpected error: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            input("Press Enter to return to menu...")

if __name__ == "__main__":
    main()