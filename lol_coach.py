#!/usr/bin/env python3
"""
League of Legends Coach - Unified Application
Multi-purpose tool for champion analysis, draft coaching, and data management
"""

import sys
import os
import argparse
from typing import List

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
  6. Manage Champion Pools     - Create, edit, and manage custom champion pools
  7. Exit

Choose an option (1-7): """
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

def _get_patch_version():
    """Ask user for patch version to analyze."""
    from src.config import config
    
    print(f"\nCurrent patch in config: {config.CURRENT_PATCH}")
    print("Options:")
    print("1. Use current patch from config")
    print("2. Specify different patch")
    print("3. Back to main menu")
    
    choice = input("\nChoose option (1-3): ").strip()
    
    if choice == "1":
        return config.CURRENT_PATCH
    elif choice == "2":
        patch_input = input("Enter patch version (e.g., 15.15): ").strip()
        if patch_input:
            # Validate patch format (basic validation)
            parts = patch_input.split('.')
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return patch_input
            else:
                print("[ERROR] Invalid patch format. Use format like 15.15")
                return None
        else:
            print("[ERROR] Patch version cannot be empty")
            return None
    elif choice == "3":
        return None
    else:
        print("[ERROR] Invalid option")
        return None

def run_draft_coach(verbose=False, auto_hover=False):
    """Run the real-time draft coach."""
    print("[INFO] Starting Real-time Draft Coach...")
    print("Make sure League of Legends client is running and start a game!")
    if auto_hover:
        print("🎯 [AUTO-HOVER] Champion auto-hover is ENABLED")
    print("Press Ctrl+C to stop monitoring.\n")
    
    try:
        monitor = DraftMonitor(verbose=verbose, auto_select_pool=False, auto_hover=auto_hover)
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
        from src.config import config
        db = Database(config.DATABASE_PATH)
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
    
    # Ask for patch version first
    patch_version = _get_patch_version()
    if not patch_version:
        return
    
    print(f"\n✅ Patch selected: {patch_version}")
    print("\nParsing options:")
    print("1. Parse SoloQ Pool only       - Fast (~1 min, recommended)")
    print("2. Parse All Champions         - Comprehensive (~30+ min)")
    print("3. Back to main menu")
    
    choice = input("\nChoose option (1-3): ").strip()
    
    if choice == "1":
        parse_champion_pool(patch_version)
    elif choice == "2":
        parse_all_champions(patch_version)
    elif choice == "3":
        return
    else:
        print("[ERROR] Invalid option")

def parse_champion_pool(patch_version=None):
    """Parse match statistics for selected champion pool."""
    print("[INFO] Champion Pool Statistics Parser")
    
    # Enhanced pool selection
    selected_pool_info = _select_pool_for_parsing()
    if not selected_pool_info:
        print("[WARNING] No pool selected, using default Top SoloQ pool")
        pool_name = "Top SoloQ (Default)"
        pool_champions = TOP_SOLOQ_POOL
    else:
        pool_name, pool_champions = selected_pool_info
    
    print(f"\n✅ Parsing statistics for: {pool_name}")
    print(f"🔧 Patch version: {patch_version or 'default'}")
    print(f"Champions to process: {', '.join(pool_champions)}")
    print(f"This will take approximately {len(pool_champions)*0.5:.1f}-{len(pool_champions)*1:.1f} minutes...")
    
    confirm = input(f"\nProceed with parsing {len(pool_champions)} champions? (y/N): ").strip().lower()
    if confirm != 'y':
        print("[INFO] Parsing cancelled.")
        return
    
    try:
        from src.config import config, normalize_champion_name_for_url
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
        
        print(f"\n[INFO] Parsing {len(pool_champions)} champions from {pool_name}...")
        total_inserted = 0
        processed = 0
        
        for champion in pool_champions:
            processed += 1
            print(f"  [{processed}/{len(pool_champions)}] Processing {champion}...")
            
            try:
                # Collect all matchups for this champion
                matchup_data = []
                normalized_champion = normalize_champion_name_for_url(champion)
                if patch_version:
                    raw_matchups = parser.get_champion_data_on_patch(patch_version, normalized_champion, "top")
                else:
                    raw_matchups = parser.get_champion_data(normalized_champion, "top")
                
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

def parse_all_champions(patch_version=None):
    """Parse match statistics for all champions."""
    print("[WARNING] Parsing ALL champions will take 30+ minutes!")
    confirm = input("Are you sure you want to continue? (y/N): ").strip().lower()
    
    if confirm != 'y':
        print("[INFO] Cancelled by user")
        return
    
    print("[INFO] Parsing ALL champion statistics...")
    print(f"🔧 Patch version: {patch_version or 'default'}")
    print("This will take approximately 30-60 minutes...")
    
    try:
        from src.constants import CHAMPIONS_LIST
        from src.config import config, normalize_champion_name_for_url
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
                normalized_champion = normalize_champion_name_for_url(champion)
                if patch_version:
                    raw_matchups = parser.get_champion_data_on_patch(patch_version, normalized_champion)
                else:
                    raw_matchups = parser.get_champion_data(normalized_champion)
                
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
    print("1. Find optimal trio from pool (traditional - blind pick + counterpicks)")
    print("2. Find optimal duo for specific champion")
    print("3. Find optimal trio combinations (holistic evaluation)")
    
    choice = input("Choose option (1-3): ").strip()
    
    try:
        from src.pool_manager import PoolManager
        ast = Assistant()
        
        # Enhanced pool selection using PoolManager
        selected_pool_info = _select_pool_for_analysis()
        if not selected_pool_info:
            print("[WARNING] No pool selected, using default Top SoloQ pool")
            selected_pool = ast.select_extended_champion_pool()
        else:
            pool_name, pool_champions = selected_pool_info
            selected_pool = pool_champions
            print(f"\n✅ Using pool: {pool_name} ({len(pool_champions)} champions)")
        
        if choice == "1":
            print(f"\n" + "="*60)
            print(f"OPTIMAL TRIO ANALYSIS")
            print("="*60)
            result = ast.optimal_trio_from_pool(selected_pool)
            blind, counter1, counter2, score = result
            print(f"\nFINAL RESULT:")
            print(f"Blind Pick: {blind}")
            print(f"Counterpicks: {counter1}, {counter2}")
            print(f"Total Score: {score:.2f}")
            
            # Proposer de sauvegarder le trio comme nouveau pool
            _offer_save_optimization_result([blind, counter1, counter2], f"Optimal Trio (Score: {score:.1f})")
            
        elif choice == "2":
            champion = input("Enter champion name: ").strip()
            if champion:
                print(f"\n" + "="*60)
                print(f"OPTIMAL DUO FOR {champion.upper()}")
                print("="*60)
                duo_result = ast.optimal_duo_for_champion(champion, selected_pool)
                
                # Si la méthode retourne un résultat, proposer de le sauvegarder
                if duo_result and isinstance(duo_result, tuple) and len(duo_result) == 4:
                    # Extract the 3 champions (exclude the score)
                    fixed_champ, companion1, companion2, score = duo_result
                    duo_champions = [fixed_champ, companion1, companion2]
                    _offer_save_optimization_result(duo_champions, f"Optimal Duo for {champion} (Score: {score:.1f})")
            else:
                print("[ERROR] No champion name provided")
                
        elif choice == "3":
            print(f"\n" + "="*60)
            print(f"HOLISTIC TRIO COMBINATIONS ANALYSIS")
            print("="*60)
            print(f"Analyzing all possible trio combinations from your pool...")
            print(f"This evaluates trios as complete units rather than blind pick + counterpicks")
            
            # Run the holistic trio analysis
            trio_results = ast.find_optimal_trios_holistic(selected_pool, num_results=5)
            
            # Display results
            _display_holistic_trio_results(trio_results)
            
            # Offer to save the best trio
            if trio_results:
                best_trio = trio_results[0]['trio']
                best_score = trio_results[0]['total_score']
                _offer_save_optimization_result(list(best_trio), f"Holistic Trio (Score: {best_score:.1f})")
                
        else:
            print("[ERROR] Invalid option")
        
        ast.close()
        
    except Exception as e:
        print(f"[ERROR] Team builder error: {e}")

def _select_pool_for_analysis():
    """Select a pool for team building analysis with enhanced interface."""
    try:
        from src.pool_manager import PoolManager
        pool_manager = PoolManager()
        
        pools = pool_manager.get_all_pools()
        if not pools:
            print("[ERROR] No pools found.")
            return None
        
        print(f"\n" + "="*50)
        print("SELECT ANALYSIS POOL")
        print("="*50)
        print("Available pools for analysis:")
        
        # Create numbered list
        pool_list = []
        idx = 1
        for name, pool in sorted(pools.items()):
            pool_list.append((name, pool))
            status = "🔧" if pool.created_by == "system" else "👤"
            suitable = "⭐" if pool.size() >= 5 else "⚠️"  # Indicator for analysis suitability
            print(f"  {idx:>2}. {status}{suitable} {name:<18} | {pool.role:<8} | {pool.size():>2} champs | {pool.description}")
            idx += 1
        
        print(f"\n  {idx}. Use Assistant's extended pool selector (legacy)")
        print("\n⭐ = Recommended for analysis (5+ champions)")
        print("⚠️ = Small pool (may have limited analysis)")
        
        try:
            choice = input(f"\nChoose pool (1-{idx} or 'cancel'): ").strip()
            
            if choice.lower() == 'cancel':
                return None
            
            choice_num = int(choice)
            if 1 <= choice_num <= len(pool_list):
                selected_name, selected_pool = pool_list[choice_num - 1]
                return (selected_name, selected_pool.champions)
            elif choice_num == idx:
                # Legacy fallback
                return None
            else:
                print(f"[ERROR] Invalid choice. Please choose 1-{idx}.")
                return None
                
        except ValueError:
            print("[ERROR] Invalid input. Please enter a number.")
            return None
            
    except Exception as e:
        print(f"[WARNING] Pool selection error: {e}")
        return None

def _select_pool_for_parsing():
    """Select a pool for statistics parsing with enhanced interface."""
    try:
        from src.pool_manager import PoolManager
        pool_manager = PoolManager()
        
        pools = pool_manager.get_all_pools()
        if not pools:
            print("[ERROR] No pools found.")
            return None
        
        print(f"\n" + "="*50)
        print("SELECT POOL FOR PARSING")
        print("="*50)
        print("Available pools for statistics parsing:")
        
        # Create numbered list
        pool_list = []
        idx = 1
        for name, pool in sorted(pools.items()):
            pool_list.append((name, pool))
            status = "🔧" if pool.created_by == "system" else "👤"
            time_est = f"~{pool.size()*0.5:.1f}-{pool.size()*1:.1f}min"
            print(f"  {idx:>2}. {status} {name:<18} | {pool.role:<8} | {pool.size():>2} champs | {time_est:>8} | {pool.description}")
            idx += 1
        
        print(f"\n  {idx}. Parse ALL Champions (extended analysis - ~60-90 min)")
        print(f"  {idx+1}. Use Top SoloQ Pool (default - ~2-3 min)")
        
        try:
            choice = input(f"\nChoose pool (1-{idx+1} or 'cancel'): ").strip()
            
            if choice.lower() == 'cancel':
                return None
            
            choice_num = int(choice)
            if 1 <= choice_num <= len(pool_list):
                selected_name, selected_pool = pool_list[choice_num - 1]
                return (selected_name, selected_pool.champions)
            elif choice_num == idx:
                # All champions option
                from src.constants import CHAMPIONS_LIST
                return ("ALL CHAMPIONS", list(CHAMPIONS_LIST))
            elif choice_num == idx + 1:
                # Default Top SoloQ
                return None
            else:
                print(f"[ERROR] Invalid choice. Please choose 1-{idx+1}.")
                return None
                
        except ValueError:
            print("[ERROR] Invalid input. Please enter a number.")
            return None
            
    except Exception as e:
        print(f"[WARNING] Pool selection error: {e}")
        return None

def _offer_save_optimization_result(champions: List[str], suggested_name: str):
    """Offer to save optimization results as a new champion pool."""
    if not champions:
        return
    
    # Show ban recommendations for this optimized pool
    _show_ban_recommendations(champions)
    
    save_choice = input(f"\nSave this result as a new pool? (y/N): ").strip().lower()
    if save_choice != 'y':
        return
    
    try:
        from src.pool_manager import PoolManager
        pool_manager = PoolManager()
        
        print(f"\nSaving pool with champions: {', '.join(champions)}")
        
        # Suggest a name but allow customization
        default_name = suggested_name
        pool_name = input(f"Pool name (or press Enter for '{default_name}'): ").strip()
        if not pool_name:
            pool_name = default_name
        
        # Check if name already exists
        if pool_manager.get_pool(pool_name):
            print(f"[WARNING] Pool '{pool_name}' already exists.")
            overwrite = input("Overwrite existing pool? (y/N): ").strip().lower()
            if overwrite != 'y':
                return
            pool_manager.delete_pool(pool_name)  # Remove existing
        
        description = input("Description (optional): ").strip()
        if not description:
            description = f"Generated from optimization analysis"
        
        # Determine role based on champions (simple heuristic)
        role = "custom"
        
        # Tags
        tags = ["optimization", "generated"]
        
        if pool_manager.create_pool(pool_name, champions, description, role, tags):
            print(f"[SUCCESS] Created pool '{pool_name}' with {len(champions)} champions!")
            
            # Save immediately
            if pool_manager.save_custom_pools():
                print(f"[SUCCESS] Pool saved successfully!")
            else:
                print(f"[WARNING] Pool created but save failed. Use 'Manage Champion Pools' menu to save manually.")
        else:
            print(f"[ERROR] Failed to create pool '{pool_name}'")
            
    except Exception as e:
        print(f"[ERROR] Error saving optimization result: {e}")

def _display_holistic_trio_results(trio_results: List[dict]):
    """Display the results of holistic trio analysis in a clear format."""
    try:
        if not trio_results:
            print("❌ No viable trios found")
            return
        
        print(f"\n🏆 TOP TRIO COMBINATIONS FOUND:")
        print("="*80)
        
        for i, result in enumerate(trio_results, 1):
            trio = result['trio']
            total = result['total_score']
            coverage = result['coverage_score']
            balance = result['balance_score']
            consistency = result['consistency_score']
            meta = result['meta_score']
            
            # Rank symbol
            rank_symbol = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            
            print(f"\n{rank_symbol} {trio[0]} + {trio[1]} + {trio[2]}")
            print(f"   🎯 Total Score: {total:>5.1f}/100")
            print(f"   📊 Coverage:    {coverage:>5.1f}/100  (Enemy matchup coverage)")
            print(f"   ⚖️  Balance:     {balance:>5.1f}/100  (Diverse profiles)")
            print(f"   📈 Consistency: {consistency:>5.1f}/100  (Reliable performance)")
            print(f"   🌟 Meta:        {meta:>5.1f}/100  (vs popular picks)")
            
            # Show some enemy coverage examples for top trio
            if i == 1 and 'enemy_coverage' in result:
                coverage_data = result['enemy_coverage']
                if coverage_data:
                    print(f"   Best matchups: ", end="")
                    top_matchups = sorted(coverage_data.items(), key=lambda x: x[1][0], reverse=True)[:3]
                    matchup_strs = [f"{enemy}(+{delta2:.1f})" for enemy, (delta2, _) in top_matchups if delta2 > 0]
                    print(", ".join(matchup_strs[:3]) if matchup_strs else "None significant")
        
        print("\n" + "="*80)
        print("💡 INTERPRETATION:")
        print("   • Higher scores = better overall trio performance")
        print("   • Coverage = How well the trio handles all enemies")
        print("   • Balance = Diversity to avoid shared weaknesses") 
        print("   • Consistency = Reliable performance across matchups")
        print("   • Meta = Performance vs currently popular champions")
        
    except Exception as e:
        print(f"[ERROR] Error displaying trio results: {e}")

def _show_ban_recommendations(champions: List[str]):
    """Show ban recommendations for a champion pool."""
    try:
        print(f"\n" + "="*60)
        print("🛡️ STRATEGIC BAN RECOMMENDATIONS")
        print("="*60)
        print(f"For your optimized pool: {', '.join(champions)}")
        
        from src.assistant import Assistant
        assistant = Assistant()
        
        ban_recommendations = assistant.get_ban_recommendations(champions, num_bans=5)
        
        if ban_recommendations:
            print(f"\nTop threats to ban:")
            for i, (enemy, threat_score, matchup_count) in enumerate(ban_recommendations, 1):
                print(f"  {i}. {enemy:<15} | Threat: {threat_score:>5.2f} | Counters {matchup_count}/{len(champions)} champions")
            
            print(f"\n💡 These champions are statistically strong against your pool.")
            print(f"💡 Banning them will improve your overall matchup spread.")
        else:
            print(f"⚠️ No ban recommendations found (insufficient data)")
        
        assistant.close()
        
    except Exception as e:
        print(f"[WARNING] Error generating ban recommendations: {e}")

def manage_champion_pools():
    """Manage champion pools with interactive interface."""
    from src.pool_manager import PoolManager
    from src.assistant import Assistant
    
    print("[INFO] Champion Pool Manager")
    
    try:
        pool_manager = PoolManager()
        assistant = Assistant()
        available_champions = set(assistant.db.get_all_champion_names().values())
        
        while True:
            print("\n" + "="*60)
            print("CHAMPION POOL MANAGEMENT")
            print("="*60)
            
            menu = """
