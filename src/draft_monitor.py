import time
import json
import subprocess
import os
import logging
import queue
import tempfile
import threading
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from .lcu_client import LCUClient
from .assistant import Assistant
from .utils.display import safe_print
from .utils.console import clear_console
from .constants import TOP_SOLOQ_POOL, CHAMPIONS_BY_ROLE, normalize_champion_name_for_onetricks
from .config import config
from .config_constants import analysis_config, draft_config, role_inference_config, scraping_config
from .role_inference import infer_team_roles

# Dedicated logger for memory diagnostics. Writes to logs/draft_monitor_memory.log
# so the RSS trace survives the frequent console clears during a draft session.
_mem_logger = logging.getLogger("leaguestats.draft_monitor.memory")


def _get_memory_logger() -> logging.Logger:
    """Lazily attach a file handler for the memory diagnostics logger."""
    if not _mem_logger.handlers:
        try:
            log_dir = Path(__file__).resolve().parent.parent / "logs"
            log_dir.mkdir(exist_ok=True)
            handler = logging.FileHandler(log_dir / "draft_monitor_memory.log", encoding="utf-8")
            handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s"))
            _mem_logger.addHandler(handler)
            _mem_logger.setLevel(logging.INFO)
            _mem_logger.propagate = False
        except Exception:
            # Diagnostics must never break the monitor; degrade silently.
            _mem_logger.addHandler(logging.NullHandler())
    return _mem_logger


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
    # SPEC-04 B3: lane info, filled from the LCU (ally_positions) and later
    # inferred by role_inference.py (B4) for all 10 players.
    ally_positions: Dict[int, str] = field(default_factory=dict)  # cellId -> lane
    inferred_roles: Dict[int, str] = field(default_factory=dict)  # championId -> lane
    role_confidence: Dict[int, float] = field(default_factory=dict)  # championId -> [0,1]
    # SPEC-04 B5: championId -> "lcu" | "inferred" | "user" (manual correction).
    role_source: Dict[int, str] = field(default_factory=dict)

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
        synergy_weight: float = None,
        preselected_pool_name: Optional[str] = None,
    ):
        self.lcu = LCUClient(verbose=verbose)
        self.assistant = Assistant()
        self.last_draft_state = DraftState()
        self.champion_id_to_name: Dict[int, str] = {}  # Riot ID -> Display name
        # SPEC-04 B4 §7: loaded once at startup, never re-read per draft tick.
        self.lane_distributions: Dict[int, Dict[str, float]] = {}
        # SPEC-04 B5: manual role corrections (championId -> lane), applied on
        # top of infer_team_roles() every tick until the champion leaves the
        # draft. Commands ("r <champion> <lane>") arrive via a background
        # stdin thread and are drained on the main poll thread (_monitor_loop)
        # so LCU/db access stays single-threaded.
        self.forced_roles: Dict[int, str] = {}
        self._command_queue: "queue.Queue[str]" = queue.Queue()
        self._command_listener_thread: Optional[threading.Thread] = None
        self.is_monitoring = False
        self.verbose = verbose
        self.current_pool = TOP_SOLOQ_POOL  # Default pool
        self.pool_name = None  # Pool name for pre-calculated ban lookups
        self.auto_select_pool = auto_select_pool
        # SPEC-06 D2: pool mémorisée d'une session précédente, réutilisée sans
        # re-poser la question si elle existe toujours.
        self.preselected_pool_name = preselected_pool_name
        self.auto_hover = auto_hover
        self.auto_accept_queue = auto_accept_queue
        self.auto_ban_hover = auto_ban_hover
        self.open_onetricks = (
            open_onetricks
            if open_onetricks is not None
            else draft_config.OPEN_ONETRICKS_ON_DRAFT_END
        )
        self.synergy_weight = (
            synergy_weight if synergy_weight is not None else draft_config.DEFAULT_SYNERGY_WEIGHT
        )
        self.last_recommendation = None  # Track last recommendation to avoid spam
        self.last_ban_recommendation = None  # Track last ban recommendation to avoid spam
        self.has_done_initial_hover = False  # Track if we've done the initial hover
        self.last_gameflow_phase = ""  # Track last gameflow phase
        self.has_analyzed_final_draft = False  # Track if we've already analyzed the final draft
        self.ready_check_accepted_time = 0  # Track when we accepted ready check
        self.player_champion = None  # Track the player's selected champion

        # SPEC-05 B7 §8-9: id of the last logged prediction row awaiting an
        # outcome, set by _calculate_final_scores and consumed by the manual
        # "outcome win"/"outcome loss" command. None = nothing to update.
        self._last_prediction_id: Optional[int] = None

        # OneTricks browser window recycling: keep a single handle so each new
        # draft replaces the previous window instead of stacking tabs/processes
        # (otherwise Brave accumulates one tab per game → system OOM on long sessions).
        self._onetricks_proc: Optional[subprocess.Popen] = None

        # Memory diagnostics: count poll-loop iterations to log RSS periodically.
        self._loop_count = 0

    def start_monitoring(self):
        """Start monitoring champion select."""
        print("[BOT] League Draft Coach - Démarrage...")

        if not self.lcu.connect():
            return False

        # Load champion ID mappings
        self._load_champion_mappings()
        self._load_lane_distributions()

        # Pool selection
        if not self.auto_select_pool:
            if self.preselected_pool_name:
                self.current_pool = self._select_champion_pool_by_name(self.preselected_pool_name)
            else:
                self.current_pool = self._select_champion_pool_interactive()
        else:
            # Auto-select top pool by default
            self.pool_name = "All Top Champions"  # System pool name
            self.current_pool = CHAMPIONS_BY_ROLE["top"]
            safe_print(f"[OK] Pool utilisée : TOP ({', '.join(self.current_pool)})")

        # Performance: Warm cache for selected pool (eliminates SQL queries during draft)
        if self.current_pool:
            self.assistant.warm_cache(self.current_pool)

        # Clear console before starting monitoring loop
        clear_console()

        self.is_monitoring = True
        print("[WATCH] Surveillance du champion select...")
        print("   (Démarrez une partie pour voir les recommandations de draft)")
        if self.auto_accept_queue:
            print("   [AUTO-ACCEPT] Acceptation automatique de la queue ACTIVÉE")
        if self.auto_ban_hover:
            print("   [AUTO-BAN-HOVER] Survol automatique des bans ACTIVÉ")
        if self.open_onetricks:
            print("   [ONETRICKS] Ouverture de la page du champion en fin de draft ACTIVÉE")
        print(
            "   Tapez 'r <champion> <lane>' + Entrée pour forcer un rôle (ex. r Pantheon support)"
        )
        print(
            "   Tapez 'outcome win' ou 'outcome loss' + Entrée après la partie pour logger le résultat"
        )
        print("   (Ctrl+C pour arrêter)")

        self._start_command_listener()

        # Log a baseline RSS measurement at startup for diagnostics.
        self._log_memory_usage(force=True)

        try:
            while self.is_monitoring:
                self._monitor_loop()
                self._loop_count += 1
                self._log_memory_usage()
                time.sleep(draft_config.POLL_INTERVAL)  # Check draft state periodically
        except KeyboardInterrupt:
            print("\n[STOP] Arrêt du draft monitor...")
        finally:
            self.cleanup()

    def _onetricks_profile_dir(self) -> str:
        """Return the dedicated, reused Brave profile dir for the OneTricks window.

        Using a dedicated ``--user-data-dir`` makes the launched Brave a standalone
        process we fully control (and can terminate). Without it, Brave merges the
        request into the user's main instance, our handle exits immediately, and we
        lose the ability to close the previous tab — which is what caused tabs to
        pile up across games. The directory is fixed (not per-call) so it is reused.
        """
        return os.path.join(tempfile.gettempdir(), "leaguestats_onetricks_profile")

    def _close_onetricks_window(self) -> None:
        """Terminate the previously opened OneTricks window, if any.

        Guarantees at most one OneTricks window is alive at a time, preventing the
        per-game tab/process accumulation that drove system memory growth.
        """
        proc = self._onetricks_proc
        if proc is None:
            return
        try:
            if proc.poll() is None:  # still running
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
        except Exception as e:
            if self.verbose:
                print(f"[ONETRICKS] Failed to close previous window: {e}")
        finally:
            self._onetricks_proc = None

    def _open_champion_page_on_onetricks(self):
        """Open the player's champion page on OneTriks.gg, recycling a single window.

        Each completed draft replaces the previous OneTricks window instead of
        opening a new tab, so Brave does not accumulate one tab per game over a
        long Draft Monitor session.
        """
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
                # Fallback to default browser. Note: we cannot recycle the default
                # browser's tabs, so accumulation is only fully prevented with Brave.
                import webbrowser

                webbrowser.open(onetricks_url)
                return

            # Close the previous OneTricks window before opening a new one.
            self._close_onetricks_window()

            # Launch a dedicated, killable Brave app window (see _onetricks_profile_dir).
            self._onetricks_proc = subprocess.Popen(
                [
                    brave_path,
                    f"--app={onetricks_url}",
                    f"--user-data-dir={self._onetricks_profile_dir()}",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        except Exception as e:
            if self.verbose:
                print(f"[WARNING] Échec d'ouverture de la page OneTricks.gg: {e}")
            else:
                print(f"[WARNING] Échec d'ouverture de la page du champion dans le navigateur")

    def stop_monitoring(self):
        """Stop monitoring."""
        self.is_monitoring = False

    # Log RSS roughly every 5 minutes (POLL_INTERVAL is 1s by default).
    _MEMORY_LOG_INTERVAL = 300

    def _log_memory_usage(self, force: bool = False) -> None:
        """Record the process RSS to logs/draft_monitor_memory.log periodically.

        This is a lightweight diagnostic to determine whether the monitor's own
        Python process grows over a long session (a leak to bisect) or stays flat
        (pointing at an external cause such as accumulating browser tabs).

        Args:
            force: If True, log immediately regardless of the interval.
        """
        if not force and self._loop_count % self._MEMORY_LOG_INTERVAL != 0:
            return
        try:
            import psutil

            rss_mb = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
            _get_memory_logger().info(
                "iteration=%d rss=%.1fMB onetricks_window=%s",
                self._loop_count,
                rss_mb,
                "open" if self._onetricks_proc and self._onetricks_proc.poll() is None else "none",
            )
        except Exception:
            # Diagnostics must never interrupt monitoring.
            pass

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
                        print("\n[INFO] Champion select quitté - La partie démarre !")

                        # Show ready message for next game
                        print("\n" + "=" * 60)
                        print("[READY] En attente de la prochaine partie...")
                        if self.auto_accept_queue:
                            print("   Auto-accept activé pour la prochaine queue")
                        print("   (Relancez une recherche de partie !)")
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

            # SPEC-04 B5: apply any queued "r <champion> <lane>" corrections —
            # forces a redisplay even when the draft itself hasn't changed.
            commands_applied = self._apply_pending_commands(current_state)

            # Check for changes and provide recommendations (only if draft not complete)
            if self._has_draft_changed(current_state) or commands_applied:
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
                    print("[QUEUE] PARTIE TROUVÉE !")
                    print("=" * 60)

                    # Get ready check details if available
                    ready_check = self.lcu.get_ready_check_state()
                    if ready_check and self.verbose:
                        timer = ready_check.get("timer", 0)
                        print(f"[DEBUG] Ready check timer: {timer}s")

                    # Auto-accept the queue
                    if self.lcu.accept_ready_check():
                        print("[OK] [AUTO-ACCEPT] Queue acceptée automatiquement !")
                        self.ready_check_accepted_time = current_time
                    else:
                        print("[ALERTE] [AUTO-ACCEPT] Échec de l'acceptation de la queue")

                    print("En attente des autres joueurs...")
                    print("=" * 60)

            # Handle transitions out of ready check
            elif self.last_gameflow_phase == "ReadyCheck" and current_phase != "ReadyCheck":
                if current_phase == "ChampSelect":
                    print(
                        "[OK] [SUCCESS] Tous les joueurs ont accepté - Entrée en champion select !"
                    )
                elif current_phase in ["Lobby", "Matchmaking"]:
                    print("[ALERTE] [FAILED] Échec du ready check - Un joueur n'a pas accepté")
                    print("[RETRY] Retour en file d'attente...")
                    # Reset ready check timer to allow new detection
                    self.ready_check_accepted_time = 0

            # Update last phase
            self.last_gameflow_phase = current_phase

        except Exception as e:
            if self.verbose:
                print(f"[WARNING] Error handling ready check: {e}")

    def _handle_auto_ban_hover(self, state: DraftState):
        """Handle auto-ban-hover when it's our turn to ban."""
        import sys

        if getattr(sys, "frozen", False):
            return  # Skip ban hover in .exe mode
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
                    if self._auto_hover_champion(top_ban, "Recommandation de ban"):
                        print(
                            f"  [AUTO-BAN-HOVER] Survol de {top_ban} (Menace : {threat_score:.2f})"
                        )
                        self.last_ban_recommendation = top_ban
                    else:
                        print(f"  [ALERTE] [AUTO-BAN-HOVER] Échec du survol de {top_ban}")
                else:
                    print(f"  [ALERTE] [AUTO-BAN-HOVER] {top_ban} déjà banni, ignoré")
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
                print("[DRAFT TERMINÉ] Tous les champions verrouillés - Analyse finale !")
                print("=" * 80)

                self._calculate_final_scores(
                    ally_picks, enemy_picks, ally_lanes=state.inferred_roles
                )

                # Mark analysis as done
                self.has_analyzed_final_draft = True

                # Open champion page on OneTriks.gg if enabled
                if self.open_onetricks:
                    self._open_champion_page_on_onetricks()

        except Exception as e:
            print(f"[ERREUR] Échec de l'analyse du draft complet: {e}")
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
        self.forced_roles = {}  # SPEC-04 B5: corrections don't carry to the next game
        self._last_prediction_id = None  # SPEC-05 B7: predictions don't carry to the next game

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

    def _load_lane_distributions(self):
        """Load the lane likelihood matrix for role inference (SPEC-04 B4).

        Loaded once here, not re-read from the DB on every draft tick — see
        SPEC-04 §7 (120 permutations per team are negligible; a DB round
        trip every second is not).
        """
        try:
            self.lane_distributions = self.assistant.db.get_all_champion_lane_distributions()
            if self.verbose:
                print(
                    f"[DATA] Loaded lane distributions for {len(self.lane_distributions)} champions"
                )
        except Exception as e:
            if self.verbose:
                print(f"[WARNING] Error loading lane distributions: {e}")

    def _start_command_listener(self) -> None:
        """Background stdin reader for role corrections (SPEC-04 B5).

        A daemon thread blocking on input() so the poll loop never blocks on
        the terminal; _apply_pending_commands() drains the queue from the
        main thread every tick, keeping LCU/db access single-threaded.
        """
        if self._command_listener_thread is not None:
            return

        def _listen() -> None:
            while self.is_monitoring:
                try:
                    line = input()
                except (EOFError, RuntimeError):
                    return
                if line.strip():
                    self._command_queue.put(line)

        self._command_listener_thread = threading.Thread(target=_listen, daemon=True)
        self._command_listener_thread.start()

    def _apply_pending_commands(self, state: DraftState) -> bool:
        """Drain queued commands: role corrections (SPEC-04 B5) and manual
        outcome logging (SPEC-05 B7 §9).

        Returns True if at least one command was applied, so the caller can
        force a redisplay even when the draft itself hasn't changed.
        """
        applied = False
        while True:
            try:
                line = self._command_queue.get_nowait()
            except queue.Empty:
                break
            stripped = line.strip()
            if stripped.lower().startswith("outcome"):
                # Never affects the draft display, so it doesn't set `applied`.
                self._handle_outcome_command(stripped)
                continue
            if self._handle_correction_command(line, state):
                applied = True
        return applied

    def _handle_correction_command(self, line: str, state: DraftState) -> bool:
        """Parse and apply one 'r <champion> <lane>' correction command."""
        parts = line.strip().split()
        if len(parts) != 3 or parts[0].lower() != "r":
            print(f"[ROLE] Commande non reconnue : '{line}'. Format attendu : r <champion> <lane>")
            return False

        _, champion_input, lane_input = parts
        lane = lane_input.lower()
        if lane not in scraping_config.LANES:
            print(
                f"[ROLE] Lane inconnue : '{lane_input}'. "
                f"Valeurs valides : {', '.join(scraping_config.LANES)}"
            )
            return False

        name_to_id = {name.lower(): champ_id for champ_id, name in self.champion_id_to_name.items()}
        champion_id = name_to_id.get(champion_input.lower())
        if champion_id is None:
            print(f"[ROLE] Champion inconnu : '{champion_input}'")
            return False

        if champion_id not in state.ally_picks and champion_id not in state.enemy_picks:
            print(f"[ROLE] {champion_input} n'est pas dans le draft en cours")
            return False

        self.forced_roles[champion_id] = lane
        state.inferred_roles[champion_id] = lane
        state.role_confidence[champion_id] = 1.0
        state.role_source[champion_id] = "user"
        print(f"[ROLE] {self._get_display_name(champion_id)} forcé sur {lane}")
        return True

    def _handle_outcome_command(self, line: str) -> None:
        """Parse and apply one 'outcome win'/'outcome loss' command (SPEC-05
        B7 §9): journalise le résultat réel de la partie sur la dernière
        prédiction en attente, pour la calibration (scripts/calibrate_model.py).

        Manual command by design (not a gameflow/EndOfGame hook, per SPEC-05:
        untestable against a real LCU client without speculating on its
        behavior). Best-effort: never raises, never blocks the draft loop.
        """
        parts = line.split()
        if len(parts) != 2 or parts[1].lower() not in ("win", "loss"):
            print(f"[OUTCOME] Commande non reconnue : '{line}'. Format attendu : outcome win|loss")
            return

        if self._last_prediction_id is None:
            print("[OUTCOME] Aucune prédiction à mettre à jour pour cette partie")
            return

        outcome = 1 if parts[1].lower() == "win" else 0
        try:
            updated = self.assistant.db.update_prediction_outcome(self._last_prediction_id, outcome)
            if updated:
                print(
                    f"[OUTCOME] Prédiction #{self._last_prediction_id} enregistrée comme {parts[1].lower()}"
                )
            else:
                print(f"[OUTCOME] Aucune prédiction trouvée pour l'id #{self._last_prediction_id}")
        except Exception as e:
            print(f"[WARNING] Échec de la mise à jour du résultat de la prédiction: {e}")

        # One outcome update per game, whether it succeeded or not.
        self._last_prediction_id = None

    def _get_display_name(self, champion_id: int) -> str:
        """Get display name for champion ID."""
        return self.champion_id_to_name.get(champion_id, f"Champion{champion_id}")

    def _calculate_score_against_team(
        self,
        matchups: List[tuple],
        enemy_team: List[int],
        champion_name: str,
        banned_champion_ids: List[int] = None,
        lane: Optional[str] = None,
        enemy_lanes: Optional[Dict[str, str]] = None,
        player_lane: Optional[str] = None,
    ) -> float:
        """Calculate score against enemy team using Assistant's method.

        Args:
            lane: Lane optionnelle transmise aux requêtes inverses internes
                  (cf. ChampionScorer.score_against_team). None = comportement
                  inchangé. La détection automatique de la lane est hors
                  périmètre ici (SPEC-04) : la valeur arrive de l'extérieur.
            enemy_lanes: Enemy display name -> inferred lane (SPEC-04 §4.3),
                  from state.inferred_roles. Weights the enemy sharing our
                  lane above the rest of the enemy team.
            player_lane: Our own (the local player's) lane.
        """
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
            matchups,
            enemy_names,
            champion_name,
            banned_names if banned_names else None,
            lane=lane,
            enemy_lanes=enemy_lanes,
            player_lane=player_lane,
        )

    def _calculate_synergy_score(
        self, champion_name: str, ally_team: List[int], lane: Optional[str] = None
    ) -> float:
        """Calculate synergy score as sum of delta2 with allied champions.

        Args:
            champion_name: Name of the champion to evaluate
            ally_team: List of allied champion IDs already picked
            lane: Lane optionnelle transmise à get_synergy_delta2. None =
                  comportement inchangé (agrégation toutes lanes).

        Returns:
            Sum of delta2 values for synergies with allies (0.0 if no allies)
        """
        if not ally_team:
            return 0.0

        synergy_score = 0.0

        for ally_id in ally_team:
            ally_name = self._get_display_name(ally_id)
            if ally_name:
                delta2 = self.assistant.db.get_synergy_delta2(champion_name, ally_name, lane=lane)
                if delta2 is not None:
                    synergy_score += delta2
                    if self.verbose:
                        print(f"[DEBUG] Synergy: {champion_name} + {ally_name} = {delta2:+.2f}")

        return synergy_score

    def _final_score(self, matchup_score: float, synergy_score: float) -> float:
        """Blend matchup and synergy scores using the configurable synergy weight.

        Formula: final_score = matchup_score * min(1, 2 * (1 - synergy_weight))
                              + synergy_score * min(1, 2 * synergy_weight)

        The min(1, ...) clamp is what makes all three pinned cases exact:
        - synergy_weight=0.5 (default): both coefficients clamp to 1
          -> final_score = matchup_score + synergy_score (unchanged historical behavior).
        - synergy_weight=0.0: matchup coefficient clamps to 1, synergy coefficient is 0
          -> final_score = matchup_score (synergy fully ignored).
        - synergy_weight=1.0: synergy coefficient clamps to 1, matchup coefficient is 0
          -> final_score = synergy_score (matchup fully ignored).
        (The naive matchup_score * (1 - w) * 2 + synergy_score * w * 2, without the
        clamp, would double-count at w=0 and w=1, so the clamp is required.)
        """
        matchup_weight = min(1.0, 2 * (1 - self.synergy_weight))
        synergy_weight = min(1.0, 2 * self.synergy_weight)
        return matchup_score * matchup_weight + synergy_score * synergy_weight

    def _parse_draft_state(self, champ_select_data: Dict) -> DraftState:
        """Parse champion select data into DraftState."""
        state = DraftState()

        # Get basic info
        state.phase = champ_select_data.get("timer", {}).get("phase", "")
        state.local_player_cell_id = champ_select_data.get("localPlayerCellId")

        # Parse team composition
        my_team = champ_select_data.get("myTeam", [])
        their_team = champ_select_data.get("theirTeam", [])

        # SPEC-04 B3: cellId -> lane, for allies whose role is assigned by the queue
        state.ally_positions = self.lcu.get_assigned_positions(champ_select_data)

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

        # SPEC-04 B4 §4.3: infer roles for both teams, recalculated on every
        # parse so the picture sharpens as the draft fills in. Allies with a
        # known assignedPosition are fixed; enemies are purely inferred
        # (their assignedPosition is hidden by the LCU).
        if state.ally_picks:
            known_positions = {
                player.get("championId"): state.ally_positions[player.get("cellId")]
                for player in my_team
                if player.get("championId", 0) > 0 and player.get("cellId") in state.ally_positions
            }
            ally_assignment = infer_team_roles(
                state.ally_picks, self.lane_distributions, known_positions=known_positions
            )
            state.inferred_roles.update(ally_assignment.roles)
            state.role_confidence.update(ally_assignment.confidence)
            state.role_source.update(ally_assignment.source)

        if state.enemy_picks:
            enemy_assignment = infer_team_roles(state.enemy_picks, self.lane_distributions)
            state.inferred_roles.update(enemy_assignment.roles)
            state.role_confidence.update(enemy_assignment.confidence)
            state.role_source.update(enemy_assignment.source)

        # SPEC-04 B5: user-forced roles override the fresh inference above and
        # survive recalculation as long as the champion stays in the draft.
        for champion_id, lane in list(self.forced_roles.items()):
            if champion_id in state.ally_picks or champion_id in state.enemy_picks:
                state.inferred_roles[champion_id] = lane
                state.role_confidence[champion_id] = 1.0
                state.role_source[champion_id] = "user"
            else:
                del self.forced_roles[champion_id]

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
        print(f"[INFO] MISE À JOUR DU DRAFT - Phase : {state.phase}")
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

    def _format_role_tag(self, champion_id: int, state: DraftState) -> str:
        """Role annotation for one champion in the draft display (SPEC-04 B5).

        "(lane·LCU)" for a role certain from the queue, "(lane·forced)" for a
        manual correction, "(lane·NN%)" for an inferred one — with a trailing
        "?" below ROLE_CONFIDENCE_WARN to flag it for a `r <champion> <lane>`
        check. Empty string when no lane is known yet (e.g. before B4's
        distributions load, or a champion missing from the lane_distributions
        likelihood matrix).
        """
        lane = state.inferred_roles.get(champion_id)
        if lane is None:
            return ""

        source = state.role_source.get(champion_id, "inferred")
        if source == "lcu":
            label = "LCU"
        elif source == "user":
            label = "forcé"
        else:
            confidence = state.role_confidence.get(champion_id, 0.0)
            label = f"{confidence * 100:.0f}%"
            if confidence < role_inference_config.ROLE_CONFIDENCE_WARN:
                label += "?"

        return f" ({lane}·{label})"

    def _display_draft_state(self, state: DraftState):
        """Display current draft state in terminal."""
        print(f"\n[ALLY] ÉQUIPE ALLIÉE :")
        if state.ally_picks:
            for i, champ_id in enumerate(state.ally_picks, 1):
                display_name = self._get_display_name(champ_id)
                print(f"  {i}. {display_name}{self._format_role_tag(champ_id, state)}")
        else:
            print("  (Aucun pick pour l'instant)")

        # Only show bans during ban phases or when bans are relevant
        if state.ally_bans and self._should_show_bans(state):
            display_bans = [self._get_display_name(champ_id) for champ_id in state.ally_bans]
            print(f"  Bans : {', '.join(display_bans)}")

        print(f"\n[ENEMY] ÉQUIPE ENNEMIE :")
        if state.enemy_picks:
            for i, champ_id in enumerate(state.enemy_picks, 1):
                display_name = self._get_display_name(champ_id)
                print(f"  {i}. {display_name}{self._format_role_tag(champ_id, state)}")
        else:
            print("  (Aucun pick pour l'instant)")

        # Only show bans during ban phases or when bans are relevant
        if state.enemy_bans and self._should_show_bans(state):
            display_bans = [self._get_display_name(champ_id) for champ_id in state.enemy_bans]
            print(f"  Bans : {', '.join(display_bans)}")

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
                print(f"\n[PICKS] RECOMMANDATIONS DE COUNTERPICK :")
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

                # SPEC-04 B4 §4.3: our own lane (from the LCU, when the queue
                # assigns one) and the enemy team's inferred lanes, for the
                # same-lane weighting in _calculate_score_against_team.
                player_lane = state.ally_positions.get(state.local_player_cell_id)
                enemy_lanes = {
                    self._get_display_name(enemy_id): state.inferred_roles[enemy_id]
                    for enemy_id in enemy_picks
                    if enemy_id in state.inferred_roles
                }
                # SPEC-04 B5: the enemy sharing our lane, shown as "vs X" next
                # to each recommendation.
                direct_counter_name = next(
                    (name for name, lane in enemy_lanes.items() if lane == player_lane), None
                )

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
                    total_games = sum(m.games for m in matchups) if matchups else 0
                    if matchups and total_games >= 500:  # Threshold for valid data
                        # Calculate matchup score against enemy team
                        matchup_score = self._calculate_score_against_team(
                            matchups,
                            enemy_picks,
                            champion_name,
                            all_banned_ids,
                            enemy_lanes=enemy_lanes,
                            player_lane=player_lane,
                        )

                        # Calculate synergy score with allied champions
                        synergy_score = self._calculate_synergy_score(
                            champion_name, ally_picks, lane=player_lane
                        )

                        # Final score = configurable blend of matchup and synergy (see _final_score)
                        final_score = self._final_score(matchup_score, synergy_score)

                        if self.verbose:
                            print(
                                f"[DEBUG] {champion_name}: Matchup={matchup_score:.2f}, "
                                f"Synergy={synergy_score:+.2f}, Final={final_score:.2f}"
                            )

                        # Le détail est conservé pour l'affichage : le recalculer
                        # coûtait un second passage et pouvait diverger du classement
                        scores.append(
                            (champion_id, final_score, matchup_score, synergy_score, total_games)
                        )

                scores.sort(key=lambda x: -x[1])

                # Show top 3 recommendations
                display_count = min(3, len(scores))
                top_recommendation = None

                for i in range(display_count):
                    champion_id, final_score, matchup_score, synergy_score, games = scores[i]
                    display_name = self._get_display_name(champion_id)
                    rank = "[1st]" if i == 0 else "[2nd]" if i == 1 else "[3rd]"

                    # Format score as win rate advantage with breakdown
                    score_text = (
                        f"+{final_score:.2f}%" if final_score > 0 else f"{final_score:.2f}%"
                    )
                    breakdown = f"(Matchup: {matchup_score:+.2f}%, Synergy: {synergy_score:+.2f}%)"

                    # SPEC-04 B5: show our lane, the direct-lane counter (if
                    # any) and the games volume behind the score.
                    lane_tag = ""
                    if player_lane:
                        lane_tag = f" ({player_lane}"
                        if direct_counter_name:
                            lane_tag += f" vs {direct_counter_name}"
                        lane_tag += ")"
                    volume_tag = f" · {games:,} games".replace(",", " ")

                    print(f"  {rank} {display_name}{lane_tag} {score_text} {breakdown}{volume_tag}")

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
                        reason = (
                            "À vous de jouer" if is_our_turn else "Mise à jour d'un pick ennemi"
                        )
                        self._auto_hover_champion(top_recommendation, reason)
                        self.last_recommendation = top_recommendation

                if not scores:
                    print("  [DATA] Aucune donnée disponible pour les matchups actuels")

            # Handle auto-ban-hover for ban phases (independent of pick phase)
            if self._is_ban_phase(state) and self.auto_ban_hover:
                self._handle_auto_ban_hover(state)

            # Phase-specific advice (dynamic based on actual game state)
            advice = None
            if state.phase == "PLANNING":
                advice = "[PLAN] Réfléchissez à la composition d'équipe et aux priorités de ban"
            elif state.phase == "BAN_PICK":
                # BAN_PICK phase includes both bans and picks - detect which we're in
                if self._is_ban_phase(state):
                    advice = "[BAN] Concentrez-vous sur les bans des forces adverses"
                else:
                    advice = "[PICK] C'est le moment de sécuriser votre champion !"
            elif state.phase == "PICK":
                advice = "[PICK] C'est le moment de sécuriser votre champion !"
            elif state.phase == "FINALIZATION":
                advice = "[FINAL] Finalisez runes et sorts d'invocateur"

            if advice:
                print(f"\n[ADVICE] {advice}")

        except Exception as e:
            print(f"[WARNING] Erreur lors de la génération des recommandations: {e}")

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
                print(f"  [AUTO-HOVER] {champion_name} survolé{reason_text}")
            else:
                if self.verbose:
                    print(f"  [ALERTE] [AUTO-HOVER] Échec du survol de {champion_name}")
        except Exception as e:
            if self.verbose:
                print(f"  [ERREUR] [AUTO-HOVER] Erreur lors du survol de {champion_name}: {e}")

    def _do_initial_hover(self):
        """Do initial hover with the best champion from the pool when entering champion select."""
        try:
            # Clear console at start of champion select
            clear_console()

            print(f"\n[INITIAL] Champion select démarré - Préparation de votre stratégie !")
            print("=" * 80)

            # Get best champion from current pool (first champion as fallback)
            if not self.current_pool:
                if self.verbose:
                    print("  [ALERTE] [INITIAL-HOVER] Aucun champion dans la pool")
                return

            # Calculate best champion from pool using smart analysis
            initial_champion = self._get_best_champion_from_pool()

            # Show the recommended blind pick
            print(f"\n[PICK] MEILLEUR BLIND PICK DE VOTRE POOL :")
            print(f"  [OK] {initial_champion}")
            print(f"  [INFO] Si vous êtes premier pick, c'est votre choix le plus sûr !")

            # Auto-hover the champion
            self._auto_hover_champion(initial_champion, "Meilleur blind pick")
            self.last_recommendation = initial_champion

            # Show ban recommendations immediately
            self._show_ban_recommendations_draft()

            print("\n" + "=" * 80)
            print("[INFO] En attente du début du draft...")
            print("=" * 80)

        except Exception as e:
            if self.verbose:
                print(f"  [ALERTE] [INITIAL-HOVER] Erreur lors du hover initial: {e}")

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
                        f"  [OK] [INITIAL-HOVER] Meilleur de la pool : {best_champion} ({scores[0][1]:+.2f}% d'avantage)"
                    )
                return best_champion
            else:
                # Fallback to first champion
                return self.current_pool[0]

        except Exception as e:
            if self.verbose:
                print(f"  [ALERTE] [INITIAL-HOVER] Erreur d'obtention du meilleur champion: {e}")
            return self.current_pool[0]  # Fallback

    def _show_ban_recommendations_draft(self):
        """Show ban recommendations for current pool during draft."""
        import sys

        if getattr(sys, "frozen", False):
            return  # Skip ban recommendations in .exe mode

        try:
            print(f"\n[BANS] RECOMMANDATIONS DE BAN STRATÉGIQUES")
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
                print(f"Envisagez de bannir ces menaces pour votre pool :")
                # Tuple format: (enemy, threat_score, best_delta2, best_champ, matchup_count)
                for i, (enemy, threat_score, _best_delta2, _best_champ, matchup_count) in enumerate(
                    ban_recommendations, 1
                ):
                    print(
                        f"  {i}. {enemy:<12} | Menace : {threat_score:>5.2f} | Counter {matchup_count}/{len(self.current_pool)} de vos champions"
                    )
                print(f"[INFO] Ces champions ont de bons matchups contre votre pool")
            else:
                if self.verbose:
                    print(f"[ALERTE] Aucune donnée de ban disponible pour votre pool")

        except Exception as e:
            if self.verbose:
                print(f"[WARNING] Erreur lors de l'affichage des recommandations de ban: {e}")

    def _show_adaptive_ban_recommendations(self, state: DraftState):
        """Show ban recommendations adapted to enemy picks."""
        import sys

        if getattr(sys, "frozen", False):
            return  # Skip adaptive bans in .exe mode
        try:
            if not state.enemy_picks:
                return

            print(f"\n[ADAPTIVE BANS] RECOMMANDATIONS DE BAN CIBLÉES")
            print("-" * 50)

            # Get enemy champion names
            enemy_names = [self._get_display_name(champ_id) for champ_id in state.enemy_picks]
            print(f"L'équipe ennemie a : {', '.join(enemy_names)}")

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
                print(f"Bans prioritaires pour neutraliser les synergies ennemies :")
                for i, (enemy, threat_score, *_) in enumerate(ban_recommendations[:3], 1):
                    print(f"  {i}. {enemy:<12} | Menace : {threat_score:>5.2f}")
                print(f"[INFO] Ciblez les champions qui synergisent avec leurs picks")

        except Exception as e:
            if self.verbose:
                print(f"[WARNING] Erreur lors de l'affichage des bans ciblés: {e}")

    def _select_champion_pool_by_name(self, pool_name: str) -> List[str]:
        """Charge une pool mémorisée par son nom, sans re-poser la question.

        Retombe sur la sélection interactive si la pool a été supprimée ou
        renommée depuis la dernière session (SPEC-06 D2).
        """
        try:
            from .pool_manager import PoolManager

            pool_manager = PoolManager()
            pool = pool_manager.get_pool(pool_name)
            if pool is None:
                print(f"[INFO] Pool '{pool_name}' introuvable, sélection manuelle.")
                return self._select_champion_pool_interactive()

            safe_print(f"[OK] Pool mémorisée utilisée : {pool_name} ({', '.join(pool.champions)})")
            self.pool_name = pool_name
            return pool.champions
        except Exception as e:
            print(f"[WARNING] Erreur lors du chargement de la pool mémorisée: {e}")
            return self._select_champion_pool_interactive()

    def _select_champion_pool_interactive(self) -> List[str]:
        """Interactive pool selection with custom pools support."""
        try:
            from .pool_manager import PoolManager

            pool_manager = PoolManager()

            print("\n" + "=" * 50)
            print("SÉLECTION DE LA POOL DE CHAMPIONS")
            print("=" * 50)

            # Show available pools
            pools = pool_manager.get_all_pools()
            pool_list = []

            print("\nPools disponibles :")
            idx = 1
            for name, pool in sorted(pools.items()):
                pool_list.append((name, pool))
                status = "[SYS]" if pool.created_by == "system" else "[USR]"
                print(
                    f"  {idx}. {status} {name:<20} | {pool.role:<8} | {pool.size():>2} champs | {pool.description}"
                )
                idx += 1

            # Add legacy options
            print(f"\n  {idx}. Utiliser le sélecteur de pool étendu de l'assistant (legacy)")

            try:
                choice = int(input(f"\nChoisissez une pool (1-{idx}) : ").strip())

                if 1 <= choice <= len(pool_list):
                    selected_name, selected_pool = pool_list[choice - 1]
                    safe_print(
                        f"[OK] Pool utilisée : {selected_name} ({', '.join(selected_pool.champions)})"
                    )
                    # Store pool name for pre-calculated ban lookups
                    self.pool_name = selected_name
                    return selected_pool.champions
                elif choice == idx:
                    # Fallback to assistant's method (no pool_name)
                    self.pool_name = None
                    return self.assistant.select_champion_pool()
                else:
                    print("[WARNING] Choix invalide, utilisation de la pool TOP par défaut")
                    self.pool_name = "All Top Champions"  # System pool name
                    return CHAMPIONS_BY_ROLE["top"]

            except (ValueError, IndexError):
                print("[WARNING] Saisie invalide, utilisation de la pool TOP par défaut")
                self.pool_name = "All Top Champions"
                return CHAMPIONS_BY_ROLE["top"]

        except Exception as e:
            print(f"[WARNING] Erreur de sélection de pool: {e}")
            print("Retour au sélecteur de pool legacy...")
            self.pool_name = None
            return self.assistant.select_champion_pool()

    def _calculate_final_scores(
        self,
        ally_picks: List[int],
        enemy_picks: List[int],
        ally_lanes: Optional[Dict[int, str]] = None,
    ):
        """Calculate individual scores for each champion at end of draft.

        Args:
            ally_lanes: championId -> inferred lane (state.inferred_roles),
                used only to log the prediction row (SPEC-05 B7 §8). None =
                no lane info stored with the prediction.
        """
        # Clear console before final analysis for clean display
        clear_console()

        print("\n" + "=" * 80)
        print("ANALYSE FINALE DU DRAFT - Scores individuels des champions")
        print("=" * 80)

        if not ally_picks or not enemy_picks:
            print("[INFO] Draft incomplet - aucune analyse finale disponible")
            return

        ally_names = [self._get_display_name(champ_id) for champ_id in ally_picks]
        enemy_names = [self._get_display_name(champ_id) for champ_id in enemy_picks]

        print(f"\n[TEAMS] COMPOSITION FINALE :")
        print(f"  Équipe alliée :  {' | '.join(ally_names)}")
        print(f"  Équipe ennemie : {' | '.join(enemy_names)}")

        print(f"\nANALYSE DE PERFORMANCE D'ÉQUIPE :")
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

                # Total score = configurable blend of matchup and synergy (see _final_score)
                total_score = self._final_score(matchup_score, synergy_score)

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

                # Total score = configurable blend of matchup and synergy (see _final_score)
                total_score = self._final_score(matchup_score, synergy_score)

                enemy_scores.append((champion_name, matchup_score, synergy_score, total_score))

            except Exception as e:
                enemy_scores.append((champion_name, None, 0.0, 0.0))  # Mark error

        # Sort both teams by total score (descending - best scores first)
        ally_scores.sort(
            key=lambda x: x[3] if x[1] is not None else -999, reverse=True
        )  # Sort by total_score
        enemy_scores.sort(key=lambda x: x[3] if x[1] is not None else -999, reverse=True)

        # Helper function to get an ASCII strength marker for a score
        def get_emoji(score):
            if score >= 2.0:
                return "[++]"
            elif score >= 1.0:
                return "[+]"
            elif score >= -1.0:
                return "[~]"
            elif score >= -2.0:
                return "[-]"
            else:
                return "[--]"

        # Display ALLY team performance (sorted)
        print(f"\nVOTRE ÉQUIPE :")
        print(f"  {'Champion':<15} | Matchup | Synergy | Total")
        print(f"  {'-'*15}-+---------+---------+-------")
        for champion_name, matchup_score, synergy_score, total_score in ally_scores:
            if matchup_score is None:
                print(f"  {champion_name:<15} | Données insuffisantes")
            else:
                matchup_emoji = get_emoji(matchup_score)
                synergy_emoji = get_emoji(synergy_score)
                total_emoji = get_emoji(total_score)
                print(
                    f"  {champion_name:<15} | {matchup_emoji} {matchup_score:+5.1f} | "
                    f"{synergy_emoji} {synergy_score:+5.1f} | {total_emoji} {total_score:+5.1f}"
                )

        # Display ENEMY team performance (sorted)
        print(f"\nÉQUIPE ENNEMIE :")
        print(f"  {'Champion':<15} | Matchup | Synergy | Total")
        print(f"  {'-'*15}-+---------+---------+-------")
        for champion_name, matchup_score, synergy_score, total_score in enemy_scores:
            if matchup_score is None:
                print(f"  {champion_name:<15} | Données insuffisantes")
            else:
                matchup_emoji = get_emoji(matchup_score)
                synergy_emoji = get_emoji(synergy_score)
                total_emoji = get_emoji(total_score)
                print(
                    f"  {champion_name:<15} | {matchup_emoji} {matchup_score:+5.1f} | "
                    f"{synergy_emoji} {synergy_score:+5.1f} | {total_emoji} {total_score:+5.1f}"
                )

        # Team summary comparison
        print(f"\nCOMPARAISON DU DRAFT :")
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
            print(
                f"  Votre équipe : {ally_total:+.2f}% d'avantage total → {ally_team_winrate:.2f}% de winrate d'équipe"
            )
        else:
            ally_team_winrate = 50.0
            ally_total = 0
            print(f"  Votre équipe : Aucune donnée valide")

        if enemy_valid_scores:
            # Convert advantages to individual winrates
            enemy_winrates = [50.0 + advantage for advantage in enemy_valid_scores]
            # Use geometric mean for team strength calculation
            enemy_team_stats = self.assistant._calculate_team_winrate(enemy_winrates)
            enemy_team_winrate = enemy_team_stats["team_winrate"]
            enemy_total = sum(enemy_valid_scores)  # For display purposes
            print(
                f"  Équipe ennemie : {enemy_total:+.2f}% d'avantage total → {enemy_team_winrate:.2f}% de winrate d'équipe"
            )
        else:
            enemy_team_winrate = 50.0
            enemy_total = 0
            print(f"  Équipe ennemie : Aucune donnée valide")

        # Normalize team winrates to ensure they sum to 100%
        if ally_team_winrate != 50.0 or enemy_team_winrate != 50.0:
            total_winrate = ally_team_winrate + enemy_team_winrate
            our_expected = (ally_team_winrate / total_winrate) * 100.0
            their_expected = (enemy_team_winrate / total_winrate) * 100.0

            print(f"\n  Matchup attendu (normalisé) : {our_expected:.2f}% vs {their_expected:.2f}%")

            # Overall assessment based on normalized winrates
            draft_diff = our_expected - their_expected
        else:
            # No valid data - neutral matchup
            our_expected = 50.0
            their_expected = 50.0
            draft_diff = 0.0

        # SPEC-05 B7 §8: best-effort prediction logging for later calibration
        # (scripts/calibrate_model.py). Never blocks nor slows down the draft.
        try:
            self._last_prediction_id = self.assistant.db.insert_prediction(
                ally_champions=ally_picks,
                enemy_champions=enemy_picks,
                ally_lanes=ally_lanes,
                predicted_probability=our_expected / 100.0,
                model_version=analysis_config.MODEL_VERSION,
            )
        except Exception as e:
            print(f"[WARNING] Échec de l'enregistrement de la prédiction: {e}")

        if draft_diff >= 5.0:
            print(f"  Évaluation : Avantage de draft majeur ({draft_diff:+.2f}% d'écart total)")
        elif draft_diff >= 2.5:
            print(f"  Évaluation : Bon avantage de draft ({draft_diff:+.2f}% d'écart total)")
        elif draft_diff >= -2.5:
            print(f"  Évaluation : Draft équilibré ({draft_diff:+.2f}% de différence)")
        elif draft_diff >= -5.0:
            print(f"  Évaluation : Désavantage de draft ({draft_diff:.2f}% de retard)")
        else:
            print(f"  Évaluation : Désavantage de draft majeur ({draft_diff:.2f}% de retard)")

        print("\n" + "=" * 80)

    def cleanup(self):
        """Clean up resources."""
        # Close the recycled OneTricks window so it doesn't outlive the monitor.
        self._close_onetricks_window()
        if self.lcu:
            self.lcu.disconnect()
        if self.assistant:
            # Clear cache to free memory
            self.assistant.clear_cache()
            self.assistant.close()
        print("[PICK] Nettoyage terminé")


def main():
    """Main entry point for draft monitoring."""
    monitor = DraftMonitor()
    monitor.start_monitoring()


if __name__ == "__main__":
    main()
