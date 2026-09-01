"""Monitor loop orchestration: ready-check, draft-change, completion, reset.

Extracted from src/draft_monitor.py (SPEC-07 E10, lot 11, dernier lot) :
déplacement verbatim, aucun changement de comportement.

Back-reference to the monitor: this is the orchestrator, it touches
virtually every piece of monitor state (``_shown_ready_message`` created/
destroyed dynamically via hasattr/delattr, has_analyzed_final_draft,
has_done_initial_hover, last_gameflow_phase, ready_check_accepted_time,
player_champion, forced_roles, _last_prediction_id) and every other
component through the monitor's own facades — never through sibling
methods on this class — because tests/test_draft_monitor_display.py and
tests/test_draft_monitor_lifecycle.py patch several of those facades
directly on the monitor instance and expect this code to observe the
replacement (e.g. ``patch.object(monitor, "_handle_draft_change")`` then
``monitor._monitor_loop()``).
"""

import time

from ..config_constants import draft_config
from ..utils.console import clear_console
from .state import DraftState


class MonitorLifecycle:
    """Drive one poll-loop tick and the draft-completion/reset transitions."""

    def __init__(self, monitor) -> None:
        self.m = monitor

    def monitor_loop(self) -> None:
        """Main monitoring loop."""
        try:
            # Check for ready check (queue found) and auto-accept if enabled
            if self.m.auto_accept_queue and self.m.lcu.is_in_ready_check():
                self.m._handle_ready_check()

            if not self.m.lcu.is_in_champion_select():
                # Show ready message when leaving champion select if we had a draft
                if self.m.last_draft_state.phase and (
                    self.m.last_draft_state.ally_picks or self.m.last_draft_state.enemy_picks
                ):
                    # Only show the message once when leaving champion select
                    if not hasattr(self.m, "_shown_ready_message"):
                        print("\n[INFO] Champion select quitté - La partie démarre !")

                        # Show ready message for next game
                        print("\n" + "=" * 60)
                        print("[READY] En attente de la prochaine partie...")
                        if self.m.auto_accept_queue:
                            print("   Auto-accept activé pour la prochaine queue")
                        print("   (Relancez une recherche de partie !)")
                        print("=" * 60)

                        self.m._shown_ready_message = True

                # Check if we've completely left the game flow and should reset
                gameflow = self.m.lcu.get_gameflow_session()
                if gameflow:
                    current_phase = gameflow.get("phase", "")
                    # Reset when we're back in lobby or matchmaking
                    if current_phase in ["Lobby", "Matchmaking", "None", ""]:
                        if self.m.has_analyzed_final_draft:  # Only reset if we had analyzed a draft
                            if self.m.verbose:
                                print(
                                    f"[DEBUG] Gameflow phase: {current_phase} - Resetting for next game"
                                )
                            self.m._reset_for_next_game()

                return

            # Get current champion select data
            champ_select_data = self.m.lcu.get_champion_select_session()
            if not champ_select_data:
                return

            # Parse draft state
            current_state = self.m._parse_draft_state(champ_select_data)

            # SPEC-04 B5: apply any queued "r <champion> <lane>" corrections —
            # forces a redisplay even when the draft itself hasn't changed.
            commands_applied = self.m._apply_pending_commands(current_state)

            # Check for changes and provide recommendations (only if draft not complete)
            if self.m._has_draft_changed(current_state) or commands_applied:
                # Only show draft updates if we haven't completed the analysis yet
                if not self.m.has_analyzed_final_draft:
                    self.m._handle_draft_change(current_state)
                self.m.last_draft_state = current_state

            # Check if draft is complete and analyze if needed
            if self.m._is_draft_complete(current_state) and not self.m.has_analyzed_final_draft:
                self.m._analyze_complete_draft(current_state)

        except Exception as e:
            if self.m.verbose:
                print(f"[WARNING] Monitor error: {e}")

    def handle_ready_check(self) -> None:
        """Handle ready check (queue found) and auto-accept if enabled."""
        try:
            # Get current gameflow phase to avoid spam
            gameflow = self.m.lcu.get_gameflow_session()
            if not gameflow:
                return

            current_phase = gameflow.get("phase", "")
            current_time = time.time()

            # Check if we've entered ready check for the first time or after a failed attempt
            if current_phase == "ReadyCheck":
                # Reset ready check acceptance if we haven't accepted recently
                # This handles cases where ready check failed and we're in a new one
                cooldown = draft_config.READY_CHECK_COOLDOWN * 2.5  # 5 seconds default
                if self.m.last_gameflow_phase != "ReadyCheck" or (
                    self.m.ready_check_accepted_time > 0
                    and current_time - self.m.ready_check_accepted_time > cooldown
                ):
                    print("\n" + "=" * 60)
                    print("[QUEUE] PARTIE TROUVÉE !")
                    print("=" * 60)

                    # Get ready check details if available
                    ready_check = self.m.lcu.get_ready_check_state()
                    if ready_check and self.m.verbose:
                        timer = ready_check.get("timer", 0)
                        print(f"[DEBUG] Ready check timer: {timer}s")

                    # Auto-accept the queue
                    if self.m.lcu.accept_ready_check():
                        print("[OK] [AUTO-ACCEPT] Queue acceptée automatiquement !")
                        self.m.ready_check_accepted_time = current_time
                    else:
                        print("[ALERTE] [AUTO-ACCEPT] Échec de l'acceptation de la queue")

                    print("En attente des autres joueurs...")
                    print("=" * 60)

            # Handle transitions out of ready check
            elif self.m.last_gameflow_phase == "ReadyCheck" and current_phase != "ReadyCheck":
                if current_phase == "ChampSelect":
                    print(
                        "[OK] [SUCCESS] Tous les joueurs ont accepté - Entrée en champion select !"
                    )
                elif current_phase in ["Lobby", "Matchmaking"]:
                    print("[ALERTE] [FAILED] Échec du ready check - Un joueur n'a pas accepté")
                    print("[RETRY] Retour en file d'attente...")
                    # Reset ready check timer to allow new detection
                    self.m.ready_check_accepted_time = 0

            # Update last phase
            self.m.last_gameflow_phase = current_phase

        except Exception as e:
            if self.m.verbose:
                print(f"[WARNING] Error handling ready check: {e}")

    def analyze_complete_draft(self, state: DraftState) -> None:
        """Analyze the complete draft immediately when all champions are locked."""
        try:
            ally_picks = state.ally_picks
            enemy_picks = state.enemy_picks

            if len(ally_picks) >= 5 and len(enemy_picks) >= 5:
                print("\n" + "=" * 80)
                print("[DRAFT TERMINÉ] Tous les champions verrouillés - Analyse finale !")
                print("=" * 80)

                self.m._calculate_final_scores(
                    ally_picks, enemy_picks, ally_lanes=state.inferred_roles
                )

                # Mark analysis as done
                self.m.has_analyzed_final_draft = True

                # Open champion page on OneTriks.gg if enabled
                if self.m.open_onetricks:
                    self.m._open_champion_page_on_onetricks()

        except Exception as e:
            print(f"[ERREUR] Échec de l'analyse du draft complet: {e}")
            if self.m.verbose:
                import traceback

                traceback.print_exc()

    def reset_for_next_game(self) -> None:
        """Reset state for the next game."""
        # Clear console when returning to queue for clean slate
        clear_console()

        self.m.last_draft_state = DraftState()
        self.m.has_done_initial_hover = False
        self.m.has_analyzed_final_draft = False
        self.m.last_recommendation = None
        self.m.last_ban_recommendation = None
        self.m.last_gameflow_phase = ""
        self.m.ready_check_accepted_time = 0
        self.m.player_champion = None
        self.m.forced_roles = {}  # SPEC-04 B5: corrections don't carry to the next game
        self.m._last_prediction_id = None  # SPEC-05 B7: predictions don't carry to the next game

        # Reset ready message flag
        if hasattr(self.m, "_shown_ready_message"):
            delattr(self.m, "_shown_ready_message")

        if self.m.verbose:
            print("[DEBUG] State reset for next game")

    def handle_draft_change(self, state: DraftState) -> None:
        """Handle draft state change and provide recommendations."""
        # Clear console on draft updates to prevent infinite scroll
        # BUT don't clear during ban phase to keep ban recommendations visible
        should_clear = True

        # Don't clear during active ban phase - keep ban recommendations visible
        if self.m._is_ban_phase(state):
            should_clear = False
            if self.m.verbose:
                print(
                    f"[DEBUG] Ban phase active - skipping console clear to preserve ban recommendations"
                )

        # Only clear on phase transitions, not during same phase
        if should_clear and self.m.last_draft_state.phase == state.phase:
            # Same phase - only clear if there's a significant change (new pick)
            picks_changed = len(state.ally_picks) != len(self.m.last_draft_state.ally_picks) or len(
                state.enemy_picks
            ) != len(self.m.last_draft_state.enemy_picks)
            if not picks_changed:
                should_clear = False

        if should_clear:
            clear_console()

        print("\n" + "=" * 80)
        print(f"[INFO] MISE À JOUR DU DRAFT - Phase : {state.phase}")
        if self.m.verbose:
            print(
                f"[DEBUG] Current actor: {state.current_actor}, Local player: {state.local_player_cell_id}"
            )
            print(
                f"[DEBUG] Enemy picks: {len(state.enemy_picks)}, Ally picks: {len(state.ally_picks)}"
            )
            print(f"[DEBUG] Enemy bans: {len(state.enemy_bans)}, Ally bans: {len(state.ally_bans)}")
        print("=" * 80)

        # Do initial hover when first entering champion select
        if self.m.auto_hover and not self.m.has_done_initial_hover and state.phase:
            self.m._do_initial_hover()
            self.m.has_done_initial_hover = True

        # Reset last recommendation if enemy composition changed for fresh hover decisions
        if self.m._enemy_picks_changed(state):
            self.m.last_recommendation = None

        # Display current draft state
        self.m._display_draft_state(state)

        # Provide coaching recommendations
        self.m._provide_recommendations(state)
