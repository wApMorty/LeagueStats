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
from src.config import config

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
  4. Analysis & Tournament     - Statistical analysis and manual tournament coaching
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
    db_path = config.DATABASE_PATH
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
        patch_input = input(f"Enter patch version (e.g., {config.CURRENT_PATCH}): ").strip()
        if patch_input:
            # Validate patch format (basic validation)
            parts = patch_input.split('.')
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return patch_input
            else:
                print(f"[ERROR] Invalid patch format. Use format like {config.CURRENT_PATCH}")
                return None
        else:
            print("[ERROR] Patch version cannot be empty")
            return None
    elif choice == "3":
        return None
    else:
        print("[ERROR] Invalid option")
        return None

def run_draft_coach(verbose=False, auto_hover=False, auto_accept_queue=False, auto_ban_hover=False, open_onetricks=None):
    """Run the real-time draft coach."""
    print("[INFO] Starting Real-time Draft Coach...")
    print("Make sure League of Legends client is running and start a game!")
    if auto_hover:
        print("🎯 [AUTO-HOVER] Champion auto-hover is ENABLED")
    if auto_accept_queue:
        print("🔥 [AUTO-ACCEPT] Queue auto-accept is ENABLED")
    if auto_ban_hover:
        print("🚫 [AUTO-BAN-HOVER] Ban hover is ENABLED")
    if open_onetricks:
        print("🌐 [ONETRICKS] Open champion page on draft completion is ENABLED")
    print("Press Ctrl+C to stop monitoring.\n")
    
    try:
        monitor = DraftMonitor(verbose=verbose, auto_select_pool=False, auto_hover=auto_hover, auto_accept_queue=auto_accept_queue, auto_ban_hover=auto_ban_hover, open_onetricks=open_onetricks)
        monitor.start_monitoring()
    except KeyboardInterrupt:
        print("\n[INFO] Draft Coach stopped by user")
    except Exception as e:
        print(f"[ERROR] Draft coach error: {e}")
        if verbose:
            import traceback
            traceback.print_exc()

def update_champion_data():
    """Update champion data with submenu."""
    print("\n" + "="*60)
    print("CHAMPION DATA MANAGEMENT")
    print("="*60)
    print("\nOptions:")
    print("1. Update Champion List        - Fetch latest champions from Riot API")
    print("2. Recalculate Champion Scores - Rebuild tier list scores from existing data")
    print("3. Back to main menu")

    choice = input("\nChoose option (1-3): ").strip()

    if choice == "1":
        _update_champion_list_from_riot()
    elif choice == "2":
        _recalculate_champion_scores()
    elif choice == "3":
        return
    else:
        print("[ERROR] Invalid option")

def _update_champion_list_from_riot():
    """Update champion list from Riot API."""
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

def _recalculate_champion_scores():
    """Recalculate champion scores for tier lists from existing matchup data."""
    print("\n[INFO] Recalculating Champion Scores for Tier Lists")
    print("="*60)
    print("\nThis will recalculate all champion scores from existing matchup data.")
    print("Useful after modifying tier list configuration or thresholds.")
    print("\nNote: This does NOT fetch new data from the web.")
    print("      Use 'Parse Match Statistics' to update matchup data first.")

    confirm = input("\nProceed with score calculation? (y/n): ").strip().lower()
    if confirm != 'y':
        print("[INFO] Cancelled")
        return

    try:
        from src.config import config
        from src.assistant import Assistant

        db = Database(config.DATABASE_PATH)
        db.connect()

        # Check if matchup data exists
        cursor = db.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM matchups")
        matchup_count = cursor.fetchone()[0]

        if matchup_count == 0:
            print("\n[ERROR] No matchup data found in database")
            print("[INFO] Please run 'Parse Match Statistics' first to populate matchup data")
            db.close()
            return

        print(f"\n[INFO] Found {matchup_count:,} matchups in database")

        # Initialize champion_scores table
        print("[INFO] Initializing champion_scores table...")
        db.init_champion_scores_table()

        # Calculate scores
        print("[INFO] Calculating global champion scores...")
        assistant = Assistant()
        champions_scored = assistant.calculate_global_scores()

        print(f"\n[SUCCESS] Successfully scored {champions_scored} champions")
        print("[INFO] Tier lists are now ready to use")

        assistant.close()
        db.close()

    except Exception as e:
        print(f"[ERROR] Calculation error: {e}")
        import traceback
        traceback.print_exc()

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
    print(f"This will take approximately {len(pool_champions)*0.5:.2f}-{len(pool_champions)*1:.2f} minutes...")
    
    confirm = input(f"\nProceed with parsing {len(pool_champions)} champions? (y/N): ").strip().lower()
    if confirm != 'y':
        print("[INFO] Parsing cancelled.")
        return
    
    try:
        from src.config import config
        from src.constants import normalize_champion_name_for_url
        db = Database(config.DATABASE_PATH)
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
        
        # Initialize matchups and champion_scores tables
        db.init_matchups_table()
        db.init_champion_scores_table()
        
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

        # Calculate global scores for tier lists
        print("\n[INFO] Calculating global champion scores for tier lists...")
        db.close()  # Close first DB connection before Assistant creates its own

        assistant = Assistant()
        champions_scored = assistant.calculate_global_scores()
        assistant.close()
        print(f"[SUCCESS] SoloQ Pool statistics updated! ({processed} champions, {total_inserted} total matchups, {champions_scored} scored)")
        
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
        from src.constants import CHAMPIONS_LIST, normalize_champion_name_for_url
        from src.config import config
        db = Database(config.DATABASE_PATH)
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
        db.init_champion_scores_table()
        
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

        # Calculate global scores for tier lists
        print("\n[INFO] Calculating global champion scores for tier lists...")
        db.close()  # Close first DB connection before Assistant creates its own

        assistant = Assistant()
        champions_scored = assistant.calculate_global_scores()
        assistant.close()
        print(f"[SUCCESS] All champion statistics updated! ({processed} champions, {total_inserted} total matchups, {champions_scored} scored)")
        
    except Exception as e:
        print(f"[ERROR] Parsing error: {e}")

