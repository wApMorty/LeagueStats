"""Auto-hover automation (champion select blind-pick assist).

Extracted from src/draft_monitor.py (SPEC-07 E10, lot 9) : déplacement
verbatim, aucun changement de comportement.

Back-reference to the monitor: reads lcu/current_pool/champion_id_to_name/
assistant, writes last_recommendation, and calls into the ban-advice domain
(``_show_ban_recommendations_draft``, extracted separately in lot 10) — too
many cross-domain touches for plain composition.
"""

from typing import List, Optional, Tuple

from ..config_constants import draft_config
from ..utils.console import clear_console


class HoverAutomation:
    """Auto-hover the best blind pick from the current pool."""

    def __init__(self, monitor) -> None:
        self.m = monitor

    def auto_hover_champion(self, champion_name: str, reason: str = "") -> None:
        """Automatically hover the recommended champion."""
        try:
            if self.m.lcu.hover_champion(champion_name):
                reason_text = f" ({reason})" if reason else ""
                print(f"  [AUTO-HOVER] {champion_name} survolé{reason_text}")
            else:
                if self.m.verbose:
                    print(f"  [ALERTE] [AUTO-HOVER] Échec du survol de {champion_name}")
        except Exception as e:
            if self.m.verbose:
                print(f"  [ERREUR] [AUTO-HOVER] Erreur lors du survol de {champion_name}: {e}")

    def do_initial_hover(self) -> None:
        """Do initial hover with the best champion from the pool when entering champion select."""
        try:
            # Clear console at start of champion select
            clear_console()

            print(f"\n[INITIAL] Champion select démarré - Préparation de votre stratégie !")
            print("=" * 80)

            # Get best champion from current pool (first champion as fallback)
            if not self.m.current_pool:
                if self.m.verbose:
                    print("  [ALERTE] [INITIAL-HOVER] Aucun champion dans la pool")
                return

            # Calculate best champion from pool using smart analysis
            initial_champion = self.m._get_best_champion_from_pool()

            # Show the recommended blind pick
            print(f"\n[PICK] MEILLEUR BLIND PICK DE VOTRE POOL :")
            print(f"  [OK] {initial_champion}")
            print(f"  [INFO] Si vous êtes premier pick, c'est votre choix le plus sûr !")

            # Auto-hover the champion
            self.m._auto_hover_champion(initial_champion, "Meilleur blind pick")
            self.m.last_recommendation = initial_champion

            # Show ban recommendations immediately
            self.m._show_ban_recommendations_draft()

            print("\n" + "=" * 80)
            print("[INFO] En attente du début du draft...")
            print("=" * 80)

        except Exception as e:
            if self.m.verbose:
                print(f"  [ALERTE] [INITIAL-HOVER] Erreur lors du hover initial: {e}")

    def _resolve_player_lane(self) -> Optional[str]:
        """SPEC-09 E3: lane being played, by order of preference.

        1. ``self.m.pool_lane`` - resolved by ``PoolSelector`` from the
           pool's own role (``pool_manager.pool_role_to_lane()``), already
           set as soon as a mono-role pool is selected, before champion
           select even opens.
        2. ``self.m.last_draft_state.ally_positions`` - the LCU-assigned
           position, once champion select has started.
        3. ``None`` - legitimate in a queue that assigns no roles. Callers
           must NOT silently fall back to scoring the all-lanes aggregate
           instead (SPEC-09 "Hors périmètre": a missing lane is not a
           licence to substitute a misleading one).
        """
        pool_lane = getattr(self.m, "pool_lane", None)
        if pool_lane:
            return pool_lane
        last_state = getattr(self.m, "last_draft_state", None)
        if last_state is not None:
            return last_state.ally_positions.get(last_state.local_player_cell_id)
        return None

    def get_best_champion_from_pool(self) -> str:
        """Get the best champion from current pool using tier list analysis."""
        try:
            # Convert current_pool (names) to champion IDs for scoring
            champion_ids = []
            for champ_name in self.m.current_pool:
                # Find champion ID by name
                for champ_id, name in self.m.champion_id_to_name.items():
                    if name.lower() == champ_name.lower():
                        champion_ids.append(champ_id)
                        break

            if not champion_ids:
                # Fallback to first champion if no IDs found
                return self.m.current_pool[0]

            # SPEC-09 E3: the blind pick was previously scored on the
            # champion's all-lanes aggregate even when the lane was already
            # known (5th residual of the September 2026 lane-filter bug
            # family) - thread the lane through like every other call site.
            player_lane = self._resolve_player_lane()

            # Calculate scores for pool champions (blind pick scenario)
            scores = []
            # SPEC-09 E1: same rule as DraftRecommender.provide() - a
            # champion without exploitable data for this lane is reported,
            # never silently dropped from the pool.
            skipped: List[Tuple[str, int]] = []
            for champion_id in champion_ids:
                champion_name = self.m._get_display_name(champion_id)
                matchups = self.m.assistant.get_matchups_for_draft(champion_name, lane=player_lane)
                total_games = sum(m.games for m in matchups) if matchups else 0
                if matchups and total_games >= draft_config.MIN_CHAMPION_GAMES:
                    # Use blind pick scoring (empty enemy team)
                    score = self.m.assistant.score_against_team(matchups, [], champion_name)
                    scores.append((champion_name, score))
                else:
                    skipped.append((champion_name, total_games))

            if skipped:
                skipped_names = ", ".join(f"{name} ({games} games)" for name, games in skipped)
                lane_suffix = f" en {player_lane}" if player_lane else ""
                print(f"  [DATA] Sans données exploitables{lane_suffix} : {skipped_names}")

            if scores:
                # Sort by score and return best champion
                scores.sort(key=lambda x: x[1], reverse=True)
                best_champion = scores[0][0]
                if self.m.verbose:
                    print(
                        f"  [OK] [INITIAL-HOVER] Meilleur de la pool : {best_champion} ({scores[0][1]:+.2f}% d'avantage)"
                    )
                return best_champion
            else:
                # Fallback to first champion
                return self.m.current_pool[0]

        except Exception as e:
            if self.m.verbose:
                print(f"  [ALERTE] [INITIAL-HOVER] Erreur d'obtention du meilleur champion: {e}")
            return self.m.current_pool[0]  # Fallback