Pool Management Options:
  1. List all pools
  2. View pool details
  3. Create new pool
  4. Edit existing pool
  5. Delete pool
  6. Duplicate pool
  7. Search pools
  8. Pool statistics
  9. Back to main menu

Choose an option (1-9): """
            
            choice = input(menu).strip()
            
            if choice == "1":
                list_pools(pool_manager)
            elif choice == "2":
                view_pool_details(pool_manager)
            elif choice == "3":
                create_new_pool(pool_manager, available_champions)
            elif choice == "4":
                edit_pool(pool_manager, available_champions)
            elif choice == "5":
                delete_pool(pool_manager)
            elif choice == "6":
                duplicate_pool(pool_manager)
            elif choice == "7":
                search_pools(pool_manager)
            elif choice == "8":
                show_pool_statistics(pool_manager)
            elif choice == "9":
                pool_manager.save_custom_pools()
                print("[INFO] Custom pools saved!")
                break
            else:
                print("[ERROR] Invalid option. Please choose 1-9.")
                
        assistant.close()
                
    except Exception as e:
        print(f"[ERROR] Pool manager error: {e}")
        if hasattr(e, '__traceback__'):
            import traceback
            traceback.print_exc()

def list_pools(pool_manager):
    """List all available pools."""
    print("\n" + "="*50)
    print("ALL CHAMPION POOLS")
    print("="*50)
    
    pools = pool_manager.get_all_pools()
    if not pools:
        print("No pools found.")
        return
    
    # Group by type
    system_pools = []
    custom_pools = []
    
    for name, pool in pools.items():
        if pool.created_by == "system":
            system_pools.append((name, pool))
        else:
            custom_pools.append((name, pool))
    
    if system_pools:
        print("\n🔧 SYSTEM POOLS:")
        for name, pool in sorted(system_pools):
            print(f"  {name:<20} | {pool.role:<8} | {pool.size():>2} champions | {pool.description}")
    
    if custom_pools:
        print("\n👤 CUSTOM POOLS:")
        for name, pool in sorted(custom_pools):
            print(f"  {name:<20} | {pool.role:<8} | {pool.size():>2} champions | {pool.description}")
    
    if not custom_pools:
        print("\n👤 CUSTOM POOLS: None created yet")

def view_pool_details(pool_manager):
    """View details of a specific pool."""
    pool = _select_pool_interactive(pool_manager, "View pool details")
    if not pool:
        return
    
    print(f"\n" + "="*50)
    print(f"POOL DETAILS: {pool.name}")
    print("="*50)
    print(f"Role: {pool.role}")
    print(f"Description: {pool.description}")
    print(f"Created by: {pool.created_by}")
    print(f"Tags: {', '.join(pool.tags) if pool.tags else 'None'}")
    print(f"Champions ({pool.size()}):")
    
    # Display champions in columns
    champions = pool.champions
    cols = 3
    for i in range(0, len(champions), cols):
        row = champions[i:i+cols]
        print(f"  {' | '.join(f'{champ:<15}' for champ in row)}")

def create_new_pool(pool_manager, available_champions):
    """Create a new champion pool."""
    from src.pool_manager import validate_champion_name, suggest_champions
    
    print("\n" + "="*50)
    print("CREATE NEW POOL")
    print("="*50)
    
    name = input("Pool name: ").strip()
    if not name:
        print("[ERROR] Pool name cannot be empty.")
        return
    
    if pool_manager.get_pool(name):
        print(f"[ERROR] Pool '{name}' already exists.")
        return
    
    description = input("Description (optional): ").strip()
    role = input("Role (top/jungle/mid/adc/support/custom): ").strip().lower()
    if role not in ["top", "jungle", "mid", "adc", "support", "custom"]:
        role = "custom"
    
    # Tags
    tags_input = input("Tags (comma-separated, optional): ").strip()
    tags = [tag.strip() for tag in tags_input.split(",") if tag.strip()] if tags_input else []
    
    print("\nAdd champions to the pool:")
    print("  - Enter champion names one by one")
    print("  - Type 'done' when finished")
    print("  - Type 'list' to see suggestions")
    
    champions = []
    while True:
        champ_input = input(f"Champion {len(champions)+1} (or 'done'/'list'): ").strip()
        
        if champ_input.lower() == 'done':
            break
        elif champ_input.lower() == 'list':
            print("Available champions:", ", ".join(sorted(list(available_champions)[:20])) + "...")
            continue
        
        # Auto-suggest if partial match
        if champ_input and not validate_champion_name(champ_input, available_champions):
            suggestions = suggest_champions(champ_input, available_champions)
            if suggestions:
                print(f"Did you mean: {', '.join(suggestions)}")
                continue
            else:
                print(f"[WARNING] Champion '{champ_input}' not found.")
                continue
        
        if champ_input and champ_input not in champions:
            champions.append(champ_input)
            print(f"  Added: {champ_input}")
        elif champ_input in champions:
            print(f"  Already in pool: {champ_input}")
    
    if not champions:
        print("[ERROR] Cannot create empty pool.")
        return
    
    if pool_manager.create_pool(name, champions, description, role, tags):
        print(f"[SUCCESS] Created pool '{name}' with {len(champions)} champions!")
    else:
        print(f"[ERROR] Failed to create pool '{name}'.")

def edit_pool(pool_manager, available_champions):
    """Edit an existing pool."""
    from src.pool_manager import validate_champion_name, suggest_champions
    
    # Select pool interactively
    pool = _select_pool_interactive(pool_manager, "Edit pool")
    if not pool:
        return
    
    if pool.created_by == "system":
        print(f"[ERROR] Cannot edit system pool '{pool.name}'.")
        return
    
    while True:
        # Display current pool state
        print(f"\n" + "="*60)
        print(f"EDITING POOL: {pool.name}")
        print("="*60)
        print(f"Role: {pool.role} | Description: {pool.description}")
        print(f"Tags: {', '.join(pool.tags) if pool.tags else 'None'}")
        print(f"Current champions ({pool.size()}):")
        
        # Display champions in a compact format
        champions = pool.champions
        if champions:
            cols = 4
            for i in range(0, len(champions), cols):
                row = champions[i:i+cols]
                print(f"  {' | '.join(f'{champ:<12}' for champ in row)}")
        else:
            print("  [No champions in pool]")
        
        menu = """