def run_champion_analysis():
    """Run champion analysis and tournament coaching."""
    print("[INFO] Champion Analysis & Tournament Coaching")
    print("\nAvailable options:")
    print("1. Generate Tier List       - Create blind pick or counter pick tier lists")
    print("2. Tournament Draft Coach   - Manual coaching for external tournaments")
    print("3. Back to main menu")

    choice = input("\nChoose option (1-3): ").strip()

    if choice == "1":
        run_tier_list_generator()
    elif choice == "2":
        run_tournament_draft_coach()
    elif choice == "3":
        return
    else:
        print("[ERROR] Invalid option")

def run_statistical_analysis():
    """Run statistical champion analysis and tier lists (deprecated - use tier list generator)."""
    print("[INFO] Running statistical analysis...")

    try:
        ast = Assistant()

        print("\n=== COMPETITIVE DRAFT ANALYSIS ===")
        ast.competitive_draft(3)

        ast.close()
        print("\n[SUCCESS] Analysis completed!")

    except Exception as e:
        print(f"[ERROR] Analysis error: {e}")

def run_tier_list_generator():
    """Generate tier lists for champion pools."""
    print("[INFO] Tier List Generator")

    try:
        from src.assistant import Assistant

        # Step 1: Select champion pool
        print("\n" + "="*60)
        print("STEP 1: SELECT CHAMPION POOL")
        print("="*60)

        selected_pool_info = _select_pool_for_analysis()
        if not selected_pool_info:
            print("[ERROR] No pool selected")
            return

        pool_name, champion_pool = selected_pool_info
        print(f"\n✅ Selected pool: {pool_name} ({len(champion_pool)} champions)")

        # Step 2: Select analysis type
        print("\n" + "="*60)
        print("STEP 2: SELECT ANALYSIS TYPE")
        print("="*60)
        print("\nChoose tier list type:")
        print("  1. Blind Pick    - Champions with consistent performance across matchups")
        print("  2. Counter Pick  - Champions with high peaks in specific matchups")
        print("  3. Cancel")

        type_choice = input("\nChoice (1-3): ").strip()

        if type_choice == "1":
            analysis_type = "blind_pick"
            type_name = "BLIND PICK"
        elif type_choice == "2":
            analysis_type = "counter_pick"
            type_name = "COUNTER PICK"
        elif type_choice == "3":
            print("[INFO] Cancelled by user")
            return
        else:
            print("[ERROR] Invalid choice")
            return

        # Step 3: Generate tier list
        print("\n" + "="*60)
        print(f"GENERATING {type_name} TIER LIST...")
        print("="*60)

        assistant = Assistant()
        tier_list = assistant.generate_tier_list(champion_pool, analysis_type)
        assistant.close()

        if not tier_list:
            print("[WARNING] No champions with sufficient data found in pool")
            return

        # Step 4: Display results
        _display_tier_list(tier_list, pool_name, type_name, analysis_type)

    except Exception as e:
        print(f"[ERROR] Tier list generation error: {e}")
        import traceback
        traceback.print_exc()

