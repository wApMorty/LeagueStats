import time
import json
import subprocess
import os
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from .lcu_client import LCUClient
from .assistant import Assistant
from .utils.display import safe_print
from .utils.console import clear_console
from .constants import SOLOQ_POOL, ROLE_POOLS, normalize_champion_name_for_onetricks
from .config import config
from .config_constants import draft_config


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

    def __init__(
        self,
        verbose: bool = False,
        auto_select_pool: bool = True,
        auto_hover: bool = False,
        auto_accept_queue: bool = False,
        auto_ban_hover: bool = False,
        open_onetricks: bool = None,
    ):
        self.lcu = LCUClient(verbose=verbose)
        self.assistant = Assistant()
        self.last_draft_state = DraftState()
        self.champion_id_to_name: Dict[int, str] = {}  # Riot ID -> Display name
        self.is_monitoring = False
        self.verbose = verbose
        self.current_pool = SOLOQ_POOL  # Default pool
        self.pool_name = None  # Pool name for pre-calculated ban lookups
        self.auto_select_pool = auto_select_pool
        self.auto_hover = auto_hover
        self.auto_accept_queue = auto_accept_queue
        self.auto_ban_hover = auto_ban_hover
        self.open_onetricks = (
            open_onetricks
            if open_onetricks is not None
            else draft_config.OPEN_ONETRICKS_ON_DRAFT_END
        )
        self.last_recommendation = None  # Track last recommendation to avoid spam
        self.last_ban_recommendation = None  # Track last ban recommendation to avoid spam
        self.has_done_initial_hover = False  # Track if we've done the initial hover
        self.last_gameflow_phase = ""  # Track last gameflow phase
        self.has_analyzed_final_draft = False  # Track if we've already analyzed the final draft
        self.ready_check_accepted_time = 0  # Track when we accepted ready check
        self.player_champion = None  # Track the player's selected champion

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
            self.pool_name = "All Top Champions"  # System pool name
            self.current_pool = ROLE_POOLS["top"]
            safe_print(f"✅ Using pool: TOP ({', '.join(self.current_pool)})")

        # Performance: Warm cache for selected pool (eliminates SQL queries during draft)
        if self.current_pool:
            self.assistant.warm_cache(self.current_pool)

        # Clear console before starting monitoring loop
        clear_console()

        self.is_monitoring = True
        print("[WATCH] Monitoring for champion select...")
        print("   (Start a game to see draft recommendations)")
        if self.auto_accept_queue:
            print("   🔥 [AUTO-ACCEPT] Queue auto-accept is ENABLED")
        if self.auto_ban_hover:
            print("   🚫 [AUTO-BAN-HOVER] Ban hover is ENABLED")
        if self.open_onetricks:
            print("   🌐 [ONETRICKS] Open champion page on draft completion is ENABLED")
        print("   (Press Ctrl+C to stop)")

        try:
            while self.is_monitoring:
                self._monitor_loop()
                time.sleep(draft_config.POLL_INTERVAL)  # Check draft state periodically
        except KeyboardInterrupt:
            print("\n[STOP] Stopping draft monitor...")
        finally:
            self.cleanup()

    def _open_champion_page_on_onetricks(self):
        """Open the player's champion page on OneTriks.gg using Brave browser."""
        try:
            if not self.player_champion:
                if self.verbose:
                    print("[ONETRICKS] No player champion detected, skipping browser open")
                return

            # Normalize champion name for OneTricks.gg URL
            normalized_name = normalize_champion_name_for_onetricks(self.player_champion)
            onetricks_url = f"https://www.onetricks.gg/champions/builds/{normalized_name}"

            # Try to get Brave browser path
            try:
                brave_path = config.get_brave_path()
            except FileNotFoundError:
                if self.verbose:
                    print("[ONETRICKS] Brave browser not found, trying default browser")
                # Fallback to default browser
                import webbrowser

                webbrowser.open(onetricks_url)
                return

            # Open with Brave browser
            subprocess.Popen(
                [brave_path, onetricks_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

        except Exception as e:
            if self.verbose:
                print(f"[WARNING] Failed to open OneTriks.gg page: {e}")
            else:
                print(f"[WARNING] Failed to open champion page in browser")

    def stop_monitoring(self):
        """Stop monitoring."""
        self.is_monitoring = False

    def _monitor_loop(self):
        """Main monitoring loop."""
        try:
            # Check for ready check (queue found) and auto-accept if enabled
            if self.auto_accept_queue and self.lcu.is_in_ready_check():
                self._handle_ready_check()

            if not self.lcu.is_in_champion_select():
                # Show ready message when leaving champion select if we had a draft
                if self.last_draft_state.phase and (
                    self.last_draft_state.ally_picks or self.last_draft_state.enemy_picks
                ):

                    # Only show the message once when leaving champion select
                    if not hasattr(self, "_shown_ready_message"):
                        print("\n[INFO] Left champion select - Game starting!")

                        # Show ready message for next game
                        print("\n" + "=" * 60)
                        print("🎮 [READY] Waiting for next game...")
                        if self.auto_accept_queue:
                            print("   🔥 Auto-accept is enabled for next queue")
                        print("   (Queue up for another game!)")
                        print("=" * 60)

                        self._shown_ready_message = True

                # Check if we've completely left the game flow and should reset
                gameflow = self.lcu.get_gameflow_session()
                if gameflow:
                    current_phase = gameflow.get("phase", "")
                    # Reset when we're back in lobby or matchmaking
                    if current_phase in ["Lobby", "Matchmaking", "None", ""]:
                        if self.has_analyzed_final_draft:  # Only reset if we had analyzed a draft
                            if self.verbose:
                                print(
                                    f"[DEBUG] Gameflow phase: {current_phase} - Resetting for next game"
                                )
                            self._reset_for_next_game()

                return

            # Get current champion select data
            champ_select_data = self.lcu.get_champion_select_session()
            if not champ_select_data:
                return

            # Parse draft state
            current_state = self._parse_draft_state(champ_select_data)

            # Check for changes and provide recommendations (only if draft not complete)
            if self._has_draft_changed(current_state):
                # Only show draft updates if we haven't completed the analysis yet
                if not self.has_analyzed_final_draft:
                    self._handle_draft_change(current_state)
                self.last_draft_state = current_state

            # Check if draft is complete and analyze if needed
            if self._is_draft_complete(current_state) and not self.has_analyzed_final_draft:
                self._analyze_complete_draft(current_state)

        except Exception as e:
            if self.verbose:
                print(f"[WARNING] Monitor error: {e}")

    def _handle_ready_check(self):
        """Handle ready check (queue found) and auto-accept if enabled."""
        try:
            # Get current gameflow phase to avoid spam
            gameflow = self.lcu.get_gameflow_session()
            if not gameflow:
                return

            current_phase = gameflow.get("phase", "")
            current_time = time.time()

            # Check if we've entered ready check for the first time or after a failed attempt
            if current_phase == "ReadyCheck":
                # Reset ready check acceptance if we haven't accepted recently
                # This handles cases where ready check failed and we're in a new one
                cooldown = draft_config.READY_CHECK_COOLDOWN * 2.5  # 5 seconds default
                if self.last_gameflow_phase != "ReadyCheck" or (
                    self.ready_check_accepted_time > 0
                    and current_time - self.ready_check_accepted_time > cooldown
                ):

                    print("\n" + "=" * 60)
                    print("🎮 [QUEUE] GAME FOUND!")
                    print("=" * 60)

                    # Get ready check details if available
                    ready_check = self.lcu.get_ready_check_state()
                    if ready_check and self.verbose:
                        timer = ready_check.get("timer", 0)
                        print(f"[DEBUG] Ready check timer: {timer}s")

                    # Auto-accept the queue
                    if self.lcu.accept_ready_check():
                        print("✅ [AUTO-ACCEPT] Queue accepted automatically!")
                        self.ready_check_accepted_time = current_time
                    else:
                        print("❌ [AUTO-ACCEPT] Failed to accept queue")

                    print("Waiting for other players...")
                    print("=" * 60)

            # Handle transitions out of ready check
            elif self.last_gameflow_phase == "ReadyCheck" and current_phase != "ReadyCheck":
                if current_phase == "ChampSelect":
                    print("✅ [SUCCESS] All players accepted - Entering champion select!")
                elif current_phase in ["Lobby", "Matchmaking"]:
                    print("❌ [FAILED] Ready check failed - Someone didn't accept")
                    print("🔄 [RETRY] Returning to queue...")
                    # Reset ready check timer to allow new detection
                    self.ready_check_accepted_time = 0

            # Update last phase
            self.last_gameflow_phase = current_phase

        except Exception as e:
            if self.verbose:
                print(f"[WARNING] Error handling ready check: {e}")

    def _handle_auto_ban_hover(self, state: DraftState):
        """Handle auto-ban-hover when it's our turn to ban."""
        try:
            if self.verbose:
                print(
                    f"[DEBUG] Auto-ban-hover called: Phase='{state.phase}', Actor={state.current_actor}, Local={state.local_player_cell_id}"
                )

            # Only act if it's our turn to ban
            if not self._is_player_ban_turn(state):
                if self.verbose:
                    print(f"[DEBUG] Not player ban turn - skipping auto-ban-hover")
                return

            if self.verbose:
                print(
                    f"[DEBUG] It's our ban turn! Getting recommendations for pool size {len(self.current_pool)}"
                )

            # Try to get pre-calculated bans from database first (fast)
            ban_recommendations = None
            if hasattr(self, "pool_name") and self.pool_name:
                ban_recommendations = self.assistant.db.get_pool_ban_recommendations(
                    self.pool_name, limit=3
                )
                if ban_recommendations and self.verbose:
                    print(
                        f"[DEBUG] Using pre-calculated bans from database for pool '{self.pool_name}'"
                    )

            # Fallback to real-time calculation if no pre-calculated data
            if not ban_recommendations:
                if self.verbose:
                    print(f"[DEBUG] No pre-calculated bans found, calculating in real-time...")
                ban_recommendations = self.assistant.get_ban_recommendations(
                    self.current_pool, num_bans=3
                )

            if not ban_recommendations:
                print("[DEBUG] No ban recommendations available")
                return

            if self.verbose:
                print(f"[DEBUG] Got {len(ban_recommendations)} ban recommendations")

            # Get the top ban recommendation
            # Tuple format: (enemy, threat_score, best_delta2, best_champ, matchup_count)
            top_ban_data = ban_recommendations[0]
            top_ban = top_ban_data[0]
            threat_score = top_ban_data[1]
            matchup_count = top_ban_data[4] if len(top_ban_data) >= 5 else 0

            if self.verbose:
                print(f"[DEBUG] Top ban recommendation: {top_ban} (threat: {threat_score:.2f})")

            # Only hover if it's a different recommendation or first time
            if top_ban != self.last_ban_recommendation:
                # Check if this champion is already banned
                banned_champions = []
                for ban_id in state.ally_bans + state.enemy_bans:
                    banned_champions.append(self._get_display_name(ban_id))

                if self.verbose:
                    print(f"[DEBUG] Currently banned: {banned_champions}")
                    print(f"[DEBUG] Checking if '{top_ban}' is in banned list")

                # Case-insensitive comparison to handle potential name mismatches
                banned_champions_lower = [name.lower() for name in banned_champions]
                if top_ban.lower() not in banned_champions_lower:
                    print(f"[DEBUG] Attempting to hover {top_ban}...")
                    if self._auto_hover_champion(top_ban, "Ban recommendation"):
                        print(
                            f"  🚫 [AUTO-BAN-HOVER] Hovering {top_ban} (Threat: {threat_score:.2f})"
                        )
                        self.last_ban_recommendation = top_ban
                    else:
                        print(f"  ⚠️ [AUTO-BAN-HOVER] Failed to hover {top_ban}")
                else:
                    print(f"  ⚠️ [AUTO-BAN-HOVER] {top_ban} already banned, skipping")
            else:
                if self.verbose:
                    print(f"[DEBUG] Same recommendation as before ({top_ban}), skipping")

        except Exception as e:
            print(f"[WARNING] Error handling auto-ban-hover: {e}")
            import traceback

            traceback.print_exc()

    def _is_draft_complete(self, state: DraftState) -> bool:
        """Check if the draft is complete (all 10 champions locked)."""
        total_picks = len(state.ally_picks) + len(state.enemy_picks)
        return total_picks >= 10

    def _analyze_complete_draft(self, state: DraftState):
        """Analyze the complete draft immediately when all champions are locked."""
        try:
            ally_picks = state.ally_picks
            enemy_picks = state.enemy_picks

            if len(ally_picks) >= 5 and len(enemy_picks) >= 5:
                print("\n" + "=" * 80)
                print("🎯 [DRAFT COMPLETE] All champions locked - Final analysis!")
                print("=" * 80)

                self._calculate_final_scores(ally_picks, enemy_picks)

                # Mark analysis as done
                self.has_analyzed_final_draft = True

                # Open champion page on OneTriks.gg if enabled
                if self.open_onetricks:
                    self._open_champion_page_on_onetricks()

        except Exception as e:
            print(f"[ERROR] Failed to analyze complete draft: {e}")
            if self.verbose:
                import traceback

                traceback.print_exc()

    def _reset_for_next_game(self):
        """Reset state for the next game."""
        # Clear console when returning to queue for clean slate
        clear_console()

        self.last_draft_state = DraftState()
        self.has_done_initial_hover = False
        self.has_analyzed_final_draft = False
        self.last_recommendation = None
        self.last_ban_recommendation = None
        self.last_gameflow_phase = ""
        self.ready_check_accepted_time = 0
        self.player_champion = None

        # Reset ready message flag
        if hasattr(self, "_shown_ready_message"):
            delattr(self, "_shown_ready_message")

        if self.verbose:
            print("[DEBUG] State reset for next game")

    def _load_champion_mappings(self):
        """Load champion mappings from database (now using Riot IDs)."""
        try:
            # Use the centralized database method
            self.champion_id_to_name = self.assistant.db.get_all_champion_names()

            if self.verbose:
                print(
                    f"[DATA] Loaded {len(self.champion_id_to_name)} champion mappings from database"
                )

        except Exception as e:
            if self.verbose:
                print(f"[WARNING] Error loading champion mappings: {e}")

    def _get_display_name(self, champion_id: int) -> str:
        """Get display name for champion ID."""
        return self.champion_id_to_name.get(champion_id, f"Champion{champion_id}")

    def _calculate_score_against_team(
        self,
        matchups: List[tuple],
        enemy_team: List[int],
        champion_name: str,
        banned_champion_ids: List[int] = None,
    ) -> float:
        """Calculate score against enemy team using Assistant's method."""
        if not matchups or not enemy_team:
            return 0.0

        # Convert enemy IDs to champion names for the assistant method
        enemy_names = []
        for enemy_id in enemy_team:
            enemy_name = self._get_display_name(enemy_id)
            if enemy_name:
                enemy_names.append(enemy_name)

        if not enemy_names:
            return 0.0

        # Convert banned champion IDs to names
        banned_names = []
        if banned_champion_ids:
            for banned_id in banned_champion_ids:
                banned_name = self._get_display_name(banned_id)
                if banned_name:
                    banned_names.append(banned_name)

        # Use the assistant's scoring method which includes blind pick logic
        return self.assistant.score_against_team(
            matchups, enemy_names, champion_name, banned_names if banned_names else None
        )

    def _calculate_synergy_score(self, champion_name: str, ally_team: List[int]) -> float:
        """Calculate synergy score as sum of delta2 with allied champions.

        Args:
            champion_name: Name of the champion to evaluate
            ally_team: List of allied champion IDs already picked

        Returns:
            Sum of delta2 values for synergies with allies (0.0 if no allies)
        """
        if not ally_team:
            return 0.0

        synergy_score = 0.0

        for ally_id in ally_team:
            ally_name = self._get_display_name(ally_id)
            if ally_name:
                delta2 = self.assistant.db.get_synergy_delta2(champion_name, ally_name)
                if delta2 is not None:
                    synergy_score += delta2
                    if self.verbose:
                        print(f"[DEBUG] Synergy: {champion_name} + {ally_name} = {delta2:+.2f}")

        return synergy_score

    def _parse_draft_state(self, champ_select_data: Dict) -> DraftState:
        """Parse champion select data into DraftState."""
        state = DraftState()

        # Get basic info
        state.phase = champ_select_data.get("timer", {}).get("phase", "")
        state.local_player_cell_id = champ_select_data.get("localPlayerCellId")

        # Parse team composition
        my_team = champ_select_data.get("myTeam", [])
        their_team = champ_select_data.get("theirTeam", [])

        # Process ally team
        for player in my_team:
            champ_id = player.get("championId", 0)
            if champ_id > 0:  # 0 means no champion selected
                state.ally_picks.append(champ_id)  # Store Riot ID directly

        # Process enemy team
        for player in their_team:
            champ_id = player.get("championId", 0)
            if champ_id > 0:
                state.enemy_picks.append(champ_id)  # Store Riot ID directly

        # Parse bans - FIXED: Bans are in actions[] with type="ban", not in bans{}
        # The bans{} object is often empty or unreliable in LCU API
        # We must parse completed ban actions from the actions[] array instead
        actions = champ_select_data.get("actions", [])

        for action_set in actions:
            for action in action_set:
                if action.get("type") == "ban" and action.get("completed"):
                    champion_id = action.get("championId", 0)
                    if champion_id > 0:
                        actor_cell_id = action.get("actorCellId")

                        # Determine if this ban is from our team or enemy team
                        # If actorCellId matches any player in myTeam, it's an ally ban
                        is_ally_ban = False
                        for player in my_team:
                            if player.get("cellId") == actor_cell_id:
                                is_ally_ban = True
                                break

                        if is_ally_ban:
                            if champion_id not in state.ally_bans:
                                state.ally_bans.append(champion_id)
                        else:
                            if champion_id not in state.enemy_bans:
                                state.enemy_bans.append(champion_id)

        # Find current actor (who's supposed to pick/ban now) and track player's champion
        # Reuse actions[] already fetched above
        for action_set in actions:
            for action in action_set:
                # Track player's champion selection
                if (
                    action.get("actorCellId") == state.local_player_cell_id
                    and action.get("type") == "pick"
                    and action.get("championId", 0) > 0
                ):
                    self.player_champion = self._get_display_name(action.get("championId"))

                if not action.get("completed", False):
                    state.current_actor = action.get("actorCellId")
                    break
            if state.current_actor:
                break

        return state

    def _has_draft_changed(self, current_state: DraftState) -> bool:
        """Check if draft state has changed significantly."""
        return (
            current_state.ally_picks != self.last_draft_state.ally_picks
            or current_state.enemy_picks != self.last_draft_state.enemy_picks
            or current_state.ally_bans != self.last_draft_state.ally_bans
            or current_state.enemy_bans != self.last_draft_state.enemy_bans
            or current_state.phase != self.last_draft_state.phase
        )

    def _handle_draft_change(self, state: DraftState):
        """Handle draft state change and provide recommendations."""
        # Clear console on draft updates to prevent infinite scroll
        # BUT don't clear during ban phase to keep ban recommendations visible
        should_clear = True

        # Don't clear during active ban phase - keep ban recommendations visible
        if self._is_ban_phase(state):
            should_clear = False
            if self.verbose:
                print(
                    f"[DEBUG] Ban phase active - skipping console clear to preserve ban recommendations"
                )

        # Only clear on phase transitions, not during same phase
        if should_clear and self.last_draft_state.phase == state.phase:
            # Same phase - only clear if there's a significant change (new pick)
            picks_changed = len(state.ally_picks) != len(self.last_draft_state.ally_picks) or len(
                state.enemy_picks
            ) != len(self.last_draft_state.enemy_picks)
            if not picks_changed:
                should_clear = False

        if should_clear:
            clear_console()

        print("\n" + "=" * 80)
        print(f"[INFO] DRAFT UPDATE - Phase: {state.phase}")
        if self.verbose:
            print(
                f"[DEBUG] Current actor: {state.current_actor}, Local player: {state.local_player_cell_id}"
            )
            print(
                f"[DEBUG] Enemy picks: {len(state.enemy_picks)}, Ally picks: {len(state.ally_picks)}"
            )
            print(f"[DEBUG] Enemy bans: {len(state.enemy_bans)}, Ally bans: {len(state.ally_bans)}")
        print("=" * 80)

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

            if self.verbose:
                print(
                    f"[DEBUG] _provide_recommendations called: Phase='{state.phase}', Enemies={len(enemy_picks)}, Allies={len(ally_picks)}"
                )

            # Skip recommendations if draft hasn't started yet (bans already shown in initial hover)
            if not enemy_picks and not ally_picks:
                if self.verbose:
                    print(f"[DEBUG] Waiting for picks to start (bans already shown at start)")
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
                            print(
                                f"[DEBUG] Champion '{champ_name}' from current pool not found in database"
                            )

                scores = []

                # Collect all banned champion IDs for score calculation
                all_banned_ids = state.ally_bans + state.enemy_bans

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

                    # Get champion name and matchups (cached for performance)
                    champion_name = self._get_display_name(champion_id)
                    matchups = self.assistant.get_matchups_for_draft(champion_name)
                    if (
                        matchups and sum(m.games for m in matchups) >= 500
                    ):  # Threshold for valid data
                        # Calculate matchup score against enemy team
                        matchup_score = self._calculate_score_against_team(
                            matchups, enemy_picks, champion_name, all_banned_ids
                        )

                        # Calculate synergy score with allied champions
                        synergy_score = self._calculate_synergy_score(champion_name, ally_picks)

                        # Final score = matchup_score + synergy_score
                        final_score = matchup_score + synergy_score

                        if self.verbose:
                            print(
                                f"[DEBUG] {champion_name}: Matchup={matchup_score:.2f}, "
                                f"Synergy={synergy_score:+.2f}, Final={final_score:.2f}"
                            )

                        scores.append((champion_id, final_score))

                scores.sort(key=lambda x: -x[1])

                # Show top 3 recommendations
                display_count = min(3, len(scores))
                top_recommendation = None

                for i in range(display_count):
                    champion_id, final_score = scores[i]
                    display_name = self._get_display_name(champion_id)
                    rank = "[1st]" if i == 0 else "[2nd]" if i == 1 else "[3rd]"

                    # Recalculate matchup and synergy scores for display
                    matchups = self.assistant.get_matchups_for_draft(display_name)
                    matchup_score = self._calculate_score_against_team(
                        matchups, enemy_picks, display_name, all_banned_ids
                    )
                    synergy_score = self._calculate_synergy_score(display_name, ally_picks)

                    # Format score as win rate advantage with breakdown
                    score_text = (
                        f"+{final_score:.2f}%" if final_score > 0 else f"{final_score:.2f}%"
                    )
                    breakdown = f"(Matchup: {matchup_score:+.2f}%, Synergy: {synergy_score:+.2f}%)"

                    print(f"  {rank} {display_name} {score_text} {breakdown}")

                    # Store top recommendation for auto-hover
                    if i == 0:
                        top_recommendation = display_name

                # Auto-hover top recommendation if enabled
                if (
                    self.auto_hover
                    and top_recommendation
                    and top_recommendation != self.last_recommendation
                ):
                    # Check if we should update hover (either it's our turn or enemy picked)
                    is_our_turn = self._is_player_turn(state)
                    enemy_changed = self._enemy_picks_changed(state)

                    if is_our_turn or enemy_changed:
                        reason = "Your turn" if is_our_turn else "Enemy pick update"
                        self._auto_hover_champion(top_recommendation, reason)
                        self.last_recommendation = top_recommendation

                if not scores:
                    print("  [DATA] No data available for current matchups")

            # Handle auto-ban-hover for ban phases (independent of pick phase)
            if self._is_ban_phase(state) and self.auto_ban_hover:
                self._handle_auto_ban_hover(state)

            # Phase-specific advice (dynamic based on actual game state)
            advice = None
            if state.phase == "PLANNING":
                advice = "[PLAN] Think about team composition and ban priorities"
            elif state.phase == "BAN_PICK":
                # BAN_PICK phase includes both bans and picks - detect which we're in
                if self._is_ban_phase(state):
                    advice = "[BAN] Focus on banning enemy strengths"
                else:
                    advice = "[PICK] Time to secure your champion!"
            elif state.phase == "PICK":
                advice = "[PICK] Time to secure your champion!"
            elif state.phase == "FINALIZATION":
                advice = "[FINAL] Finalize runes and summoner spells"

            if advice:
                print(f"\n[ADVICE] {advice}")

        except Exception as e:
            print(f"[WARNING] Error providing recommendations: {e}")

    def _is_player_turn(self, state: DraftState) -> bool:
        """Check if it's the local player's turn to pick."""
        if not state.current_actor or not state.local_player_cell_id:
            return False
        return state.current_actor == state.local_player_cell_id

    def _is_player_ban_turn(self, state: DraftState) -> bool:
        """Check if it's the local player's turn to ban."""
        if not self._is_ban_phase(state):
            return False
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
        1. We have 0 picks (ban phase is before any picks)
        2. We haven't reached the maximum number of bans yet

        Returns:
            True if currently in an active ban phase, False otherwise
        """
        if not state.phase:
            return False

        # Key insight: Ban phase happens BEFORE any picks
        # If there are any picks, we're in pick phase (even if phase name is "BAN_PICK")
        total_picks = len(state.ally_picks) + len(state.enemy_picks)
        if total_picks > 0:
            if self.verbose:
                print(f"[DEBUG] Not ban phase: {total_picks} picks already made")
            return False

        # Check if we haven't exceeded typical ban limits
        # In most draft modes, each team gets 5 bans (10 total)
        total_bans = len(state.ally_bans) + len(state.enemy_bans)
        if total_bans >= 10:  # Standard draft has 10 bans total
            if self.verbose:
                print(f"[DEBUG] Ban phase check: Max bans reached ({total_bans}/10)")
            return False

        if self.verbose:
            print(
                f"[DEBUG] Ban phase detected: Phase='{state.phase}', Picks={total_picks}, Bans={total_bans}/10"
            )

        return True

    def _should_show_bans(self, state: DraftState) -> bool:
        """
        Determine if bans should be displayed based on the current draft phase.

        Ban phase is considered active until enemy bans are revealed.
        Once enemy bans appear, we know ban phase is complete.

        Returns:
            True if bans should be shown, False otherwise
        """
        if not state.phase:
            return False

        # Show bans during ban phase (until enemy bans are revealed)
        # Once enemy bans appear, ban phase is complete and we hide ban recommendations
        if not state.enemy_bans:
            # No enemy bans yet = still in ban phase
            return True

        # Enemy bans revealed = ban phase complete, hide bans to reduce clutter
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
            # Clear console at start of champion select
            clear_console()

            print(f"\n[INITIAL] 🎮 Champion select started - Preparing your strategy!")
            print("=" * 80)

            # Get best champion from current pool (first champion as fallback)
            if not self.current_pool:
                if self.verbose:
                    print("  ⚠️ [INITIAL-HOVER] No champions in pool")
                return

            # Calculate best champion from pool using smart analysis
            initial_champion = self._get_best_champion_from_pool()

            # Show the recommended blind pick
            print(f"\n[PICK] 🎯 BEST BLIND PICK FROM YOUR POOL:")
            print(f"  ✅ {initial_champion}")
            print(f"  💡 If you're first pick, this is your safest choice!")

            # Auto-hover the champion
            self._auto_hover_champion(initial_champion, "Best blind pick")
            self.last_recommendation = initial_champion

            # Show ban recommendations immediately
            self._show_ban_recommendations_draft()

            print("\n" + "=" * 80)
            print("[INFO] Waiting for draft to begin...")
            print("=" * 80)

        except Exception as e:
            if self.verbose:
                print(f"  ⚠️ [INITIAL-HOVER] Error doing initial hover: {e}")

    def _get_best_champion_from_pool(self) -> str:
        """Get the best champion from current pool using tier list analysis."""
        try:
            # Convert current_pool (names) to champion IDs for scoring
            champion_ids = []
            for champ_name in self.current_pool:
                # Find champion ID by name
                for champ_id, name in self.champion_id_to_name.items():
                    if name.lower() == champ_name.lower():
                        champion_ids.append(champ_id)
                        break

            if not champion_ids:
                # Fallback to first champion if no IDs found
                return self.current_pool[0]

            # Calculate scores for pool champions (blind pick scenario)
            scores = []
            for champion_id in champion_ids:
                champion_name = self._get_display_name(champion_id)
                matchups = self.assistant.get_matchups_for_draft(champion_name)
                if matchups and sum(m.games for m in matchups) >= 500:  # Threshold for valid data
                    # Use blind pick scoring (empty enemy team)
                    score = self.assistant.score_against_team(matchups, [], champion_name)
                    scores.append((champion_name, score))

            if scores:
                # Sort by score and return best champion
                scores.sort(key=lambda x: x[1], reverse=True)
                best_champion = scores[0][0]
                if self.verbose:
                    print(
                        f"  ✅ [INITIAL-HOVER] Best from pool: {best_champion} ({scores[0][1]:+.2f}% advantage)"
                    )
                return best_champion
            else:
                # Fallback to first champion
                return self.current_pool[0]

        except Exception as e:
            if self.verbose:
                print(f"  ⚠️ [INITIAL-HOVER] Error getting best champion: {e}")
            return self.current_pool[0]  # Fallback

    def _show_ban_recommendations_draft(self):
        """Show ban recommendations for current pool during draft."""
        try:
            print(f"\n[BANS] 🛡️ STRATEGIC BAN RECOMMENDATIONS")
            print("-" * 50)

            # Try to get pre-calculated bans from database first (fast)
            ban_recommendations = None
            if hasattr(self, "pool_name") and self.pool_name:
                ban_recommendations = self.assistant.db.get_pool_ban_recommendations(
                    self.pool_name, limit=3
                )
                if ban_recommendations and self.verbose:
                    print(
                        f"[DEBUG] Using pre-calculated bans from database for pool '{self.pool_name}'"
                    )

            # Fallback to real-time calculation if no pre-calculated data
            if not ban_recommendations:
                if self.verbose:
                    print(f"[DEBUG] No pre-calculated bans found, calculating in real-time...")
                ban_recommendations = self.assistant.get_ban_recommendations(
                    self.current_pool, num_bans=3
                )

            if ban_recommendations:
                print(f"Consider banning these threats to your pool:")
                # Tuple format: (enemy, threat_score, best_delta2, best_champ, matchup_count)
                for i, (enemy, threat_score, _best_delta2, _best_champ, matchup_count) in enumerate(
                    ban_recommendations, 1
                ):
                    print(
                        f"  {i}. {enemy:<12} | Threat: {threat_score:>5.2f} | Counters {matchup_count}/{len(self.current_pool)} of your champions"
                    )
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

            # Try to get pre-calculated bans from database first (fast)
            ban_recommendations = None
            if hasattr(self, "pool_name") and self.pool_name:
                ban_recommendations = self.assistant.db.get_pool_ban_recommendations(
                    self.pool_name, limit=3
                )

            # Fallback to real-time calculation if no pre-calculated data
            if not ban_recommendations:
                ban_recommendations = self.assistant.get_ban_recommendations(
                    self.current_pool, num_bans=3
                )

            if ban_recommendations:
                print(f"Priority bans to deny enemy synergies:")
                for i, (enemy, threat_score, *_) in enumerate(ban_recommendations[:3], 1):
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

            print("\n" + "=" * 50)
            print("SELECT CHAMPION POOL")
            print("=" * 50)

            # Show available pools
            pools = pool_manager.get_all_pools()
            pool_list = []

            print("\nAvailable pools:")
            idx = 1
            for name, pool in sorted(pools.items()):
                pool_list.append((name, pool))
                status = "🔧" if pool.created_by == "system" else "👤"
                print(
                    f"  {idx}. {status} {name:<20} | {pool.role:<8} | {pool.size():>2} champs | {pool.description}"
                )
                idx += 1

            # Add legacy options
            print(f"\n  {idx}. Use Assistant's extended pool selector (legacy)")

            try:
                choice = int(input(f"\nChoose pool (1-{idx}): ").strip())

                if 1 <= choice <= len(pool_list):
                    selected_name, selected_pool = pool_list[choice - 1]
                    safe_print(
                        f"✅ Using pool: {selected_name} ({', '.join(selected_pool.champions)})"
                    )
                    # Store pool name for pre-calculated ban lookups
                    self.pool_name = selected_name
                    return selected_pool.champions
                elif choice == idx:
                    # Fallback to assistant's method (no pool_name)
                    self.pool_name = None
                    return self.assistant.select_champion_pool()
                else:
                    print("[WARNING] Invalid choice, using default TOP pool")
                    self.pool_name = "All Top Champions"  # System pool name
                    return ROLE_POOLS["top"]

            except (ValueError, IndexError):
                print("[WARNING] Invalid input, using default TOP pool")
                self.pool_name = "All Top Champions"
                return ROLE_POOLS["top"]

        except Exception as e:
            print(f"[WARNING] Pool selection error: {e}")
            print("Falling back to legacy pool selection...")
            self.pool_name = None
            return self.assistant.select_champion_pool()

    def _calculate_final_scores(self, ally_picks: List[int], enemy_picks: List[int]):
        """Calculate individual scores for each champion at end of draft."""
        # Clear console before final analysis for clean display
        clear_console()

        print("\n" + "=" * 80)
        safe_print("🎮 FINAL DRAFT ANALYSIS - Individual Champion Scores")
        print("=" * 80)

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
                # Get champion matchups (cached for performance) - uses 6-column format
                champion_matchups = self.assistant.get_matchups_for_draft(champion_name)

                if (
                    not champion_matchups or sum(m.games for m in champion_matchups) < 500
                ):  # m.games = games in 6-column format
                    if self.verbose:
                        total_games = (
                            sum(m.games for m in champion_matchups) if champion_matchups else 0
                        )
                        print(
                            f"[DEBUG] {champion_name}: Insufficient data (games={total_games}, need >=500)"
                        )
                    ally_scores.append(
                        (champion_name, None, 0, 0.0)
                    )  # (name, matchup_score, synergy_score, total)
                    continue

                # Use the new normalized scoring system
                enemy_names = [self._get_display_name(enemy_id) for enemy_id in enemy_picks]

                # Calculate matchup score against enemies
                matchup_score = self.assistant.score_against_team(
                    champion_matchups, enemy_names, champion_name
                )

                # Calculate synergy score with other allies (excluding self)
                other_allies = [aid for aid in ally_picks if aid != champion_id]
                synergy_score = self._calculate_synergy_score(champion_name, other_allies)

                # Total score = matchup + synergy
                total_score = matchup_score + synergy_score

                ally_scores.append((champion_name, matchup_score, synergy_score, total_score))

            except Exception as e:
                ally_scores.append((champion_name, None, 0.0, 0.0))  # Mark error

        # Calculate scores for ENEMY team (without displaying yet)
        for i, champion_id in enumerate(enemy_picks):
            champion_name = self._get_display_name(champion_id)

            try:
                # Get champion matchups (cached for performance) - uses 6-column format
                champion_matchups = self.assistant.get_matchups_for_draft(champion_name)

                if (
                    not champion_matchups or sum(m.games for m in champion_matchups) < 500
                ):  # m.games = games in 6-column format
                    if self.verbose:
                        total_games = (
                            sum(m.games for m in champion_matchups) if champion_matchups else 0
                        )
                        print(
                            f"[DEBUG] {champion_name}: Insufficient data (games={total_games}, need >=500)"
                        )
                    enemy_scores.append((champion_name, None, 0.0, 0.0))  # Mark insufficient data
                    continue

                # Use the new normalized scoring system
                ally_names = [self._get_display_name(ally_id) for ally_id in ally_picks]

                # Calculate matchup score against our team
                matchup_score = self.assistant.score_against_team(
                    champion_matchups, ally_names, champion_name
                )

                # Calculate synergy score with other enemies (excluding self)
                other_enemies = [eid for eid in enemy_picks if eid != champion_id]
                synergy_score = self._calculate_synergy_score(champion_name, other_enemies)

                # Total score = matchup + synergy
                total_score = matchup_score + synergy_score

                enemy_scores.append((champion_name, matchup_score, synergy_score, total_score))

            except Exception as e:
                enemy_scores.append((champion_name, None, 0.0, 0.0))  # Mark error

        # Sort both teams by total score (descending - best scores first)
        ally_scores.sort(
            key=lambda x: x[3] if x[1] is not None else -999, reverse=True
        )  # Sort by total_score
        enemy_scores.sort(key=lambda x: x[3] if x[1] is not None else -999, reverse=True)

        # Helper function to get emoji for score
        def get_emoji(score):
            if score >= 2.0:
                return "✅"
            elif score >= 1.0:
                return "🟡"
            elif score >= -1.0:
                return "➖"
            elif score >= -2.0:
                return "🟠"
            else:
                return "🔴"

        # Display ALLY team performance (sorted)
        safe_print(f"\n🟢 YOUR TEAM:")
        safe_print(f"  {'Champion':<15} | Matchup | Synergy | Total")
        safe_print(f"  {'-'*15}-+---------+---------+-------")
        for champion_name, matchup_score, synergy_score, total_score in ally_scores:
            if matchup_score is None:
                safe_print(f"  {champion_name:<15} | ❌ Insufficient data")
            else:
                matchup_emoji = get_emoji(matchup_score)
                synergy_emoji = get_emoji(synergy_score)
                total_emoji = get_emoji(total_score)
                safe_print(
                    f"  {champion_name:<15} | {matchup_emoji} {matchup_score:+5.1f} | "
                    f"🤝 {synergy_score:+5.1f} | {total_emoji} {total_score:+5.1f}"
                )

        # Display ENEMY team performance (sorted)
        safe_print(f"\n🔴 ENEMY TEAM:")
        safe_print(f"  {'Champion':<15} | Matchup | Synergy | Total")
        safe_print(f"  {'-'*15}-+---------+---------+-------")
        for champion_name, matchup_score, synergy_score, total_score in enemy_scores:
            if matchup_score is None:
                safe_print(f"  {champion_name:<15} | ❌ Insufficient data")
            else:
                matchup_emoji = get_emoji(matchup_score)
                synergy_emoji = get_emoji(synergy_score)
                total_emoji = get_emoji(total_score)
                safe_print(
                    f"  {champion_name:<15} | {matchup_emoji} {matchup_score:+5.1f} | "
                    f"🤝 {synergy_score:+5.1f} | {total_emoji} {total_score:+5.1f}"
                )

        # Team summary comparison
        safe_print(f"\n📈 DRAFT COMPARISON:")
        print("-" * 40)

        # Calculate team winrates using total scores (matchup + synergy)
        ally_valid_scores = [
            score[3] for score in ally_scores if score[1] is not None
        ]  # index 3 = total_score
        enemy_valid_scores = [score[3] for score in enemy_scores if score[1] is not None]

        if ally_valid_scores:
            # Convert total advantages to individual winrates
            ally_winrates = [50.0 + advantage for advantage in ally_valid_scores]
            # Use geometric mean for team strength calculation
            ally_team_stats = self.assistant._calculate_team_winrate(ally_winrates)
            ally_team_winrate = ally_team_stats["team_winrate"]
            ally_total = sum(ally_valid_scores)  # For display purposes
            safe_print(
                f"  🟢 Your Team: {ally_total:+.2f}% total advantage → {ally_team_winrate:.2f}% team winrate"
            )
        else:
            ally_team_winrate = 50.0
            ally_total = 0
            safe_print(f"  🟢 Your Team: No valid data")

        if enemy_valid_scores:
            # Convert advantages to individual winrates
            enemy_winrates = [50.0 + advantage for advantage in enemy_valid_scores]
            # Use geometric mean for team strength calculation
            enemy_team_stats = self.assistant._calculate_team_winrate(enemy_winrates)
            enemy_team_winrate = enemy_team_stats["team_winrate"]
            enemy_total = sum(enemy_valid_scores)  # For display purposes
            safe_print(
                f"  🔴 Enemy Team: {enemy_total:+.2f}% total advantage → {enemy_team_winrate:.2f}% team winrate"
            )
        else:
            enemy_team_winrate = 50.0
            enemy_total = 0
            safe_print(f"  🔴 Enemy Team: No valid data")

        # Normalize team winrates to ensure they sum to 100%
        if ally_team_winrate != 50.0 or enemy_team_winrate != 50.0:
            total_winrate = ally_team_winrate + enemy_team_winrate
            our_expected = (ally_team_winrate / total_winrate) * 100.0
            their_expected = (enemy_team_winrate / total_winrate) * 100.0

            safe_print(
                f"\n  🎯 Expected Matchup (normalized): {our_expected:.2f}% vs {their_expected:.2f}%"
            )

            # Overall assessment based on normalized winrates
            draft_diff = our_expected - their_expected
        else:
            # No valid data - neutral matchup
            our_expected = 50.0
            their_expected = 50.0
            draft_diff = 0.0
        if draft_diff >= 5.0:
            safe_print(f"  Assessment: ✅ Major draft advantage ({draft_diff:+.2f}% total edge)")
        elif draft_diff >= 2.5:
            safe_print(f"  Assessment: 🟡 Good draft advantage ({draft_diff:+.2f}% total edge)")
        elif draft_diff >= -2.5:
            safe_print(f"  Assessment: ➖ Even draft ({draft_diff:+.2f}% difference)")
        elif draft_diff >= -5.0:
            safe_print(f"  Assessment: 🟠 Draft disadvantage ({draft_diff:.2f}% behind)")
        else:
            safe_print(f"  Assessment: 🔴 Major draft disadvantage ({draft_diff:.2f}% behind)")

        print("\n" + "=" * 80)

    def cleanup(self):
        """Clean up resources."""
        if self.lcu:
            self.lcu.disconnect()
        if self.assistant:
            # Clear cache to free memory
            self.assistant.clear_cache()
            self.assistant.close()
        print("[PICK] Cleanup complete")


def main():
    """Main entry point for draft monitoring."""
    monitor = DraftMonitor()
    monitor.start_monitoring()


if __name__ == "__main__":
    main()
