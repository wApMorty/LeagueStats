"""Champion recommendations during pick/ban phases.

SPEC-12 : le classement ne vient plus d'un score par delta calculé sur la
draft telle qu'elle est, mais de ``src/draft/search.py`` — on déroule la fin de
la draft en supposant que les deux camps jouent au mieux, et on affiche la
probabilité de victoire de la position obtenue. Un pick qui ouvre un
contre-pick évident n'est donc plus recommandé en aveugle.

Back-reference to the monitor: touches ~9 different domains (verbose,
current_pool, champion_id_to_name, assistant, search, auto_hover,
auto_ban_hover, last_recommendation — written, last_draft_state) and calls back
through the monitor's own facades (_is_ban_phase,
_show_adaptive_ban_recommendations, _get_display_name, _is_player_turn,
_enemy_picks_changed, _auto_hover_champion, _handle_auto_ban_hover) because
tests/test_draft_monitor_recommendations.py patches some of these directly on
the monitor instance and counts calls — they must be invoked via
self.m.<method>, not sibling methods here.
"""

from typing import List, Optional, Sequence, Tuple

from ..analysis.game_eval import Placed
from ..config_constants import draft_config, ui_config
from ..utils.display import format_games_count
from .search import PickTurn, SearchResult
from .state import DraftState