def _display_tier_list(tier_list: List[dict], pool_name: str, type_name: str, analysis_type: str):
    """Display formatted tier list results."""
    from src.config import tierlist_config
    from src.assistant import safe_print

    print("\n" + "="*80)
    if analysis_type == "blind_pick":
        safe_print(f"🎯 {type_name} TIER LIST - {pool_name} ({len(tier_list)} champions)")
        print("Focus: Consistency and stability across all matchups")
    else:
        safe_print(f"⚔️ {type_name} TIER LIST - {pool_name} ({len(tier_list)} champions)")
        print("Focus: Situational power and counter potential")
    print("="*80)

    # Group by tier
    tiers = {'S': [], 'A': [], 'B': [], 'C': []}
    for entry in tier_list:
        tiers[entry['tier']].append(entry)

    # Display each tier
    tier_icons = {'S': '🟢', 'A': '🟡', 'B': '🟠', 'C': '🔴'}
    tier_ranges = {
        'S': f"{tierlist_config.S_TIER_THRESHOLD:.0f}-100",
        'A': f"{tierlist_config.A_TIER_THRESHOLD:.0f}-{tierlist_config.S_TIER_THRESHOLD:.0f}",
        'B': f"{tierlist_config.B_TIER_THRESHOLD:.0f}-{tierlist_config.A_TIER_THRESHOLD:.0f}",
        'C': f"0-{tierlist_config.B_TIER_THRESHOLD:.0f}"
    }

    for tier_letter in ['S', 'A', 'B', 'C']:
        champions_in_tier = tiers[tier_letter]
        if not champions_in_tier:
            continue

        tier_desc = {
            'S': 'Elite' if analysis_type == 'blind_pick' else 'Premium counterpicks',
            'A': 'Strong' if analysis_type == 'blind_pick' else 'Strong counterpicks',
            'B': 'Situational' if analysis_type == 'blind_pick' else 'Niche counterpicks',
            'C': 'Weak' if analysis_type == 'blind_pick' else 'Limited value'
        }

        safe_print(f"\n{tier_icons[tier_letter]} {tier_letter}-TIER ({tier_ranges[tier_letter]}) - {tier_desc[tier_letter]}")

        for i, entry in enumerate(champions_in_tier, 1):
            champion = entry['champion']
            score = entry['score']
            metrics = entry['metrics']

            print(f"  {i}. {champion:<15} | Score: {score:>5.1f} / 100")

            # Display metrics based on analysis type
            if analysis_type == "blind_pick":
                avg_delta2 = metrics['avg_delta2_raw']
                variance = metrics['variance']
                coverage = metrics['coverage_raw']
                safe_print(f"     📊 Avg Delta2:   {avg_delta2:>+5.2f}  (Performance)")
                safe_print(f"     📈 Stability:    {metrics['stability']:>5.2f}  (Variance: {variance:.2f})")
                safe_print(f"     ✅ Coverage:     {coverage:>5.1%}  (Decent matchups)")

            elif analysis_type == "counter_pick":
                peak_impact = metrics['peak_impact_raw']
                variance = metrics['variance']
                target_ratio = metrics['target_ratio_raw']
                safe_print(f"     💥 Peak Impact:  {peak_impact:>5.2f}  (Weighted good matchups)")
                safe_print(f"     📊 Volatility:   {variance:>5.2f}  (High = situational)")
                safe_print(f"     🎯 Targets:      {target_ratio:>5.1%}  (Viable counterpick %)")

            print()

    # Summary footer
    print("="*80)
    safe_print("💡 TIER LIST CONFIGURATION:")
    if analysis_type == "blind_pick":
        safe_print(f"   • Weights: Performance {tierlist_config.BLIND_AVG_WEIGHT:.0%}, "
                   f"Stability {tierlist_config.BLIND_STABILITY_WEIGHT:.0%}, "
                   f"Coverage {tierlist_config.BLIND_COVERAGE_WEIGHT:.0%}")
    else:
        safe_print(f"   • Weights: Peak Impact {tierlist_config.COUNTER_PEAK_WEIGHT:.0%}, "
                   f"Volatility {tierlist_config.COUNTER_VOLATILITY_WEIGHT:.0%}, "
                   f"Targets {tierlist_config.COUNTER_TARGETS_WEIGHT:.0%}")
    safe_print(f"   • Thresholds: S≥{tierlist_config.S_TIER_THRESHOLD:.0f}, "
               f"A≥{tierlist_config.A_TIER_THRESHOLD:.0f}, "
               f"B≥{tierlist_config.B_TIER_THRESHOLD:.0f}")
    print("="*80)

def run_tournament_draft_coach():
    """Manual draft coaching for tournament scenarios."""
    print("[INFO] Tournament Draft Coach")
    print("Perfect for external tournaments, scrimmages, or any draft outside the League client")
    print("\nThis tool provides the same coaching logic as the real-time coach,")
    print("but allows you to manually input pick/ban information.")
    
    try:
        from src.tournament_coach import TournamentCoach
        coach = TournamentCoach()
        coach.start_coaching_session()
        
    except ImportError:
        # If the module doesn't exist yet, create a basic implementation
        print("\n[INFO] Starting tournament coaching session...")
        _run_basic_tournament_coach()
    except Exception as e:
        print(f"[ERROR] Tournament coach error: {e}")

