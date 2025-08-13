import time
import json
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from lcu_client import LCUClient
from assistant import Assistant
from constants import SOLOQ_POOL, ROLE_POOLS

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
    
    def __init__(self, verbose: bool = False, auto_select_pool: bool = True):
        self.lcu = LCUClient(verbose=verbose)
        self.assistant = Assistant()
        self.last_draft_state = DraftState()
        self.champion_id_to_name: Dict[int, str] = {}  # Riot ID -> Display name
        self.is_monitoring = False
        self.verbose = verbose
        self.current_pool = SOLOQ_POOL  # Default pool
        self.auto_select_pool = auto_select_pool
        
    def start_monitoring(self):
        """Start monitoring champion select."""
        print("[BOT] League Draft Coach - Starting...")
        
        if not self.lcu.connect():
            return False
        
        # Load champion ID mappings
        self._load_champion_mappings()
        
        # Pool selection
        if not self.auto_select_pool:
            self.current_pool = self.assistant.select_champion_pool()
        else:
            # Auto-select top pool by default
            self.current_pool = ROLE_POOLS["top"]
            from assistant import safe_print
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
                        self._calculate_final_scores(ally_picks, enemy_picks)
                    
                    # Reset state after analysis
                    self.last_draft_state = DraftState()
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
        print("="*80)
        
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
        
        if state.ally_bans:
            display_bans = [self._get_display_name(champ_id) for champ_id in state.ally_bans]
            print(f"  Bans: {', '.join(display_bans)}")
        
        print(f"\n[ENEMY] ENEMY TEAM:")  
        if state.enemy_picks:
            for i, champ_id in enumerate(state.enemy_picks, 1):
                display_name = self._get_display_name(champ_id)
                print(f"  {i}. {display_name}")
        else:
            print("  (No picks yet)")
            
        if state.enemy_bans:
            display_bans = [self._get_display_name(champ_id) for champ_id in state.enemy_bans]
            print(f"  Bans: {', '.join(display_bans)}")
    
    def _provide_recommendations(self, state: DraftState):
        """Provide coaching recommendations based on current draft."""
        try:
            enemy_picks = state.enemy_picks
            ally_picks = state.ally_picks
            
            if not enemy_picks and not ally_picks:
                print(f"\n[COACH] COACH SAYS: Draft just started - prepare your champion pool!")
                return
            
            # Use existing coach logic
            if enemy_picks:
                print(f"\n[PICKS] COUNTERPICK RECOMMENDATIONS:")
                print("-" * 50)
                
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
                for i in range(display_count):
                    champion_id, score = scores[i]
                    display_name = self._get_display_name(champion_id)
                    rank = "[1st]" if i == 0 else "[2nd]" if i == 1 else "[3rd]"
                    print(f"  {rank} {display_name} (Score: {score:.1f})")
                
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
    
    def _calculate_final_scores(self, ally_picks: List[int], enemy_picks: List[int]):
        """Calculate individual scores for each champion at end of draft."""
        from assistant import safe_print
        
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