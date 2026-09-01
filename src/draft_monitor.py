import time
import json
import subprocess
import os
import queue
import threading
from typing import Dict, List, Optional, Set
from .lcu_client import LCUClient
from .assistant import Assistant
from .utils.display import safe_print
from .utils.console import clear_console
from .constants import TOP_SOLOQ_POOL, CHAMPIONS_BY_ROLE
from .config_constants import draft_config
from .draft.state import ChampionAction, DraftState
from .draft import phases
from .draft import display
from .draft.memory_diagnostics import log_memory_usage
from .draft.scoring import DraftScorer
from .draft.state_parser import DraftStateParser
from .draft.onetricks import OneTricksWindow
from .draft.automation import HoverAutomation
from .draft.pool_selection import PoolSelector
from .draft.ban_advice import BanAdvisor
from .draft.commands import CommandListener
from .draft.recommendations import DraftRecommender
from .draft.final_analysis import FinalDraftAnalyzer
from .draft.lifecycle import MonitorLifecycle


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
        self.scorer = DraftScorer(
            self.assistant, self._get_display_name, self.synergy_weight, verbose=verbose
        )
        self.state_parser = DraftStateParser(self.lcu, self._get_display_name, verbose=verbose)
        self.onetricks = OneTricksWindow(self)
        self.hover = HoverAutomation(self)
        self.pool_selector = PoolSelector(self)
        self.ban_advisor = BanAdvisor(self)
        self.commands = CommandListener(self)
        self.recommender = DraftRecommender(self)
        self.final_analyzer = FinalDraftAnalyzer(self)
        self.lifecycle = MonitorLifecycle(self)
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
        """Return the dedicated, reused Brave profile dir for the OneTricks window."""
        return self.onetricks.profile_dir()

    def _close_onetricks_window(self) -> None:
        """Terminate the previously opened OneTricks window, if any."""
        self.onetricks.close_window()

    def _open_champion_page_on_onetricks(self):
        """Open the player's champion page on OneTriks.gg, recycling a single window."""
        self.onetricks.open_champion_page()

    def stop_monitoring(self):
        """Stop monitoring."""
        self.is_monitoring = False

    def _log_memory_usage(self, force: bool = False) -> None:
        """Record the process RSS to logs/draft_monitor_memory.log periodically."""
        log_memory_usage(self._loop_count, self._onetricks_proc, force=force)

    def _monitor_loop(self):
        """Main monitoring loop."""
        self.lifecycle.monitor_loop()

    def _handle_ready_check(self):
        """Handle ready check (queue found) and auto-accept if enabled."""
        self.lifecycle.handle_ready_check()

    def _handle_auto_ban_hover(self, state: DraftState):
        """Handle auto-ban-hover when it's our turn to ban."""
        self.ban_advisor.handle_auto_ban_hover(state)

    def _is_draft_complete(self, state: DraftState) -> bool:
        """Check if the draft is complete (all 10 champions locked)."""
        return phases.is_draft_complete(state)

    def _analyze_complete_draft(self, state: DraftState):
        """Analyze the complete draft immediately when all champions are locked."""
        self.lifecycle.analyze_complete_draft(state)

    def _reset_for_next_game(self):
        """Reset state for the next game."""
        self.lifecycle.reset_for_next_game()

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
        """Background stdin reader for role corrections (SPEC-04 B5)."""
        self.commands.start()

    def _apply_pending_commands(self, state: DraftState) -> bool:
        """Drain queued commands: role corrections (SPEC-04 B5) and manual
        outcome logging (SPEC-05 B7 §9)."""
        return self.commands.apply_pending(state)

    def _handle_correction_command(self, line: str, state: DraftState) -> bool:
        """Parse and apply one 'r <champion> <lane>' correction command."""
        return self.commands.handle_correction_command(line, state)

    def _handle_outcome_command(self, line: str) -> None:
        """Parse and apply one 'outcome win'/'outcome loss' command (SPEC-05 B7 §9)."""
        self.commands.handle_outcome_command(line)

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
        """Calculate score against enemy team using Assistant's method."""
        return self.scorer.calculate_score_against_team(
            matchups,
            enemy_team,
            champion_name,
            banned_champion_ids,
            lane=lane,
            enemy_lanes=enemy_lanes,
            player_lane=player_lane,
        )

    def _calculate_synergy_score(
        self, champion_name: str, ally_team: List[int], lane: Optional[str] = None
    ) -> float:
        """Calculate synergy score as sum of delta2 with allied champions."""
        return self.scorer.calculate_synergy_score(champion_name, ally_team, lane=lane)

    def _final_score(self, matchup_score: float, synergy_score: float) -> float:
        """Blend matchup and synergy scores using the configurable synergy weight."""
        return self.scorer.final_score(matchup_score, synergy_score)

    def _parse_draft_state(self, champ_select_data: Dict) -> DraftState:
        """Parse champion select data into DraftState."""
        state, player_champion = self.state_parser.parse(
            champ_select_data, self.forced_roles, self.lane_distributions
        )
        if player_champion is not None:
            self.player_champion = player_champion
        return state

    def _has_draft_changed(self, current_state: DraftState) -> bool:
        """Check if draft state has changed significantly."""
        return phases.has_draft_changed(current_state, self.last_draft_state)

    def _handle_draft_change(self, state: DraftState):
        """Handle draft state change and provide recommendations."""
        self.lifecycle.handle_draft_change(state)

    def _format_role_tag(self, champion_id: int, state: DraftState) -> str:
        """Role annotation for one champion in the draft display (SPEC-04 B5)."""
        return display.format_role_tag(champion_id, state)

    def _display_draft_state(self, state: DraftState):
        """Display current draft state in terminal."""
        display.display_draft_state(state, self._get_display_name, self._should_show_bans)

    def _provide_recommendations(self, state: DraftState):
        """Provide coaching recommendations based on current draft."""
        self.recommender.provide(state)

    def _is_player_turn(self, state: DraftState) -> bool:
        """Check if it's the local player's turn to pick."""
        return phases.is_player_turn(state)

    def _is_player_ban_turn(self, state: DraftState) -> bool:
        """Check if it's the local player's turn to ban."""
        return phases.is_player_ban_turn(state, self.verbose)

    def _enemy_picks_changed(self, state: DraftState) -> bool:
        """Check if enemy team composition has changed."""
        return phases.enemy_picks_changed(state, self.last_draft_state)

    def _is_ban_phase(self, state: DraftState) -> bool:
        """
        Check if we are currently in an active ban phase.

        This method checks multiple conditions:
        1. We have 0 picks (ban phase is before any picks)
        2. We haven't reached the maximum number of bans yet

        Returns:
            True if currently in an active ban phase, False otherwise
        """
        return phases.is_ban_phase(state, self.verbose)

    def _should_show_bans(self, state: DraftState) -> bool:
        """
        Determine if bans should be displayed based on the current draft phase.

        Ban phase is considered active until enemy bans are revealed.
        Once enemy bans appear, we know ban phase is complete.

        Returns:
            True if bans should be shown, False otherwise
        """
        return phases.should_show_bans(state)

    def _auto_hover_champion(self, champion_name: str, reason: str = ""):
        """Automatically hover the recommended champion."""
        self.hover.auto_hover_champion(champion_name, reason)

    def _do_initial_hover(self):
        """Do initial hover with the best champion from the pool when entering champion select."""
        self.hover.do_initial_hover()

    def _get_best_champion_from_pool(self) -> str:
        """Get the best champion from current pool using tier list analysis."""
        return self.hover.get_best_champion_from_pool()

    def _show_ban_recommendations_draft(self):
        """Show ban recommendations for current pool during draft."""
        self.ban_advisor.show_ban_recommendations_draft()

    def _show_adaptive_ban_recommendations(self, state: DraftState):
        """Show ban recommendations adapted to enemy picks."""
        self.ban_advisor.show_adaptive_ban_recommendations(state)

    def _select_champion_pool_by_name(self, pool_name: str) -> List[str]:
        """Charge une pool mémorisée par son nom, sans re-poser la question.

        Retombe sur la sélection interactive si la pool a été supprimée ou
        renommée depuis la dernière session (SPEC-06 D2).
        """
        return self.pool_selector.select_by_name(pool_name)

    def _select_champion_pool_interactive(self) -> List[str]:
        """Interactive pool selection with custom pools support."""
        return self.pool_selector.select_interactive()

    def _calculate_final_scores(
        self,
        ally_picks: List[int],
        enemy_picks: List[int],
        ally_lanes: Optional[Dict[int, str]] = None,
    ):
        """Calculate individual scores for each champion at end of draft."""
        self.final_analyzer.analyze(ally_picks, enemy_picks, ally_lanes)

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