def _run_basic_tournament_coach():
    """Enhanced tournament coaching implementation with full features."""
    from src.assistant import Assistant
    from src.pool_manager import PoolManager
    import time
    import json

    try:
        assistant = Assistant()

        # Select coaching pool
        print("\n" + "="*60)
        print("SELECT CHAMPION POOL FOR COACHING")
        print("="*60)

        selected_pool_info = _select_pool_for_analysis()
        if not selected_pool_info:
            print("[WARNING] No pool selected, using assistant's extended pool")
            champion_pool = assistant.select_extended_champion_pool()
            pool_name = "Extended Pool"
        else:
            pool_name, champion_pool = selected_pool_info

        print(f"\n✅ Using pool: {pool_name} ({len(champion_pool)} champions)")

        # Initialize draft state
        ally_team = []
        enemy_team = []
        banned_champions = []
        draft_history = []  # (timestamp, action, champion, side)
        auto_recommend = True  # Auto-show recommendations after picks

        print("\n" + "="*80)
        print("🎯 TOURNAMENT DRAFT COACHING SESSION")
        print("="*80)
        _show_tournament_help()

        while True:
            try:
                cmd = input("\n⚡ Coach > ").strip().lower()

                if cmd in ["quit", "exit", "q"]:
                    break

                elif cmd == "status":
                    _show_tournament_draft_state(assistant, ally_team, enemy_team, banned_champions, champion_pool)

                elif cmd == "reset":
                    ally_team.clear()
                    enemy_team.clear()
                    banned_champions.clear()
                    draft_history.clear()
                    print("✅ Draft state reset!")

                elif cmd == "recommend":
                    _show_recommendations(assistant, enemy_team, ally_team, banned_champions, champion_pool, 5)

                elif cmd == "analyze":
                    if len(ally_team) == 5 and len(enemy_team) == 5:
                        _analyze_complete_draft(assistant, ally_team, enemy_team)
                    else:
                        print(f"⚠️ Draft incomplete: {len(ally_team)}/5 ally, {len(enemy_team)}/5 enemy")

                elif cmd.startswith("ally "):
                    champ_input = cmd[5:].strip()
                    champ = assistant.validate_champion_name(champ_input)
                    if champ:
                        if champ in ally_team:
                            print(f"⚠️ {champ} already in your team")
                        elif champ in enemy_team:
                            print(f"⚠️ {champ} already picked by enemy")
                        elif champ in banned_champions:
                            print(f"⚠️ {champ} is banned")
                        elif len(ally_team) >= 5:
                            print(f"⚠️ Your team is full (5/5)")
                        else:
                            ally_team.append(champ)
                            draft_history.append((time.time(), "ally", champ, "ally"))
                            print(f"✅ Added {champ} to your team ({len(ally_team)}/5)")
                            if auto_recommend and enemy_team:
                                print(f"\n📊 Top picks after adding {champ}:")
                                _show_recommendations(assistant, enemy_team, ally_team, banned_champions, champion_pool, 3)

                elif cmd.startswith("enemy "):
                    champ_input = cmd[6:].strip()
                    champ = assistant.validate_champion_name(champ_input)
                    if champ:
                        if champ in enemy_team:
                            print(f"⚠️ {champ} already in enemy team")
                        elif champ in ally_team:
                            print(f"⚠️ {champ} already picked by you")
                        elif champ in banned_champions:
                            print(f"⚠️ {champ} is banned")
                        elif len(enemy_team) >= 5:
                            print(f"⚠️ Enemy team is full (5/5)")
                        else:
                            enemy_team.append(champ)
                            draft_history.append((time.time(), "enemy", champ, "enemy"))
                            print(f"✅ Enemy picked {champ} ({len(enemy_team)}/5)")
                            if auto_recommend:
                                print(f"\n📊 Best counters to {champ}:")
                                _show_recommendations(assistant, enemy_team, ally_team, banned_champions, champion_pool, 3)

                elif cmd.startswith("ban "):
                    champ_input = cmd[4:].strip()
                    champ = assistant.validate_champion_name(champ_input)
                    if champ:
                        if champ in banned_champions:
                            print(f"⚠️ {champ} already banned")
                        elif champ in ally_team or champ in enemy_team:
                            print(f"⚠️ {champ} already picked")
                        else:
                            banned_champions.append(champ)
                            draft_history.append((time.time(), "ban", champ, "ban"))
                            print(f"✅ Banned {champ}")

                elif cmd.startswith("remove ally "):
                    champ_input = cmd[12:].strip()
                    champ = assistant.validate_champion_name(champ_input)
                    if champ and champ in ally_team:
                        ally_team.remove(champ)
                        draft_history.append((time.time(), "remove_ally", champ, "ally"))
                        print(f"✅ Removed {champ} from your team")
                    else:
                        print(f"⚠️ {champ_input} not in your team")

                elif cmd.startswith("remove enemy "):
                    champ_input = cmd[13:].strip()
                    champ = assistant.validate_champion_name(champ_input)
                    if champ and champ in enemy_team:
                        enemy_team.remove(champ)
                        draft_history.append((time.time(), "remove_enemy", champ, "enemy"))
                        print(f"✅ Removed {champ} from enemy team")
                    else:
                        print(f"⚠️ {champ_input} not in enemy team")

                elif cmd.startswith("remove ban "):
                    champ_input = cmd[11:].strip()
                    champ = assistant.validate_champion_name(champ_input)
                    if champ and champ in banned_champions:
                        banned_champions.remove(champ)
                        draft_history.append((time.time(), "unban", champ, "ban"))
                        print(f"✅ Unbanned {champ}")
                    else:
                        print(f"⚠️ {champ_input} not in ban list")

                elif cmd == "history":
                    _show_draft_history(draft_history)

                elif cmd == "undo":
                    if draft_history:
                        ts, action, champ, side = draft_history.pop()
                        if action == "ally":
                            ally_team.remove(champ)
                            print(f"↩️ Undone: {champ} removed from ally team")
                        elif action == "enemy":
                            enemy_team.remove(champ)
                            print(f"↩️ Undone: {champ} removed from enemy team")
                        elif action == "ban":
                            banned_champions.remove(champ)
                            print(f"↩️ Undone: {champ} unbanned")
                        elif action.startswith("remove"):
                            # Can't undo removes easily, skip
                            print(f"⚠️ Can't undo remove action")
                    else:
                        print("⚠️ No actions to undo")

                elif cmd.startswith("import "):
                    _handle_import_command(cmd, assistant, ally_team, enemy_team, banned_champions, draft_history)

                elif cmd == "export":
                    _export_draft(ally_team, enemy_team, banned_champions, pool_name)

                elif cmd == "auto on":
                    auto_recommend = True
                    print("✅ Auto-recommendations enabled")
                elif cmd == "auto off":
                    auto_recommend = False
                    print("✅ Auto-recommendations disabled")

                elif cmd in ["help", "h", "?"]:
                    _show_tournament_help()

                elif cmd == "":
                    continue

                else:
                    print(f"❌ Unknown command: '{cmd}'. Type 'help' for available commands.")

            except KeyboardInterrupt:
                print("\n\n👋 Exiting tournament coach...")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                if "--debug" in sys.argv:
                    import traceback
                    traceback.print_exc()

        assistant.close()
        print("\n✅ Tournament coaching session ended!")

    except Exception as e:
        print(f"❌ Tournament coaching error: {e}")
        import traceback
        traceback.print_exc()