Edit Options:
  1. Add champion
  2. Remove champion
  3. Edit description
  4. Edit role
  5. Edit tags
  6. Back to pool menu

Choose option (1-6): """
        
        choice = input(menu).strip()
        
        if choice == "1":
            print(f"\nAdding champion to '{pool.name}'")
            champ = input("Champion to add: ").strip()
            if champ:
                if validate_champion_name(champ, available_champions):
                    if pool.add_champion(champ):
                        print(f"[SUCCESS] Added {champ} to {pool.name}")
                    else:
                        print(f"[INFO] {champ} already in pool")
                else:
                    suggestions = suggest_champions(champ, available_champions)
                    if suggestions:
                        print(f"[ERROR] Champion not found. Suggestions: {', '.join(suggestions)}")
                    else:
                        print(f"[ERROR] Champion '{champ}' not found.")
        
        elif choice == "2":
            if not pool.champions:
                print("[INFO] Pool is empty, no champions to remove.")
                continue
            
            print(f"\nRemoving champion from '{pool.name}'")
            print("Current champions:")
            for i, champ in enumerate(pool.champions, 1):
                print(f"  {i}. {champ}")
            
            try:
                remove_choice = input("\nRemove by number or name: ").strip()
                
                # Try as number first
                if remove_choice.isdigit():
                    idx = int(remove_choice) - 1
                    if 0 <= idx < len(pool.champions):
                        champ_to_remove = pool.champions[idx]
                        pool.remove_champion(champ_to_remove)
                        print(f"[SUCCESS] Removed {champ_to_remove} from {pool.name}")
                    else:
                        print("[ERROR] Invalid number.")
                else:
                    # Try as name
                    if pool.remove_champion(remove_choice):
                        print(f"[SUCCESS] Removed {remove_choice} from {pool.name}")
                    else:
                        print(f"[ERROR] {remove_choice} not found in pool")
            except ValueError:
                print("[ERROR] Invalid input.")
        
        elif choice == "3":
            print(f"\nEditing description for '{pool.name}'")
            print(f"Current: {pool.description}")
            new_desc = input("New description (or press Enter to keep current): ").strip()
            if new_desc:
                pool.description = new_desc
                print("[SUCCESS] Description updated")
        
        elif choice == "4":
            print(f"\nEditing role for '{pool.name}'")
            print(f"Current: {pool.role}")
            print("Available roles: top, jungle, mid, adc, support, custom")
            new_role = input("New role: ").strip().lower()
            if new_role in ["top", "jungle", "mid", "adc", "support", "custom"]:
                pool.role = new_role
                print("[SUCCESS] Role updated")
            elif new_role:
                print("[ERROR] Invalid role")
        
        elif choice == "5":
            print(f"\nEditing tags for '{pool.name}'")
            print(f"Current: {', '.join(pool.tags) if pool.tags else 'None'}")
            tags_input = input("New tags (comma-separated, or press Enter to clear): ").strip()
            pool.tags = [tag.strip() for tag in tags_input.split(",") if tag.strip()] if tags_input else []
            print("[SUCCESS] Tags updated")
        
        elif choice == "6":
            break
        
        else:
            print("[ERROR] Invalid option. Please choose 1-6.")

def delete_pool(pool_manager):
    """Delete a pool."""
    # Filter to show only custom pools for deletion
    custom_pools = {name: pool for name, pool in pool_manager.get_all_pools().items() 
                   if pool.created_by == "user"}
    
    if not custom_pools:
        print("[INFO] No custom pools available to delete.")
        return
    
    print(f"\n" + "="*50)
    print("DELETE POOL")
    print("="*50)
    print("Custom pools available for deletion:")
    
    pool_list = []
    idx = 1
    for name, pool in sorted(custom_pools.items()):
        pool_list.append((name, pool))
        print(f"  {idx:>2}. 👤 {name:<20} | {pool.role:<8} | {pool.size():>2} champs | {pool.description}")
        idx += 1
    
    try:
        choice = input(f"\nChoose pool to delete (1-{len(pool_list)} or 'cancel'): ").strip()
        
        if choice.lower() == 'cancel':
            return
        
        choice_num = int(choice)
        if 1 <= choice_num <= len(pool_list):
            selected_name, selected_pool = pool_list[choice_num - 1]
            
            # Show pool details before confirmation
            print(f"\nAbout to delete:")
            print(f"  Pool: {selected_name}")
            print(f"  Champions: {', '.join(selected_pool.champions)}")
            
            confirm = input(f"\nAre you sure you want to delete '{selected_name}'? (y/N): ").strip().lower()
            if confirm == 'y':
                if pool_manager.delete_pool(selected_name):
                    print(f"[SUCCESS] Deleted pool '{selected_name}'")
                else:
                    print(f"[ERROR] Failed to delete pool '{selected_name}'")
        else:
            print(f"[ERROR] Invalid choice. Please choose 1-{len(pool_list)}.")
            
    except ValueError:
        print("[ERROR] Invalid input. Please enter a number.")

def duplicate_pool(pool_manager):
    """Duplicate an existing pool."""
    source_pool = _select_pool_interactive(pool_manager, "Duplicate pool")
    if not source_pool:
        return
    
    print(f"\nDuplicating pool '{source_pool.name}'")
    new_name = input("Enter new pool name: ").strip()
    
    if not new_name:
        print("[ERROR] New pool name cannot be empty.")
        return
    
    if pool_manager.duplicate_pool(source_pool.name, new_name):
        print(f"[SUCCESS] Duplicated '{source_pool.name}' as '{new_name}'")
        
        # Show the new pool info
        new_pool = pool_manager.get_pool(new_name)
        if new_pool:
            print(f"New pool created with {new_pool.size()} champions: {', '.join(new_pool.champions)}")
    else:
        print("[ERROR] Failed to duplicate pool (name may already exist)")

def search_pools(pool_manager):
    """Search for pools."""
    query = input("\nEnter search query: ").strip()
    matches = pool_manager.search_pools(query)
    
    if matches:
        print(f"\nFound {len(matches)} pools:")
        for name in matches:
            pool = pool_manager.get_pool(name)
            print(f"  {name} | {pool.role} | {pool.size()} champions")
    else:
        print("No pools found.")

def show_pool_statistics(pool_manager):
    """Show pool statistics."""
    stats = pool_manager.get_pool_stats()
    
    print("\n" + "="*40)
    print("POOL STATISTICS")
    print("="*40)
    print(f"Total pools: {stats['total_pools']}")
    print(f"Custom pools: {stats['custom_pools']}")
    print(f"System pools: {stats['system_pools']}")
    
    print("\nBy role:")
    for key, value in stats.items():
        if key.endswith('_pools') and not key.startswith(('total', 'custom', 'system')):
            role = key.replace('_pools', '')
            print(f"  {role.capitalize()}: {value}")

def _select_pool_interactive(pool_manager, action_name="Select pool"):
    """Interactive pool selection with numbered choices."""
    pools = pool_manager.get_all_pools()
    if not pools:
        print("[ERROR] No pools found.")
        return None
    
    print(f"\n" + "="*50)
    print(f"{action_name.upper()}")
    print("="*50)
    print("Available pools:")
    
    # Create numbered list
    pool_list = []
    idx = 1
    for name, pool in sorted(pools.items()):
        pool_list.append((name, pool))
        status = "🔧" if pool.created_by == "system" else "👤"
        print(f"  {idx:>2}. {status} {name:<20} | {pool.role:<8} | {pool.size():>2} champs | {pool.description}")
        idx += 1
    
    try:
        choice = input(f"\nChoose pool (1-{len(pool_list)} or 'cancel'): ").strip()
        
        if choice.lower() == 'cancel':
            return None
        
        choice_num = int(choice)
        if 1 <= choice_num <= len(pool_list):
            selected_name, selected_pool = pool_list[choice_num - 1]
            return selected_pool
        else:
            print(f"[ERROR] Invalid choice. Please choose 1-{len(pool_list)}.")
            return None
            
    except ValueError:
        print("[ERROR] Invalid input. Please enter a number.")
        return None

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
    parser.add_argument(
        "--auto-hover",
        action="store_true",
        help="Enable automatic champion hovering in draft coach"
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
        
        run_draft_coach(args.verbose, auto_hover=args.auto_hover)
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
                
                # Ask about auto-hover
                hover_choice = input("\nEnable automatic champion hovering? (y/N): ").strip().lower()
                auto_hover = hover_choice == 'y'
                
                run_draft_coach(args.verbose, auto_hover=auto_hover)
                
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
                manage_champion_pools()
                input("\nPress Enter to return to menu...")
                
            elif choice == "7":
                print("\nGoodbye!")
                break
                
            else:
                print("\n[ERROR] Invalid option. Please choose 1-7.")
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