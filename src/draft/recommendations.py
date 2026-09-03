"""Champion recommendations during pick/ban phases.

Extracted from src/draft_monitor.py (SPEC-07 E10, lot 11) : déplacement
verbatim, aucun changement de comportement.

Back-reference to the monitor: touches ~9 different domains (verbose,
current_pool, champion_id_to_name, assistant, auto_hover, auto_ban_hover,
last_recommendation — written, last_draft_state) and calls back through the
monitor's own facades (_is_ban_phase, _show_adaptive_ban_recommendations,
_get_display_name, _calculate_score_against_team, _calculate_synergy_score,
_final_score, _is_player_turn, _enemy_picks_changed, _auto_hover_champion,
_handle_auto_ban_hover) because tests/test_draft_monitor_recommendations.py
patches two of these directly on the monitor instance and counts calls —
they must be invoked via self.m.<method>, not sibling methods here.
"""

from ..config_constants import draft_config, ui_config
from .state import DraftState


class DraftRecommender:
    """Compute and print champion pick recommendations for the current draft."""

    def __init__(self, monitor) -> None:
        self.m = monitor

    def provide(self, state: DraftState) -> None:
        """Provide coaching recommendations based on current draft."""
        try:
            enemy_picks = state.enemy_picks
            ally_picks = state.ally_picks

            if self.m.verbose:
                print(
                    f"[DEBUG] _provide_recommendations called: Phase='{state.phase}', Enemies={len(enemy_picks)}, Allies={len(ally_picks)}"
                )

            # Skip recommendations if draft hasn't started yet (bans already shown in initial hover)
            if not enemy_picks and not ally_picks:
                if self.m.verbose:
                    print(f"[DEBUG] Waiting for picks to start (bans already shown at start)")
                return

            # Use existing coach logic
            if enemy_picks:
                print(f"\n[PICKS] RECOMMANDATIONS DE COUNTERPICK :")
                print("-" * 50)

                # Show adaptive ban recommendations only during actual ban phases
                if self.m._is_ban_phase(state) and len(enemy_picks) >= 1:
                    self.m._show_adaptive_ban_recommendations(state)

                # Get champion IDs from current pool only
                name_to_id = {
                    name: champ_id for champ_id, name in self.m.champion_id_to_name.items()
                }
                pool_champion_ids = []
                for champ_name in self.m.current_pool:
                    if champ_name in name_to_id:
                        pool_champion_ids.append(name_to_id[champ_name])
                    else:
                        if self.m.verbose:
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
                    self.m._get_display_name(enemy_id): state.inferred_roles[enemy_id]
                    for enemy_id in enemy_picks
                    if enemy_id in state.inferred_roles
                }
                # SPEC-04 B5: the enemy sharing our lane, shown as "vs X" next
                # to each recommendation.
                direct_counter_name = next(
                    (name for name, lane in enemy_lanes.items() if lane == player_lane), None
                )

                # Debug: show current bans
                if self.m.verbose:
                    if state.ally_bans or state.enemy_bans:
                        ally_ban_names = [self.m._get_display_name(bid) for bid in state.ally_bans]
                        enemy_ban_names = [
                            self.m._get_display_name(bid) for bid in state.enemy_bans
                        ]
                        print(f"[DEBUG] Ally bans: {ally_ban_names}")
                        print(f"[DEBUG] Enemy bans: {enemy_ban_names}")

                for champion_id in pool_champion_ids:
                    # Skip if already picked/banned
                    if champion_id in enemy_picks or champion_id in ally_picks:
                        continue
                    if champion_id in state.ally_bans or champion_id in state.enemy_bans:
                        if self.m.verbose:
                            banned_name = self.m._get_display_name(champion_id)
                            print(f"[DEBUG] Skipping banned champion: {banned_name}")
                        continue

                    # Get champion name and matchups (cached for performance).
                    # Lane-filtered when known (SPEC-04 B5): an unfiltered,
                    # all-lanes fetch mixes a multi-lane champion's off-role
                    # sample into the score/volume shown for the lane actually
                    # being played.
                    champion_name = self.m._get_display_name(champion_id)
                    matchups = self.m.assistant.get_matchups_for_draft(
                        champion_name, lane=player_lane
                    )
                    total_games = sum(m.games for m in matchups) if matchups else 0
                    if matchups and total_games >= draft_config.MIN_CHAMPION_GAMES:
                        # Calculate matchup score against enemy team
                        matchup_score = self.m._calculate_score_against_team(
                            matchups,
                            enemy_picks,
                            champion_name,
                            all_banned_ids,
                            lane=player_lane,
                            enemy_lanes=enemy_lanes,
                            player_lane=player_lane,
                        )

                        # Calculate synergy score with allied champions
                        synergy_score = self.m._calculate_synergy_score(
                            champion_name, ally_picks, lane=player_lane
                        )

                        # Final score = configurable blend of matchup and synergy (see _final_score)
                        final_score = self.m._final_score(matchup_score, synergy_score)

                        if self.m.verbose:
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

                # Show top recommendations
                display_count = min(ui_config.MAX_RECOMMENDATIONS, len(scores))
                top_recommendation = None

                for i in range(display_count):
                    champion_id, final_score, matchup_score, synergy_score, games = scores[i]
                    display_name = self.m._get_display_name(champion_id)
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
                    self.m.auto_hover
                    and top_recommendation
                    and top_recommendation != self.m.last_recommendation
                ):
                    # Check if we should update hover (either it's our turn or enemy picked)
                    is_our_turn = self.m._is_player_turn(state)
                    enemy_changed = self.m._enemy_picks_changed(state)

                    if is_our_turn or enemy_changed:
                        reason = (
                            "À vous de jouer" if is_our_turn else "Mise à jour d'un pick ennemi"
                        )
                        self.m._auto_hover_champion(top_recommendation, reason)
                        self.m.last_recommendation = top_recommendation

                if not scores:
                    print("  [DATA] Aucune donnée disponible pour les matchups actuels")

            # Handle auto-ban-hover for ban phases (independent of pick phase)
            if self.m._is_ban_phase(state) and self.m.auto_ban_hover:
                self.m._handle_auto_ban_hover(state)

            # Phase-specific advice (dynamic based on actual game state)
            advice = None
            if state.phase == "PLANNING":
                advice = "[PLAN] Réfléchissez à la composition d'équipe et aux priorités de ban"
            elif state.phase == "BAN_PICK":
                # BAN_PICK phase includes both bans and picks - detect which we're in
                if self.m._is_ban_phase(state):
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