def _show_tournament_help():
    """Display tournament coach help."""
    print("\n📖 TOURNAMENT COACH COMMANDS")
    print("="*60)
    print("DRAFT MANAGEMENT:")
    print("  ally <champion>          - Add champion to your team")
    print("  enemy <champion>         - Add champion to enemy team")
    print("  ban <champion>           - Add champion to ban list")
    print("  remove ally/enemy/ban <champion> - Remove champion")
    print()
    print("ANALYSIS:")
    print("  status                   - Show current draft state with scores")
    print("  recommend                - Get champion recommendations")
    print("  analyze                  - Full analysis (when both teams complete)")
    print("  history                  - Show draft action history")
    print()
    print("UTILITIES:")
    print("  undo                     - Undo last action")
    print("  reset                    - Clear entire draft")
    print("  auto on/off              - Toggle auto-recommendations")
    print("  export                   - Save draft to JSON file")
    print("  import <type>: <champs>  - Quick import (see examples below)")
    print()
    print("  help, h, ?               - Show this help")
    print("  quit, exit, q            - Exit coach")
    print()
    print("IMPORT EXAMPLES:")
    print("  import ally: Aatrox, Graves, Ahri")
    print("  import enemy: Gwen, Lee Sin, Syndra")
    print("  import bans: Yone, Yasuo, Zed")
    print("="*60)

def _show_tournament_draft_state(assistant, ally_team, enemy_team, banned_champions, champion_pool):
    """Show enhanced tournament draft state with individual champion scores."""
    print(f"\n" + "="*70)
    print("📋 CURRENT DRAFT STATE")
    print("="*70)

    # Show teams with individual scores
    print(f"\n🟦 YOUR TEAM ({len(ally_team)}/5):")
    if ally_team:
        for champ in ally_team:
            matchups = assistant.db.get_champion_matchups_by_name(champ)
            if matchups and enemy_team:
                advantage = assistant.score_against_team(matchups, enemy_team, champ)
                if advantage >= 2.0:
                    status = "✅ Strong"
                elif advantage >= 0:
                    status = "🟡 Good"
                else:
                    status = "🔴 Weak"
                print(f"  • {champ:<15} {status:>10}  ({advantage:+.2f}%)")
            else:
                print(f"  • {champ:<15}")
    else:
        print("  (No picks yet)")

    print(f"\n🟥 ENEMY TEAM ({len(enemy_team)}/5):")
    if enemy_team:
        for champ in enemy_team:
            print(f"  • {champ}")
    else:
        print("  (No picks yet)")

    print(f"\n🚫 BANNED CHAMPIONS ({len(banned_champions)}):")
    if banned_champions:
        print(f"  {', '.join(banned_champions)}")
    else:
        print("  (None)")

    # Show progress
    remaining_ally = 5 - len(ally_team)
    remaining_enemy = 5 - len(enemy_team)
    print(f"\n📊 REMAINING PICKS:")
    print(f"  You: {remaining_ally}  |  Enemy: {remaining_enemy}")

    # Show team winrate estimate if both teams have picks
    if len(ally_team) >= 3 and len(enemy_team) >= 3:
        print(f"\n💯 DRAFT ADVANTAGE:")
        ally_advantages = []
        for champ in ally_team:
            matchups = assistant.db.get_champion_matchups_by_name(champ)
            if matchups:
                adv = assistant.score_against_team(matchups, enemy_team, champ)
                ally_advantages.append(adv)

        if ally_advantages:
            avg_advantage = sum(ally_advantages) / len(ally_advantages)
            if avg_advantage >= 2.0:
                print(f"  ✅ Strong advantage ({avg_advantage:+.2f}% avg)")
            elif avg_advantage >= 0:
                print(f"  🟡 Slight advantage ({avg_advantage:+.2f}% avg)")
            else:
                print(f"  🔴 Disadvantage ({avg_advantage:+.2f}% avg)")

    print("="*70)