class DraftRecommender:
    """Compute and print champion pick recommendations for the current draft."""

    def __init__(self, monitor) -> None:
        self.m = monitor

    # ---------- préparation de la position ----------

    def _placed(self, champion_ids: Sequence[int], state: DraftState) -> List[Placed]:
        """championIds -> (nom, lane inférée) pour l'évaluateur."""
        return [
            (self.m._get_display_name(champ_id), state.inferred_roles.get(champ_id))
            for champ_id in champion_ids
        ]

    def _turns_from_our_next_pick(self, state: DraftState) -> List[PickTurn]:
        """Les tours à partir du nôtre, notre tour en tête.

        ponytail: les tours qui PRÉCÈDENT le nôtre (un allié ou un ennemi qui
        pick avant nous) sont simplement retirés, et leurs slots comptent pour
        0 comme tout slot non atteint. Exact quand c'est effectivement notre
        tour — le seul moment où l'on agit sur la recommandation ; approximatif
        quand le coach affiche un classement par anticipation. Les intégrer
        demanderait de chaîner la racine sur un nœud adverse, donc de perdre la
        valeur exacte par candidat qu'on affiche.
        """
        for index, turn in enumerate(state.remaining_picks):
            if turn.is_local_player:
                return list(state.remaining_picks[index:])
        return []

    def _split_pool(
        self, state: DraftState, player_lane: Optional[str]
    ) -> Tuple[List[str], List[Tuple[str, int]], dict]:
        """Sépare le pool en champions exploitables et champions sans données.

        SPEC-09 E1 : un champion sans données pour cette lane n'est pas « un
        mauvais pick », il est inconnu — la recherche le noterait à 50 % comme
        un matchup réellement neutre. Il est donc écarté du classement et
        affiché à part.
        """
        playable: List[str] = []
        skipped: List[Tuple[str, int]] = []
        games_by_champion: dict = {}

        for champion_name in self.m.current_pool:
            matchups = self.m.assistant.get_matchups_for_draft(champion_name, lane=player_lane)
            total_games = sum(m.games for m in matchups) if matchups else 0
            if matchups and total_games >= draft_config.MIN_CHAMPION_GAMES:
                playable.append(champion_name)
                games_by_champion[champion_name] = total_games
            else:
                skipped.append((champion_name, total_games))

        return playable, skipped, games_by_champion

    # ---------- affichage ----------

    @staticmethod
    def _format_variation(result: SearchResult) -> str:
        """La suite supposée optimale, façon variante principale d'un moteur."""
        if not result.principal_variation:
            return ""
        moves = ", ".join(
            f"{name}{f' ({lane})' if lane else ''}" for name, lane in result.principal_variation
        )
        return f" → suite attendue : {moves}"

    def _print_results(
        self,
        results: Sequence[SearchResult],
        games_by_champion: dict,
        player_lane: Optional[str],
        direct_counter_name: Optional[str],
    ) -> Optional[str]:
        """Affiche le classement, renvoie le nom du meilleur pick."""
        top_recommendation = None
        display_count = min(ui_config.MAX_RECOMMENDATIONS, len(results))

        for i in range(display_count):
            result = results[i]
            rank = "[1st]" if i == 0 else "[2nd]" if i == 1 else "[3rd]"

            lane_tag = ""
            if player_lane:
                lane_tag = f" ({player_lane}"
                if direct_counter_name:
                    lane_tag += f" vs {direct_counter_name}"
                lane_tag += ")"

            games = games_by_champion.get(result.champion)
            volume_tag = f" · {format_games_count(games)} games" if games else ""

            print(
                f"  {rank} {result.champion}{lane_tag} "
                f"{result.win_probability * 100:.2f}% de victoire"
                f"{volume_tag}{self._format_variation(result)}"
            )

            if i == 0:
                top_recommendation = result.champion

        if results:
            print(f"  [SEARCH] Profondeur atteinte : {results[0].depth} pick(s) anticipé(s)")
        return top_recommendation

    # ---------- entrée principale ----------

    def provide(self, state: DraftState) -> None:
        """Provide coaching recommendations based on current draft."""
        try:
            enemy_picks = state.enemy_picks
            ally_picks = state.ally_picks

            if self.m.verbose:
                print(
                    f"[DEBUG] _provide_recommendations called: Phase='{state.phase}', "
                    f"Enemies={len(enemy_picks)}, Allies={len(ally_picks)}"
                )

            # Skip recommendations if draft hasn't started yet (bans already shown in initial hover)
            if not enemy_picks and not ally_picks:
                if self.m.verbose:
                    print(f"[DEBUG] Waiting for picks to start (bans already shown at start)")
                return

            if enemy_picks:
                print(f"\n[PICKS] RECOMMANDATIONS DE COUNTERPICK :")
                print("-" * 50)

                # Show adaptive ban recommendations only during actual ban phases
                if self.m._is_ban_phase(state) and len(enemy_picks) >= 1:
                    self.m._show_adaptive_ban_recommendations(state)

                # SPEC-04 B4 §4.3 : notre lane (LCU) et celles inférées côté
                # ennemi, qui pondèrent les paires dans l'évaluateur.
                player_lane = state.ally_positions.get(state.local_player_cell_id)
                allies = self._placed(ally_picks, state)
                enemies = self._placed(enemy_picks, state)
                banned = [
                    self.m._get_display_name(ban_id)
                    for ban_id in state.ally_bans + state.enemy_bans
                ]

                # SPEC-04 B5 : l'ennemi qui partage notre lane, affiché « vs X ».
                direct_counter_name = next(
                    (name for name, lane in enemies if lane and lane == player_lane), None
                )

                if self.m.verbose and banned:
                    print(f"[DEBUG] Bans: {banned}")

                playable, skipped, games_by_champion = self._split_pool(state, player_lane)
                turns = self._turns_from_our_next_pick(state)

                results: List[SearchResult] = []
                if playable and turns:
                    results = self.m.search.rank(
                        allies=allies,
                        enemies=enemies,
                        pool=playable,
                        remaining_turns=turns,
                        banned=banned,
                        player_lane=player_lane,
                    )

                top_recommendation = self._print_results(
                    results, games_by_champion, player_lane, direct_counter_name
                )

                # Auto-hover top recommendation if enabled
                if (
                    self.m.auto_hover
                    and top_recommendation
                    and top_recommendation != self.m.last_recommendation
                ):
                    is_our_turn = self.m._is_player_turn(state)
                    enemy_changed = self.m._enemy_picks_changed(state)

                    if is_our_turn or enemy_changed:
                        reason = (
                            "À vous de jouer" if is_our_turn else "Mise à jour d'un pick ennemi"
                        )
                        self.m._auto_hover_champion(top_recommendation, reason)
                        self.m.last_recommendation = top_recommendation

                # « Plus de tour » passe avant « pas de données » : c'est
                # l'explication la plus spécifique de la liste vide.
                if not results and not turns:
                    print("  [DATA] Plus aucun pick à jouer de votre côté")
                elif not results and not skipped:
                    print("  [DATA] Aucune donnée disponible pour les matchups actuels")

                # SPEC-09 E1: écartés affichés à part, jamais mêlés au
                # classement (ils ne sont pas classables faute de données).
                if skipped:
                    skipped_names = ", ".join(
                        f"{name} ({format_games_count(games)} games)" for name, games in skipped
                    )
                    lane_suffix = f" en {player_lane}" if player_lane else ""
                    print(f"  [DATA] Sans données exploitables{lane_suffix} : {skipped_names}")

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
