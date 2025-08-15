import time
import json
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from .lcu_client import LCUClient
from .assistant import Assistant, safe_print
from .constants import SOLOQ_POOL, ROLE_POOLS

@dataclass
class ChampionAction:
    """Represents a champion pick/ban action."""
    champion_id: int
    champion_name: str
    actor_cell_id: int
    action_type: str  # "pick" or "ban"
    is_ally: bool
    completed: bool

@dataclass 
class DraftState:
    """Current state of the draft."""
    phase: str = ""
    ally_picks: List[str] = field(default_factory=list)
    enemy_picks: List[str] = field(default_factory=list)
    ally_bans: List[str] = field(default_factory=list)
    enemy_bans: List[str] = field(default_factory=list)
    current_actor: Optional[int] = None
    local_player_cell_id: Optional[int] = None
    
    def get_all_picks(self) -> List[str]:
        """Get all picked champions."""
        return self.ally_picks + self.enemy_picks
    
    def get_all_actions(self) -> List[str]:
        """Get all picks and bans."""
        return self.ally_picks + self.enemy_picks + self.ally_bans + self.enemy_bans

class DraftMonitor:
    """Monitors League of Legends champion select and provides coaching."""
    
    def __init__(self, verbose: bool = False, auto_select_pool: bool = True, auto_hover: bool = False):
        self.lcu = LCUClient(verbose=verbose)
        self.assistant = Assistant()
        self.last_draft_state = DraftState()
        self.champion_id_to_name: Dict[int, str] = {}  # Riot ID -> Display name
        self.is_monitoring = False
        self.verbose = verbose
        self.current_pool = SOLOQ_POOL  # Default pool
        self.auto_select_pool = auto_select_pool
        self.auto_hover = auto_hover
        self.last_recommendation = None  # Track last recommendation to avoid spam
        self.has_done_initial_hover = False  # Track if we've done the initial hover
        
    def start_monitoring(self):
        """Start monitoring champion select."""
        print("[BOT] League Draft Coach - Starting...")
        
        if not self.lcu.connect():
            return False
        
        # Load champion ID mappings
        self._load_champion_mappings()
        
        # Pool selection
        if not self.auto_select_pool:
            self.current_pool = self._select_champion_pool_interactive()
        else:
            # Auto-select top pool by default
            self.current_pool = ROLE_POOLS["top"]
            safe_print(f"✅ Using pool: TOP ({', '.join(self.current_pool)})")
        
        self.is_monitoring = True
        print("[WATCH] Monitoring for champion select...")
        print("   (Start a game to see draft recommendations)")
        print("   (Press Ctrl+C to stop)")
        
        try:
            while self.is_monitoring:
                self._monitor_loop()
                time.sleep(1)  # Check every second
        except KeyboardInterrupt:
            print("\n[STOP] Stopping draft monitor...")
        finally:
            self.cleanup()
    
    def stop_monitoring(self):
        """Stop monitoring."""
        self.is_monitoring = False
    
    def _monitor_loop(self):
        """Main monitoring loop."""
        try:
            if not self.lcu.is_in_champion_select():
                # Calculate final scores before leaving champ select
                if self.last_draft_state.phase and (self.last_draft_state.ally_picks or self.last_draft_state.enemy_picks):
                    print("\n[INFO] Left champion select - Draft completed!")
                    
                    # Calculate final team scores
                    ally_picks = self.last_draft_state.ally_picks
                    enemy_picks = self.last_draft_state.enemy_picks
                    
                    if ally_picks and enemy_picks:
                        try:
                            self._calculate_final_scores(ally_picks, enemy_picks)
                        except Exception as e:
                            print(f"[ERROR] Failed to calculate final analysis: {e}")
                            if self.verbose:
                                import traceback
                                traceback.print_exc()
                    
                    # Reset state after analysis
                    self.last_draft_state = DraftState()
                    self.has_done_initial_hover = False  # Reset for next game
                return
            
            # Get current champion select data
            champ_select_data = self.lcu.get_champion_select_session()
            if not champ_select_data:
                return
                
            # Parse draft state
            current_state = self._parse_draft_state(champ_select_data)
            
            # Check for changes and provide recommendations
            if self._has_draft_changed(current_state):
                self._handle_draft_change(current_state)
                self.last_draft_state = current_state
                
        except Exception as e:
            if self.verbose:
                print(f"[WARNING] Monitor error: {e}")
    
    def _load_champion_mappings(self):
        """Load champion mappings from database (now using Riot IDs)."""
        try:
            # Use the centralized database method
            self.champion_id_to_name = self.assistant.db.get_all_champion_names()
            
            if self.verbose:
                print(f"[DATA] Loaded {len(self.champion_id_to_name)} champion mappings from database")
                
        except Exception as e:
            if self.verbose:
                print(f"[WARNING] Error loading champion mappings: {e}")
    
    def _get_display_name(self, champion_id: int) -> str:
        """Get display name for champion ID."""
        return self.champion_id_to_name.get(champion_id, f"Champion{champion_id}")
    
    def _calculate_score_against_team(self, matchups: List[tuple], enemy_team: List[int]) -> float:
        """Calculate average delta2 score against enemy team."""
        if not matchups or not enemy_team:
            return 0.0
        
        # Convert matchups to dict for faster lookup
        matchup_dict = {enemy_id: delta2 for enemy_id, winrate, delta1, delta2, pickrate, games in matchups}
        
        # Calculate average delta2 against picked enemies
        relevant_scores = []
        for enemy_id in enemy_team:
            if enemy_id in matchup_dict:
                relevant_scores.append(matchup_dict[enemy_id])
        
        if not relevant_scores:
            return 0.0
            
        return sum(relevant_scores) / len(relevant_scores)
    
    def _parse_draft_state(self, champ_select_data: Dict) -> DraftState:
        """Parse champion select data into DraftState."""
        state = DraftState()
        
        # Get basic info
        state.phase = champ_select_data.get('timer', {}).get('phase', '')
        state.local_player_cell_id = champ_select_data.get('localPlayerCellId')
        
        # Parse team composition
        my_team = champ_select_data.get('myTeam', [])
        their_team = champ_select_data.get('theirTeam', [])
        
        # Process ally team
        for player in my_team:
            champ_id = player.get('championId', 0)
            if champ_id > 0:  # 0 means no champion selected
                state.ally_picks.append(champ_id)  # Store Riot ID directly
        
        # Process enemy team  
        for player in their_team:
            champ_id = player.get('championId', 0)
            if champ_id > 0:
                state.enemy_picks.append(champ_id)  # Store Riot ID directly
        
        # Parse bans
        bans_session = champ_select_data.get('bans', {})
        my_team_bans = bans_session.get('myTeamBans', [])
        their_team_bans = bans_session.get('theirTeamBans', [])
        
        for ban_id in my_team_bans:
            if ban_id > 0:
                state.ally_bans.append(ban_id)  # Store Riot ID directly
        
        for ban_id in their_team_bans:
            if ban_id > 0:
                state.enemy_bans.append(ban_id)  # Store Riot ID directly
        
        # Find current actor (who's supposed to pick/ban now)
        for action_set in champ_select_data.get('actions', []):
            for action in action_set:
                if not action.get('completed', False):
                    state.current_actor = action.get('actorCellId')
                    break
            if state.current_actor:
                break
        
        return state
    
    def _has_draft_changed(self, current_state: DraftState) -> bool:
        """Check if draft state has changed significantly."""
        return (
            current_state.ally_picks != self.last_draft_state.ally_picks or
            current_state.enemy_picks != self.last_draft_state.enemy_picks or
            current_state.ally_bans != self.last_draft_state.ally_bans or
            current_state.enemy_bans != self.last_draft_state.enemy_bans or
            current_state.phase != self.last_draft_state.phase
        )
    
    def _handle_draft_change(self, state: DraftState):
        """Handle draft state change and provide recommendations."""
        print("\n" + "="*80)
        print(f"[INFO] DRAFT UPDATE - Phase: {state.phase}")
        if self.verbose:
            print(f"[DEBUG] Current actor: {state.current_actor}, Local player: {state.local_player_cell_id}")
            print(f"[DEBUG] Enemy picks: {len(state.enemy_picks)}, Ally picks: {len(state.ally_picks)}")
            print(f"[DEBUG] Enemy bans: {len(state.enemy_bans)}, Ally bans: {len(state.ally_bans)}")
        print("="*80)
        
        # Do initial hover when first entering champion select
        if self.auto_hover and not self.has_done_initial_hover and state.phase:
            self._do_initial_hover()
            self.has_done_initial_hover = True
        
        # Reset last recommendation if enemy composition changed for fresh hover decisions
        if self._enemy_picks_changed(state):
            self.last_recommendation = None
        
        # Display current draft state
        self._display_draft_state(state)
        
        # Provide coaching recommendations
        self._provide_recommendations(state)
    
    def _display_draft_state(self, state: DraftState):
        """Display current draft state in terminal."""
        print(f"\n[ALLY] ALLY TEAM:")
        if state.ally_picks:
            for i, champ_id in enumerate(state.ally_picks, 1):
                display_name = self._get_display_name(champ_id)
                print(f"  {i}. {display_name}")
        else:
            print("  (No picks yet)")
        
        # Only show bans during ban phases or when bans are relevant
        if state.ally_bans and self._should_show_bans(state):
            display_bans = [self._get_display_name(champ_id) for champ_id in state.ally_bans]
            print(f"  Bans: {', '.join(display_bans)}")
        
        print(f"\n[ENEMY] ENEMY TEAM:")  
        if state.enemy_picks:
            for i, champ_id in enumerate(state.enemy_picks, 1):
                display_name = self._get_display_name(champ_id)
                print(f"  {i}. {display_name}")
        else:
            print("  (No picks yet)")
            
        # Only show bans during ban phases or when bans are relevant
        if state.enemy_bans and self._should_show_bans(state):
            display_bans = [self._get_display_name(champ_id) for champ_id in state.enemy_bans]
            print(f"  Bans: {', '.join(display_bans)}")
    
    def _provide_recommendations(self, state: DraftState):
        """Provide coaching recommendations based on current draft."""
        try:
            enemy_picks = state.enemy_picks
            ally_picks = state.ally_picks
            
            if not enemy_picks and not ally_picks:
                print(f"\n[COACH] COACH SAYS: Draft just started - prepare your champion pool!")
                # Show ban recommendations only if we're actually in a ban phase
                if self._is_ban_phase(state):
                    self._show_ban_recommendations_draft()
                return
            
            # Use existing coach logic
            if enemy_picks:
                print(f"\n[PICKS] COUNTERPICK RECOMMENDATIONS:")
                print("-" * 50)
                
                # Show adaptive ban recommendations only during actual ban phases
                if self._is_ban_phase(state) and len(enemy_picks) >= 1:
                    self._show_adaptive_ban_recommendations(state)
                
                # Get champion IDs from current pool only
                name_to_id = {name: champ_id for champ_id, name in self.champion_id_to_name.items()}
                pool_champion_ids = []
                for champ_name in self.current_pool:
                    if champ_name in name_to_id:
                        pool_champion_ids.append(name_to_id[champ_name])
                    else:
                        if self.verbose:
                            print(f"[DEBUG] Champion '{champ_name}' from current pool not found in database")
                
                scores = []
                
                # Debug: show current bans
                if self.verbose:
                    if state.ally_bans or state.enemy_bans:
                        ally_ban_names = [self._get_display_name(bid) for bid in state.ally_bans]
                        enemy_ban_names = [self._get_display_name(bid) for bid in state.enemy_bans]
                        print(f"[DEBUG] Ally bans: {ally_ban_names}")
                        print(f"[DEBUG] Enemy bans: {enemy_ban_names}")
                
                for champion_id in pool_champion_ids:
                    # Skip if already picked/banned
                    if champion_id in enemy_picks or champion_id in ally_picks:
                        continue
                    if champion_id in state.ally_bans or champion_id in state.enemy_bans:
                        if self.verbose:
                            banned_name = self._get_display_name(champion_id)
                            print(f"[DEBUG] Skipping banned champion: {banned_name}")
                        continue
                        
                    # Get matchups for this champion
                    matchups = self.assistant.db.get_champion_matchups(champion_id)
                    if matchups and sum(m[5] for m in matchups) >= 500:  # Threshold for valid data
                        # Calculate score against enemy team
                        score = self._calculate_score_against_team(matchups, enemy_picks)
                        scores.append((champion_id, score))
                
                scores.sort(key=lambda x: -x[1])
                
                # Show top 3 recommendations
                display_count = min(3, len(scores))
                top_recommendation = None
                
                for i in range(display_count):
                    champion_id, score = scores[i]
                    display_name = self._get_display_name(champion_id)
                    rank = "[1st]" if i == 0 else "[2nd]" if i == 1 else "[3rd]"
                    print(f"  {rank} {display_name} (Score: {score:.1f})")
                    
                    # Store top recommendation for auto-hover
                    if i == 0:
                        top_recommendation = display_name
                
                # Auto-hover top recommendation if enabled
                if (self.auto_hover and top_recommendation and 
                    top_recommendation != self.last_recommendation):
                    # Check if we should update hover (either it's our turn or enemy picked)
                    is_our_turn = self._is_player_turn(state)
                    enemy_changed = self._enemy_picks_changed(state)
                    
                    if is_our_turn or enemy_changed:
                        reason = "Your turn" if is_our_turn else "Enemy pick update"
                        self._auto_hover_champion(top_recommendation, reason)
                        self.last_recommendation = top_recommendation
                
                if not scores:
                    print("  [DATA] No data available for current matchups")
            
            # Phase-specific advice
            phase_advice = {
                "PLANNING": "[PLAN] Think about team composition and ban priorities",
                "BAN_PICK": "[BAN] Focus on banning enemy strengths",
                "PICK": "[PICK] Time to secure your champion!",
                "FINALIZATION": "[FINAL] Finalize runes and summoner spells"
            }
            
            if state.phase in phase_advice:
                print(f"\n[ADVICE] {phase_advice[state.phase]}")
                
        except Exception as e:
            print(f"[WARNING] Error providing recommendations: {e}")
    
    def _is_player_turn(self, state: DraftState) -> bool:
        """Check if it's the local player's turn to pick."""
        if not state.current_actor or not state.local_player_cell_id:
            return False
        return state.current_actor == state.local_player_cell_id
    
    def _enemy_picks_changed(self, state: DraftState) -> bool:
        """Check if enemy team composition has changed."""
        return state.enemy_picks != self.last_draft_state.enemy_picks
    
    def _is_ban_phase(self, state: DraftState) -> bool:
        """
        Check if we are currently in an active ban phase.
        
        This method checks multiple conditions:
        1. Phase name contains 'BAN'
        2. Current actor exists (someone is supposed to act)
        3. We haven't reached the maximum number of bans yet
        
        Returns:
            True if currently in an active ban phase, False otherwise
        """
        if not state.phase:
            return False
        
        # Check if phase name indicates banning
        phase_upper = state.phase.upper()
        if "BAN" not in phase_upper:
            return False
        
        # Additional check: make sure we're not in a pure pick phase
        if "PICK" in phase_upper and "BAN" not in phase_upper:
            return False
        
        # Check if someone is supposed to act (there's a current actor)
        if not state.current_actor:
            return False
        
        # Check if we haven't exceeded typical ban limits
        # In most draft modes, each team gets 5 bans (10 total)
        total_bans = len(state.ally_bans) + len(state.enemy_bans)
        if total_bans >= 10:  # Standard draft has 10 bans total
            if self.verbose:
                print(f"[DEBUG] Ban phase check: Max bans reached ({total_bans}/10)")
            return False
        
        if self.verbose:
            print(f"[DEBUG] Ban phase detected: Phase='{state.phase}', Actor={state.current_actor}, Bans={total_bans}/10")
        
        return True
    
    def _should_show_bans(self, state: DraftState) -> bool:
        """
        Determine if bans should be displayed based on the current draft phase.
        
        Returns:
            True if bans should be shown, False otherwise
        """
        if not state.phase:
            return False
        
        phase_upper = state.phase.upper()
        
        # Show bans during ban phases
        if "BAN" in phase_upper:
            return True
        
        # Hide bans during pure pick phases
        if "PICK" in phase_upper and "BAN" not in phase_upper:
            return False
        
        # Show bans during planning phase (before draft starts)
        if "PLANNING" in phase_upper:
            return True
        
        # Default: hide bans during active picking to reduce clutter
        return False
    
    def _auto_hover_champion(self, champion_name: str, reason: str = ""):
        """Automatically hover the recommended champion."""
        try:
            if self.lcu.hover_champion(champion_name):
                reason_text = f" ({reason})" if reason else ""
                print(f"  🎯 [AUTO-HOVER] Hovered {champion_name}{reason_text}")
            else:
                if self.verbose:
                    print(f"  ⚠️ [AUTO-HOVER] Failed to hover {champion_name}")
        except Exception as e:
            if self.verbose:
                print(f"  ❌ [AUTO-HOVER] Error hovering {champion_name}: {e}")
    
    def _do_initial_hover(self):
        """Do initial hover with the best champion from the pool when entering champion select."""
        try:
            print(f"\n[INITIAL] Entering champion select - showing your best champion from pool!")
            
            # Get best champion from current pool (first champion as fallback)
            if not self.current_pool:
                if self.verbose:
                    print("  ⚠️ [INITIAL-HOVER] No champions in pool")
                return
            
            # Use first champion from pool as initial recommendation
            # In the future, this could be smarter (e.g., based on meta or personal stats)
            initial_champion = self.current_pool[0]
            
            self._auto_hover_champion(initial_champion, "Initial hover")
            self.last_recommendation = initial_champion
            
        except Exception as e:
            if self.verbose:
                print(f"  ⚠️ [INITIAL-HOVER] Error doing initial hover: {e}")
    
    def _show_ban_recommendations_draft(self):
        """Show ban recommendations for current pool during draft."""
        try:
            print(f"\n[BANS] 🛡️ STRATEGIC BAN RECOMMENDATIONS")
            print("-" * 50)
            
            ban_recommendations = self.assistant.get_ban_recommendations(self.current_pool, num_bans=3)
            
            if ban_recommendations:
                print(f"Consider banning these threats to your pool:")
                for i, (enemy, threat_score, matchup_count) in enumerate(ban_recommendations, 1):
                    print(f"  {i}. {enemy:<12} | Threat: {threat_score:>5.2f} | Counters {matchup_count}/{len(self.current_pool)} of your champions")
                print(f"💡 These champions have good matchups against your pool")
            else:
                if self.verbose:
                    print(f"⚠️ No ban data available for your pool")
                    
        except Exception as e:
            if self.verbose:
                print(f"[WARNING] Error showing ban recommendations: {e}")
    
    def _show_adaptive_ban_recommendations(self, state: DraftState):
        """Show ban recommendations adapted to enemy picks."""
        try:
            if not state.enemy_picks:
                return
            
            print(f"\n[ADAPTIVE BANS] 🎯 TARGETED BAN RECOMMENDATIONS")
            print("-" * 50)
            
            # Get enemy champion names
            enemy_names = [self._get_display_name(champ_id) for champ_id in state.enemy_picks]
            print(f"Enemy team has: {', '.join(enemy_names)}")
            
            # Get adaptive ban recommendations based on enemy comp
            # This could be enhanced to consider synergies, but for now show general threats
            ban_recommendations = self.assistant.get_ban_recommendations(self.current_pool, num_bans=3)
            
            if ban_recommendations:
                print(f"Priority bans to deny enemy synergies:")
                for i, (enemy, threat_score, matchup_count) in enumerate(ban_recommendations[:3], 1):
                    print(f"  {i}. {enemy:<12} | Threat: {threat_score:>5.2f}")
                print(f"💡 Focus on champions that synergize with their picks")
            
        except Exception as e:
            if self.verbose:
                print(f"[WARNING] Error showing adaptive ban recommendations: {e}")
    
    def _select_champion_pool_interactive(self) -> List[str]:
        """Interactive pool selection with custom pools support."""
        try:
            from .pool_manager import PoolManager
            pool_manager = PoolManager()
            
            print("\n" + "="*50)
            print("SELECT CHAMPION POOL")
            print("="*50)
            
            # Show available pools
            pools = pool_manager.get_all_pools()
            pool_list = []
            
            print("\nAvailable pools:")
            idx = 1
            for name, pool in sorted(pools.items()):
                pool_list.append((name, pool))
                status = "🔧" if pool.created_by == "system" else "👤"
                print(f"  {idx}. {status} {name:<20} | {pool.role:<8} | {pool.size():>2} champs | {pool.description}")
                idx += 1
            
            # Add legacy options
            print(f"\n  {idx}. Use Assistant's extended pool selector (legacy)")
            
            try:
                choice = int(input(f"\nChoose pool (1-{idx}): ").strip())
                
                if 1 <= choice <= len(pool_list):
                    selected_name, selected_pool = pool_list[choice - 1]
                    safe_print(f"✅ Using pool: {selected_name} ({', '.join(selected_pool.champions)})")
                    return selected_pool.champions
                elif choice == idx:
                    # Fallback to assistant's method
                    return self.assistant.select_champion_pool()
                else:
                    print("[WARNING] Invalid choice, using default TOP pool")
                    return ROLE_POOLS["top"]
                    
            except (ValueError, IndexError):
                print("[WARNING] Invalid input, using default TOP pool")
                return ROLE_POOLS["top"]
                
        except Exception as e:
            print(f"[WARNING] Pool selection error: {e}")
            print("Falling back to legacy pool selection...")
            return self.assistant.select_champion_pool()
    
    def _calculate_final_scores(self, ally_picks: List[int], enemy_picks: List[int]):
        """Calculate individual scores for each champion at end of draft."""
        
        print("\n" + "="*80)
        safe_print("🎮 FINAL DRAFT ANALYSIS - Individual Champion Scores")
        print("="*80)
        
        if not ally_picks or not enemy_picks:
            print("[INFO] Incomplete draft - no final analysis available")
            return
            
        ally_names = [self._get_display_name(champ_id) for champ_id in ally_picks]
        enemy_names = [self._get_display_name(champ_id) for champ_id in enemy_picks]
        
        print(f"\n[TEAMS] FINAL COMPOSITION:")
        print(f"  Ally Team:  {' | '.join(ally_names)}")
        print(f"  Enemy Team: {' | '.join(enemy_names)}")
        
        safe_print(f"\n📊 TEAM PERFORMANCE ANALYSIS:")
        print("-" * 60)
        
        ally_scores = []
        enemy_scores = []
        
        # Calculate scores for ALLY team (without displaying yet)
        for i, champion_id in enumerate(ally_picks):
            champion_name = self._get_display_name(champion_id)
            
            try:
                # Get matchups for this champion
                matchups = self.assistant.db.get_champion_matchups(champion_id)
                
                if not matchups or sum(m[5] for m in matchups) < 500:
                    ally_scores.append((champion_name, None, 0))  # Mark insufficient data
                    continue
                
                # Calculate score against enemy team
                total_score = 0
                valid_matchups = 0
                
                for enemy_id in enemy_picks:
                    # Find specific matchup
                    for matchup in matchups:
                        if matchup[0] == enemy_id:  # enemy_id is first element
                            delta2 = matchup[3]  # delta2 is at index 3
                            total_score += delta2
                            valid_matchups += 1
                            break
                
                avg_score = total_score / valid_matchups if valid_matchups > 0 else 0
                ally_scores.append((champion_name, avg_score, total_score))
                
            except Exception as e:
                ally_scores.append((champion_name, None, 0))  # Mark error
        
        # Calculate scores for ENEMY team (without displaying yet)
        for i, champion_id in enumerate(enemy_picks):
            champion_name = self._get_display_name(champion_id)
            
            try:
                # Get matchups for this champion
                matchups = self.assistant.db.get_champion_matchups(champion_id)
                
                if not matchups or sum(m[5] for m in matchups) < 500:
                    enemy_scores.append((champion_name, None, 0))  # Mark insufficient data
                    continue
                
                # Calculate score against ally team
                total_score = 0
                valid_matchups = 0
                
                for ally_id in ally_picks:
                    # Find specific matchup
                    for matchup in matchups:
                        if matchup[0] == ally_id:  # ally_id is first element
                            delta2 = matchup[3]  # delta2 is at index 3
                            total_score += delta2
                            valid_matchups += 1
                            break
                
                avg_score = total_score / valid_matchups if valid_matchups > 0 else 0
                enemy_scores.append((champion_name, avg_score, total_score))
                
            except Exception as e:
                enemy_scores.append((champion_name, None, 0))  # Mark error
        
        # Sort both teams by average score (descending - best scores first)
        ally_scores.sort(key=lambda x: x[1] if x[1] is not None else -999, reverse=True)
        enemy_scores.sort(key=lambda x: x[1] if x[1] is not None else -999, reverse=True)
        
        # Display ALLY team performance (sorted)
        safe_print(f"\n🟢 YOUR TEAM:")
        for champion_name, avg_score, total_score in ally_scores:
            if avg_score is None:
                safe_print(f"  {champion_name:<15} | ❌ Insufficient data")
            else:
                # Overall assessment with symmetric thresholds
                if avg_score > 1.0:
                    safe_print(f"  {champion_name:<15} | ✅ +{avg_score:.1f} (Excellent)")
                elif avg_score >= 0.5:
                    safe_print(f"  {champion_name:<15} | 🟡 +{avg_score:.1f} (Good)")
                elif avg_score >= -0.5:
                    safe_print(f"  {champion_name:<15} | ➖ {avg_score:+.1f} (Neutral)")
                elif avg_score >= -1.0:
                    safe_print(f"  {champion_name:<15} | 🟠 {avg_score:.1f} (Bad)")
                else:
                    safe_print(f"  {champion_name:<15} | 🔴 {avg_score:.1f} (Very Bad)")
        
        # Display ENEMY team performance (sorted)
        safe_print(f"\n🔴 ENEMY TEAM:")
        for champion_name, avg_score, total_score in enemy_scores:
            if avg_score is None:
                safe_print(f"  {champion_name:<15} | ❌ Insufficient data")
            else:
                # Overall assessment (from enemy perspective)
                if avg_score > 1.0:
                    safe_print(f"  {champion_name:<15} | ✅ +{avg_score:.1f} (Excellent)")
                elif avg_score >= 0.5:
                    safe_print(f"  {champion_name:<15} | 🟡 +{avg_score:.1f} (Good)")
                elif avg_score >= -0.5:
                    safe_print(f"  {champion_name:<15} | ➖ {avg_score:+.1f} (Neutral)")
                elif avg_score >= -1.0:
                    safe_print(f"  {champion_name:<15} | 🟠 {avg_score:.1f} (Bad)")
                else:
                    safe_print(f"  {champion_name:<15} | 🔴 {avg_score:.1f} (Very Bad)")
        
        # Team summary comparison
        safe_print(f"\n📈 DRAFT COMPARISON:")
        print("-" * 40)
        
        # Calculate averages only for champions with valid scores
        ally_valid_scores = [score[1] for score in ally_scores if score[1] is not None]
        enemy_valid_scores = [score[1] for score in enemy_scores if score[1] is not None]
        
        if ally_valid_scores:
            ally_avg = sum(ally_valid_scores) / len(ally_valid_scores)
            safe_print(f"  🟢 Your Team Avg:  {ally_avg:+.1f}")
        else:
            ally_avg = 0
            safe_print(f"  🟢 Your Team Avg:  No valid data")
            
        if enemy_valid_scores:
            enemy_avg = sum(enemy_valid_scores) / len(enemy_valid_scores)
            safe_print(f"  🔴 Enemy Team Avg: {enemy_avg:+.1f}")
        else:
            enemy_avg = 0
            safe_print(f"  🔴 Enemy Team Avg: No valid data")
        
        # Draft advantage calculation
        draft_diff = ally_avg - enemy_avg
        safe_print(f"  📊 Draft Difference: {draft_diff:+.1f}")
        
        # Overall assessment based on difference
        if draft_diff > 1.0:
            safe_print(f"  Assessment: ✅ Major draft advantage")
        elif draft_diff >= 0.5:
            safe_print(f"  Assessment: 🟡 Good draft advantage") 
        elif draft_diff >= -0.5:
            safe_print(f"  Assessment: ➖ Even draft")
        elif draft_diff >= -1.0:
            safe_print(f"  Assessment: 🟠 Draft disadvantage")
        else:
            safe_print(f"  Assessment: 🔴 Major draft disadvantage")
        
        print("\n" + "="*80)

    def cleanup(self):
        """Clean up resources."""
        if self.lcu:
            self.lcu.disconnect()
        if self.assistant:
            self.assistant.close()
        print("[PICK] Cleanup complete")

def main():
    """Main entry point for draft monitoring."""
    monitor = DraftMonitor()
    monitor.start_monitoring()

if __name__ == "__main__":
    main()