def _show_recommendations(assistant, enemy_team, ally_team, banned_champions, champion_pool, nb_results):
    """Show formatted recommendations."""
    if not enemy_team and not ally_team:
        print("⚠️ No picks yet. Add enemy picks first for meaningful recommendations.")
        return

    print(f"\n🎯 TOP {nb_results} RECOMMENDATIONS:")
    print("-" * 50)
    assistant._calculate_and_display_recommendations(
        enemy_team, ally_team, nb_results, champion_pool, banned_champions
    )

def _show_draft_history(draft_history):
    """Display draft action history."""
    if not draft_history:
        print("📜 No actions yet")
        return

    print(f"\n📜 DRAFT HISTORY ({len(draft_history)} actions):")
    print("-" * 60)
    for i, (ts, action, champ, side) in enumerate(draft_history, 1):
        action_icons = {
            "ally": "🟦",
            "enemy": "🟥",
            "ban": "🚫",
            "remove_ally": "↩️🟦",
            "remove_enemy": "↩️🟥",
            "unban": "↩️🚫"
        }
        icon = action_icons.get(action, "•")
        print(f"  {i:2}. {icon} {action.upper():<12} {champ}")

def _analyze_complete_draft(assistant, ally_team, enemy_team):
    """Analyze complete draft using same logic as draft monitor."""
    print("\n" + "="*80)
    print("🎯 COMPLETE DRAFT ANALYSIS")
    print("="*80)

    # Calculate individual scores
    ally_scores = []
    for champ in ally_team:
        matchups = assistant.db.get_champion_matchups_by_name(champ)
        if matchups:
            advantage = assistant.score_against_team(matchups, enemy_team, champ)
            ally_scores.append((champ, advantage))
        else:
            ally_scores.append((champ, None))

    enemy_scores = []
    for champ in enemy_team:
        matchups = assistant.db.get_champion_matchups_by_name(champ)
        if matchups:
            advantage = assistant.score_against_team(matchups, ally_team, champ)
            enemy_scores.append((champ, advantage))
        else:
            enemy_scores.append((champ, None))

    # Sort by advantage
    ally_scores.sort(key=lambda x: x[1] if x[1] is not None else -999, reverse=True)
    enemy_scores.sort(key=lambda x: x[1] if x[1] is not None else -999, reverse=True)

    # Display ally team
    print(f"\n🟦 YOUR TEAM PERFORMANCE:")
    print("-" * 60)
    for champ, advantage in ally_scores:
        if advantage is None:
            print(f"  {champ:<15} | ❌ Insufficient data")
        elif advantage >= 2.0:
            print(f"  {champ:<15} | ✅ {advantage:+.2f}% (Excellent)")
        elif advantage >= 1.0:
            print(f"  {champ:<15} | 🟢 {advantage:+.2f}% (Good)")
        elif advantage >= -1.0:
            print(f"  {champ:<15} | 🟡 {advantage:+.2f}% (Neutral)")
        elif advantage >= -2.0:
            print(f"  {champ:<15} | 🟠 {advantage:.2f}% (Bad)")
        else:
            print(f"  {champ:<15} | 🔴 {advantage:.2f}% (Very Bad)")

    # Display enemy team
    print(f"\n🟥 ENEMY TEAM PERFORMANCE:")
    print("-" * 60)
    for champ, advantage in enemy_scores:
        if advantage is None:
            print(f"  {champ:<15} | ❌ Insufficient data")
        elif advantage >= 2.0:
            print(f"  {champ:<15} | ⚠️ {advantage:+.2f}% (Strong vs us)")
        elif advantage >= 1.0:
            print(f"  {champ:<15} | 🟡 {advantage:+.2f}% (Good vs us)")
        elif advantage >= -1.0:
            print(f"  {champ:<15} | ➖ {advantage:+.2f}% (Neutral)")
        elif advantage >= -2.0:
            print(f"  {champ:<15} | 🟢 {advantage:.2f}% (Weak vs us)")
        else:
            print(f"  {champ:<15} | ✅ {advantage:.2f}% (Very weak vs us)")

    # Team winrate calculation using geometric mean
    ally_valid = [adv for _, adv in ally_scores if adv is not None]
    enemy_valid = [adv for _, adv in enemy_scores if adv is not None]

    if ally_valid and enemy_valid:
        print(f"\n📊 TEAM MATCHUP PREDICTION:")
        print("-" * 60)

        # Convert to winrates and use geometric mean
        ally_winrates = [50.0 + adv for adv in ally_valid]
        enemy_winrates = [50.0 + adv for adv in enemy_valid]

        ally_team_stats = assistant._calculate_team_winrate(ally_winrates)
        enemy_team_stats = assistant._calculate_team_winrate(enemy_winrates)

        # Normalize to 100%
        total = ally_team_stats['team_winrate'] + enemy_team_stats['team_winrate']
        ally_normalized = (ally_team_stats['team_winrate'] / total) * 100
        enemy_normalized = (enemy_team_stats['team_winrate'] / total) * 100

        print(f"  Your team:   {ally_normalized:.1f}%")
        print(f"  Enemy team:  {enemy_normalized:.1f}%")

        diff = ally_normalized - enemy_normalized
        if diff >= 5.0:
            print(f"\n  ✅ Major advantage ({diff:+.1f}%)")
        elif diff >= 2.5:
            print(f"\n  🟢 Good advantage ({diff:+.1f}%)")
        elif diff >= -2.5:
            print(f"\n  🟡 Even matchup ({diff:+.1f}%)")
        elif diff >= -5.0:
            print(f"\n  🟠 Disadvantage ({diff:.1f}%)")
        else:
            print(f"\n  🔴 Major disadvantage ({diff:.1f}%)")

    print("\n" + "="*80)

