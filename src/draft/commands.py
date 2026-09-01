"""Background stdin command listener (manual role corrections + outcome logging).

Extracted from src/draft_monitor.py (SPEC-07 E10, lot 10) : déplacement
verbatim, aucun changement de comportement.

Back-reference to the monitor: the listener thread's loop condition
(``while self.m.is_monitoring``) must observe the monitor's live flag, not a
copy captured at construction time — otherwise the thread would never start
if ``is_monitoring`` was still False when this component was built (R6).
``_command_queue``/``_command_listener_thread`` stay attributes on the
monitor itself (tests read/write them directly on the instance).
"""

import queue
import threading

from ..config_constants import scraping_config
from .state import DraftState


class CommandListener:
    """Drain manual `r <champion> <lane>` and `outcome win|loss` commands."""

    def __init__(self, monitor) -> None:
        self.m = monitor

    def start(self) -> None:
        """Background stdin reader for role corrections (SPEC-04 B5).

        A daemon thread blocking on input() so the poll loop never blocks on
        the terminal; apply_pending() drains the queue from the main thread
        every tick, keeping LCU/db access single-threaded.
        """
        if self.m._command_listener_thread is not None:
            return

        def _listen() -> None:
            while self.m.is_monitoring:
                try:
                    line = input()
                except (EOFError, RuntimeError):
                    return
                if line.strip():
                    self.m._command_queue.put(line)

        self.m._command_listener_thread = threading.Thread(target=_listen, daemon=True)
        self.m._command_listener_thread.start()

    def apply_pending(self, state: DraftState) -> bool:
        """Drain queued commands: role corrections (SPEC-04 B5) and manual
        outcome logging (SPEC-05 B7 §9).

        Returns True if at least one command was applied, so the caller can
        force a redisplay even when the draft itself hasn't changed.
        """
        applied = False
        while True:
            try:
                line = self.m._command_queue.get_nowait()
            except queue.Empty:
                break
            stripped = line.strip()
            if stripped.lower().startswith("outcome"):
                # Never affects the draft display, so it doesn't set `applied`.
                self.handle_outcome_command(stripped)
                continue
            if self.handle_correction_command(line, state):
                applied = True
        return applied

    def handle_correction_command(self, line: str, state: DraftState) -> bool:
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

        name_to_id = {
            name.lower(): champ_id for champ_id, name in self.m.champion_id_to_name.items()
        }
        champion_id = name_to_id.get(champion_input.lower())
        if champion_id is None:
            print(f"[ROLE] Champion inconnu : '{champion_input}'")
            return False

        if champion_id not in state.ally_picks and champion_id not in state.enemy_picks:
            print(f"[ROLE] {champion_input} n'est pas dans le draft en cours")
            return False

        self.m.forced_roles[champion_id] = lane
        state.inferred_roles[champion_id] = lane
        state.role_confidence[champion_id] = 1.0
        state.role_source[champion_id] = "user"
        print(f"[ROLE] {self.m._get_display_name(champion_id)} forcé sur {lane}")
        return True

    def handle_outcome_command(self, line: str) -> None:
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

        if self.m._last_prediction_id is None:
            print("[OUTCOME] Aucune prédiction à mettre à jour pour cette partie")
            return

        outcome = 1 if parts[1].lower() == "win" else 0
        try:
            updated = self.m.assistant.db.update_prediction_outcome(
                self.m._last_prediction_id, outcome
            )
            if updated:
                print(
                    f"[OUTCOME] Prédiction #{self.m._last_prediction_id} enregistrée comme {parts[1].lower()}"
                )
            else:
                print(
                    f"[OUTCOME] Aucune prédiction trouvée pour l'id #{self.m._last_prediction_id}"
                )
        except Exception as e:
            print(f"[WARNING] Échec de la mise à jour du résultat de la prédiction: {e}")

        # One outcome update per game, whether it succeeded or not.
        self.m._last_prediction_id = None