def _handle_import_command(cmd, assistant, ally_team, enemy_team, banned_champions, draft_history):
    """Handle import commands for quick draft entry."""
    import time

    try:
        # Format: import ally: Aatrox, Jax, Ahri
        if ":" not in cmd:
            print("⚠️ Import format: import <type>: <champion1>, <champion2>, ...")
            print("   Example: import ally: Aatrox, Graves, Ahri")
            return

        parts = cmd.split(":", 1)
        cmd_part = parts[0].strip().lower()
        champs_part = parts[1].strip()

        target_type = cmd_part.replace("import ", "").strip()

        if target_type not in ["ally", "enemy", "bans", "ban"]:
            print(f"⚠️ Unknown import type: {target_type}. Use: ally, enemy, or bans")
            return

        # Parse champion names
        champ_names = [c.strip() for c in champs_part.split(",")]

        imported = 0
        for champ_input in champ_names:
            champ = assistant.validate_champion_name(champ_input)
            if not champ:
                continue

            if target_type == "ally":
                if champ not in ally_team and len(ally_team) < 5:
                    ally_team.append(champ)
                    draft_history.append((time.time(), "ally", champ, "ally"))
                    imported += 1
            elif target_type == "enemy":
                if champ not in enemy_team and len(enemy_team) < 5:
                    enemy_team.append(champ)
                    draft_history.append((time.time(), "enemy", champ, "enemy"))
                    imported += 1
            elif target_type in ["bans", "ban"]:
                if champ not in banned_champions:
                    banned_champions.append(champ)
                    draft_history.append((time.time(), "ban", champ, "ban"))
                    imported += 1

        print(f"✅ Imported {imported}/{len(champ_names)} champions to {target_type}")

    except Exception as e:
        print(f"❌ Import error: {e}")

def _export_draft(ally_team, enemy_team, banned_champions, pool_name):
    """Export draft to JSON file."""
    import json
    import time
    from datetime import datetime

    timestamp = int(time.time())
    filename = f"draft_{timestamp}.json"

    draft_data = {
        "timestamp": timestamp,
        "datetime": datetime.fromtimestamp(timestamp).isoformat(),
        "pool": pool_name,
        "ally_team": ally_team,
        "enemy_team": enemy_team,
        "banned_champions": banned_champions,
        "version": "1.0"
    }

    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(draft_data, f, indent=2, ensure_ascii=False)
        print(f"✅ Draft exported to: {filename}")
    except Exception as e:
        print(f"❌ Export failed: {e}")

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
            _offer_save_optimization_result([blind, counter1, counter2], f"Optimal Trio (Score: {score:.2f})")
            
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
                    _offer_save_optimization_result(duo_champions, f"Optimal Duo for {champion} (Score: {score:.2f})")
            else:
                print("[ERROR] No champion name provided")
                
        elif choice == "3":
            print(f"\n" + "="*60)
            print(f"HOLISTIC TRIO COMBINATIONS ANALYSIS")
            print("="*60)
            print(f"Analyzing all possible trio combinations from your pool...")
            print(f"This evaluates trios as complete units rather than blind pick + counterpicks")
            
            # Ask user for scoring profile
            scoring_profile = _select_scoring_profile()
            
            # Run the holistic trio analysis
            trio_results = ast.find_optimal_trios_holistic(selected_pool, num_results=5, profile=scoring_profile)
            
            # Display results
            _display_holistic_trio_results(trio_results, scoring_profile)
            
            # Offer to save the best trio
            if trio_results:
                best_trio = trio_results[0]['trio']
                best_score = trio_results[0]['total_score']
                _offer_save_optimization_result(list(best_trio), f"Holistic Trio (Score: {best_score:.2f})")
                
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
            time_est = f"~{pool.size()*0.5:.2f}-{pool.size()*1:.2f}min"
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

def _select_scoring_profile() -> str:
    """Ask user to select a scoring profile for trio analysis."""
    print(f"\n" + "="*50)
    print("SELECT SCORING PROFILE")
    print("="*50)
    print("Choose your preferred analysis style:")
    print()
    print("  1. SAFE       - Prioritizes consistency and balance over raw performance")
    print("                  Best for: Risk-averse players, ranked climbing")
    print()
    print("  2. META       - Focuses on performance against popular champions")
    print("                  Best for: Current patch adaptation, high elo play")
    print()
    print("  3. AGGRESSIVE - Maximizes coverage and diverse champion profiles")
    print("                  Best for: Proactive players, team flexibility")
    print()
    print("  4. BALANCED   - Mathematical weights with no bias")
    print("                  Best for: Default choice, general use")
    print()
    
    profile_map = {
        "1": "safe",
        "2": "meta", 
        "3": "aggressive",
        "4": "balanced"
    }
    
    while True:
        choice = input("Choose scoring profile (1-4): ").strip()
        
        if choice in profile_map:
            selected_profile = profile_map[choice]
            profile_names = {
                "safe": "SAFE",
                "meta": "META", 
                "aggressive": "AGGRESSIVE",
                "balanced": "BALANCED"
            }
            print(f"\nSelected profile: {profile_names[selected_profile]}")
            return selected_profile
        else:
            print("[ERROR] Invalid choice. Please select 1-4.")

def _display_holistic_trio_results(trio_results: List[dict], profile: str = "balanced"):
    """Display the results of holistic trio analysis in a clear format."""
    try:
        if not trio_results:
            print("No viable trios found")
            return
        
        # Display profile info
        profile_names = {
            "safe": "SAFE (Consistency Focus)",
            "meta": "META (Popular Champions Focus)", 
            "aggressive": "AGGRESSIVE (Coverage Focus)",
            "balanced": "BALANCED (Mathematical Weights)"
        }
        
        print(f"\nTOP TRIO COMBINATIONS FOUND:")
        print(f"Analysis Profile: {profile_names.get(profile, profile.upper())}")
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
            print(f"   🎯 Total Score: {total:>5.2f}/100")
            print(f"   📊 Coverage:    {coverage:>5.2f}/100  (Enemy matchup coverage)")
            print(f"   ⚖️  Balance:     {balance:>5.2f}/100  (Diverse profiles)")
            print(f"   📈 Consistency: {consistency:>5.2f}/100  (Reliable performance)")
            print(f"   🌟 Meta:        {meta:>5.2f}/100  (vs popular picks)")
            
            # Show some enemy coverage examples for top trio
            if i == 1 and 'enemy_coverage' in result:
                coverage_data = result['enemy_coverage']
                if coverage_data:
                    print(f"   Best matchups: ", end="")
                    top_matchups = sorted(coverage_data.items(), key=lambda x: x[1][0], reverse=True)[:3]
                    matchup_strs = [f"{enemy}(+{delta2:.2f})" for enemy, (delta2, _) in top_matchups if delta2 > 0]
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
    parser.add_argument(
        "--auto-accept-queue",
        action="store_true",
        help="Enable automatic queue acceptance when matchmaking finds a game"
    )
    parser.add_argument(
        "--auto-ban-hover",
        action="store_true",
        help="Enable automatic ban hovering during ban phases"
    )
    parser.add_argument(
        "--open-onetricks",
        action="store_true",
        help="Open champion page on Onetricks.gg when draft completes"
    )
    parser.add_argument(
        "--no-onetricks",
        action="store_true",
        help="Disable opening champion page on Onetricks.gg (overrides config default)"
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
        
        # Determine open_onetricks setting from command line args
        if args.no_onetricks:
            open_onetricks = False
        elif args.open_onetricks:
            open_onetricks = True
        else:
            open_onetricks = None  # Use config default
        
        run_draft_coach(args.verbose, auto_hover=args.auto_hover, auto_accept_queue=args.auto_accept_queue, auto_ban_hover=args.auto_ban_hover, open_onetricks=open_onetricks)
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
                
                # Ask about auto-accept queue
                accept_choice = input("Enable automatic queue acceptance? (y/N): ").strip().lower()
                auto_accept_queue = accept_choice == 'y'
                
                # Ask about auto-ban-hover
                ban_hover_choice = input("Enable automatic ban hovering? (y/N): ").strip().lower()
                auto_ban_hover = ban_hover_choice == 'y'
                
                # Ask about opening Onetricks.gg page
                onetricks_choice = input("Open champion page on Onetricks.gg when draft completes? (Y/n): ").strip().lower()
                open_onetricks = onetricks_choice != 'n'  # Default to True unless explicitly 'n'
                
                run_draft_coach(args.verbose, auto_hover=auto_hover, auto_accept_queue=auto_accept_queue, auto_ban_hover=auto_ban_hover, open_onetricks=open_onetricks)
                
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