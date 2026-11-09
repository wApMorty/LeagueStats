"""Champion recommendations during pick/ban phases.

SPEC-12 : le classement vient de ``src/draft/search.py``. Une stratégie à
anticipation y ajoute la réponse du vis-à-vis non vu (SPEC-48) : un pick qui
ouvre un contre-pick évident n'est plus recommandé en aveugle.

Back-reference to the monitor: touches ~9 different domains (verbose,
current_pool, champion_id_to_name, assistant, search, auto_hover,
auto_ban_hover, last_recommendation — written, last_draft_state) and calls back
through the monitor's own facades (_is_ban_phase,
_get_display_name, _is_player_turn,
_enemy_picks_changed, _auto_hover_champion, _handle_auto_ban_hover) because
tests/test_draft_monitor_recommendations.py patches some of these directly on
the monitor instance and counts calls — they must be invoked via
self.m.<method>, not sibling methods here.
"""

from dataclasses import asdict, replace
from typing import Dict, List, Optional, Sequence, Tuple

from ..analysis.game_eval import Placed
from ..analysis.mastery import term_of, to_win_points, with_term
from ..analysis.pick_order import PICK_ORDER_META_KEY, Pick, from_meta
from ..analysis.exposure import d_scores
from ..analysis.strategy import Strategy, WeightedEvaluator, strategy_of
from ..config_constants import draft_config, ui_config
from ..utils.display import format_games_count
from .search import PickTurn, SearchResult
from .pick_advice import pick_advice as advise_pick, request_effect
from .snapshot import TOPIC, Analysis, SnapshotPickAdvice, SnapshotSwapAdvice, build_snapshot
from .state import DraftState
from .swap_advice import has_open_swap, role_swaps


class DraftRecommender:
    """Compute and print champion pick recommendations for the current draft."""

    def __init__(self, monitor) -> None:
        self.m = monitor
        self._last_analysis: Optional[Analysis] = None
        self._last_key = None
        self._swap_key = None
        self._swap_cache: List[SnapshotSwapAdvice] = []
        self._pick_line: Optional[List[Pick]] = None  # séquence lue une fois par champ select
        self._pick_said: Optional[tuple] = None  # dernier conseil écrit dans la console

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
    def _format_reply(result: SearchResult) -> str:
        """La réponse attendue du vis-à-vis (SPEC-48), vide sans anticipation."""
        if not result.reply:
            return ""
        name, lane = result.reply
        return f" → réponse attendue : {name}{f' ({lane})' if lane else ''}"

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
            personal_tag = ""
            if result.personal_points:
                played = term_of(self.m).games(result.champion)
                personal_tag = f" · toi {result.personal_points:+.1f} pts ({played} parties)"

            print(
                f"  {rank} {result.champion}{lane_tag} "
                f"{result.win_probability * 100:.2f}% de victoire"
                f"{volume_tag}{personal_tag}{self._format_reply(result)}"
            )

            if i == 0:
                top_recommendation = result.champion

        return top_recommendation

    # ---------- entrée principale ----------

    def _advice(self, state: DraftState) -> Optional[str]:
        """Conseil propre à la phase (selon l'état réel de la draft)."""
        if state.phase == "PLANNING":
            return "[PLAN] Réfléchissez à la composition d'équipe et aux priorités de ban"
        if state.phase == "BAN_PICK":
            # BAN_PICK phase includes both bans and picks - detect which we're in
            if self.m._is_ban_phase(state):
                return "[BAN] Concentrez-vous sur les bans des forces adverses"
            return "[PICK] C'est le moment de sécuriser votre champion !"
        if state.phase == "PICK":
            return "[PICK] C'est le moment de sécuriser votre champion !"
        if state.phase == "FINALIZATION":
            return "[FINAL] Finalisez runes et sorts d'invocateur"
        return None

    def provide(self, state: DraftState) -> None:
        """Provide coaching recommendations based on current draft.

        Le calcul remplit une `Analysis`, imprimée comme avant puis reprise dans le snapshot que le
        client dessine (SPEC-21 tâche 72).
        """
        analysis = Analysis()
        try:
            self._provide(state, analysis)
        except Exception as e:
            print(f"[WARNING] Erreur lors de la génération des recommandations: {e}")
        if getattr(self.m, "bus", None) is None:
            return  # mode console : rien ne change, aucun calcul de plus
        self._fill_candidates(state, analysis)
        self._publish(state, analysis)

    def _fill_candidates(self, state: DraftState, analysis: Analysis) -> None:
        """Victoire prédite si je prenais chacun des champions encore libres, sur ma lane (grimoire)."""
        try:
            lane = state.ally_positions.get(state.local_player_cell_id)
            mine = next(
                (c for c in state.ally_cells if c.cell_id == state.local_player_cell_id), None
            )
            if not lane or (mine is not None and mine.champion_id) or self.m._is_ban_phase(state):
                return
            allies = self._placed(state.ally_picks, state)
            enemies = self._placed(state.enemy_picks, state)
            taken = set(state.get_all_actions())
            term = term_of(self.m)  # SPEC-41 : ma maîtrise du champion, sur mon pick
            for champion_id, name in self.m.champion_id_to_name.items():
                if champion_id not in taken:
                    analysis.candidates[champion_id] = with_term(
                        self.m.evaluator.win_probability(allies + [(name, lane)], enemies),
                        term.logit(name),
                    )
        except Exception:  # pylint: disable=broad-exception-caught
            analysis.candidates.clear()

    @staticmethod
    def _signature(state: DraftState) -> tuple:
        """Ce que le client dessine et que la liste des picks ne dit pas : survols, tour, bans."""
        cells = [
            (c.cell_id, c.champion_id, c.hover_id, c.skin_id)
            for c in state.ally_cells + state.enemy_cells
        ]
        return (
            state.phase,
            state.current_actor,
            tuple(sorted(state.acting_cells)),
            state.local_player_cell_id,  # un échange d'ordre accepté change ma cellule
            tuple((s.kind, s.cell_id, s.state) for s in state.swaps),
            tuple(cells),
            tuple(state.ally_bans),
            tuple(state.enemy_bans),
            state.my_ban_id,
            state.my_ban_hover_id,
        )

    def _key(self, state: DraftState) -> tuple:
        """La signature de la draft et la build écrite : l'import du lock-in arrive après la publication
        du tick, c'est le tick suivant qui doit republier le snapshot qui la porte."""
        return (self._signature(state), self.m.loadout.state(), strategy_of(self.m).name)

    def clear(self) -> None:
        """Fin du champ select : l'écran de draft repasse à l'état vide (publie `None` une seule fois)."""
        self._pick_line = self._pick_said = None  # la séquence se relit à la draft suivante
        try:
            if self._last_key is None:
                return
            self._last_analysis = self._last_key = None
            self.m.last_snapshot = None
            if getattr(self.m, "bus", None) is not None:
                self.m.bus.publish(TOPIC, None)
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    def refresh(self, state: DraftState) -> None:
        """Republie le dernier classement avec l'état à jour quand un survol ou un tour a changé.

        Appelé à chaque tick où la draft n'a pas changé (la console, elle, ne se redessine pas).
        """
        try:
            if getattr(self.m, "bus", None) is None or self._last_analysis is None:
                return
            if self._key(state) != self._last_key:
                self._publish(state, self._last_analysis)
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    def _publish(self, state: DraftState, analysis: Analysis) -> None:
        """Snapshot du tick sur le bus, s'il y en a un. Best-effort : jamais d'exception."""
        try:
            self._last_analysis, self._last_key = analysis, self._key(state)
            if analysis.base_probability is None:  # phase de bans, ou aucun ennemi
                analysis.base_probability = self._base_probability(
                    self._placed(state.ally_picks, state), self._placed(state.enemy_picks, state)
                )
            snapshot = build_snapshot(
                self.m,
                state,
                analysis,
                self._advice(state),
                self._swap_advice(state),
                self._pick_advice(state),
            )
            self.m.last_snapshot = snapshot
            bus = getattr(self.m, "bus", None)
            if bus is not None:
                bus.publish(TOPIC, asdict(snapshot))
        except Exception as e:  # pylint: disable=broad-exception-caught
            if self.m.verbose is True:
                print(f"[WARNING] Snapshot du draft non publié: {e}")

    def _pick_advice(self, state: DraftState) -> Optional[SnapshotPickAdvice]:
        """Place de pick conseillée (SPEC-53), tant que la session liste des échanges d'ordre et que
        mon pick reste à jouer. La séquence vient de `db_meta`, écrite à la mise à jour des données.

        Best-effort : une panne ne coûte que le conseil, jamais le snapshot ni la boucle.
        """
        try:
            if not any(swap.kind == "pick_order" for swap in state.swaps):
                return None
            if not any(turn.is_local_player for turn in state.remaining_picks):
                return None
            if self._pick_line is None:
                self._pick_line = from_meta(self.m.assistant.db.get_meta(PICK_ORDER_META_KEY))
            ally_cells = {cell.cell_id for cell in state.ally_cells}
            ranks = {cell: rank for cell, rank in state.pick_order.items() if cell in ally_cells}
            me = state.local_player_cell_id
            advice = advise_pick(
                self._pick_line, state.ally_positions.get(me), me, ranks, state.swaps
            )
            if advice is None:
                return None
            effects = {}
            for swap in state.swaps:
                if swap.kind == "pick_order" and swap.state == "RECEIVED":
                    effect = request_effect(advice, ranks, swap.cell_id)
                    if effect is not None:
                        effects[swap.cell_id] = effect
            said = (advice.target, advice.current, advice.cell_id)
            if said != self._pick_said:
                self._pick_said = said
                print(f"[INFO] Place conseillée : {_pick_line_text(advice)}")
            return SnapshotPickAdvice(**vars(advice), request_effects=effects)
        except Exception:  # pylint: disable=broad-exception-caught
            return None

    def _swap_advice(self, state: DraftState) -> List[SnapshotSwapAdvice]:
        """Conseils d'échange de rôle ; recalculés quand les picks, les lanes ou les échanges changent.

        Best-effort : une panne du conseil ne coûte que le conseil (SPEC-24 tâche 102).
        """
        try:
            if not has_open_swap(state.swaps, "position"):
                self._swap_key = None
                return []
            me = state.local_player_cell_id
            allies = {}
            for cell in state.ally_cells:
                champion_id = cell.champion_id or (cell.hover_id if cell.cell_id == me else 0)
                if champion_id:
                    lane = state.inferred_roles.get(cell.champion_id) or cell.position
                    allies[cell.cell_id] = (self.m._get_display_name(champion_id), lane)
            enemies = self._placed(state.enemy_picks, state)
            key = (
                tuple(sorted(allies.items(), key=lambda item: item[0])),
                tuple(enemies),
                me,
                tuple((s.kind, s.cell_id, s.state) for s in state.swaps),
            )
            if key != self._swap_key:
                self._swap_key = key
                self._swap_cache = role_swaps(self.m.evaluator, allies, enemies, me, state.swaps)
            return self._swap_cache
        except Exception:  # pylint: disable=broad-exception-caught
            return []

    def _calibrated(
        self,
        results: Sequence[SearchResult],
        allies: List[Placed],
        enemies: List[Placed],
        strategy: Strategy,
    ) -> List[SearchResult]:
        """Le classement de la stratégie, chaque candidat avec sa victoire du modèle calibré (SPEC-46).

        `score` garde la valeur qui a classé, `win_probability` devient celle de mon pick et de la
        réponse du vis-à-vis, si la stratégie l'anticipe. À score égal, la victoire départage : un
        terme nul sur tout le pool rendrait sinon le premier du pool. La correction de tirage (ADR-004)
        ne touche que `score`.
        """
        term = term_of(self.m)
        weighted = WeightedEvaluator(self.m.evaluator, strategy)
        ranked = []
        for result in results:
            probability = result.win_probability
            if not strategy.is_calibrated:
                ally_side = list(allies) + [(result.champion, result.lane)]
                enemy_side = list(enemies) + ([result.reply] if result.reply else [])
                probability = with_term(
                    self.m.evaluator.win_probability(ally_side, enemy_side),
                    term.logit(result.champion),
                )
            correction = weighted.draw_correction((result.champion, result.lane), enemies)
            score = with_term(result.win_probability, correction)
            ranked.append(replace(result, win_probability=probability, score=score))
        ranked.sort(key=lambda r: (-r.score, -r.win_probability))
        return ranked

    def _parts(
        self,
        results: Sequence[SearchResult],
        allies: List[Placed],
        enemies: List[Placed],
        strategy: Strategy,
    ) -> Dict[str, Dict[str, float]]:
        """Ce que chaque terme de la stratégie apporte à chaque candidat, en points de victoire."""
        weighted = WeightedEvaluator(self.m.evaluator, strategy)
        return {
            result.champion: {
                name: to_win_points(logit)
                for name, logit in weighted.parts(
                    (result.champion, result.lane), allies, enemies
                ).items()
                if getattr(strategy, name)
            }
            for result in results
        }

    def _exposure_order(
        self,
        results: Sequence[SearchResult],
        allies: List[Placed],
        enemies: List[Placed],
        banned: Sequence[str],
        player_lane: Optional[str],
    ) -> Tuple[List[SearchResult], Optional[Dict[str, Tuple[float, float]]]]:
        """Le classement dans l'ordre de la règle D (SPEC-55), et (connu, exposition) en points.

        Les champions hors de D passent après, dans l'ordre reçu. Sans lane, ou si D échoue,
        l'ordre reçu et None : la console le dit, la draft continue (best-effort).
        """
        if not player_lane:
            print("  [INFO] Arbre : poste inconnu, classement force + duel")
            return list(results), None
        try:
            popularity = self.m.lane_popularity()
            if popularity is None:
                return list(results), None
            scores = d_scores(
                self.m.evaluator,
                player_lane,
                [result.champion for result in results],
                allies,
                enemies,
                banned,
                popularity,
            )
        except Exception as error:  # pylint: disable=broad-exception-caught
            print(f"  [ALERTE] Exposition indisponible ({error})")
            return list(results), None
        rank = {score.champion.casefold(): index for index, score in enumerate(scores)}
        ordered = sorted(
            enumerate(results),
            key=lambda item: (rank.get(item[1].champion.casefold(), len(rank)), item[0]),
        )
        exposure = {
            score.champion: (to_win_points(score.known), to_win_points(score.exposure))
            for score in scores
        }
        if scores:
            self._print_exposure(scores[0].champion, *exposure[scores[0].champion])
        return [result for _, result in ordered], exposure

    @staticmethod
    def _print_exposure(champion: str, known: float, exposure: float) -> None:
        """`[D] Ornn : connu +1,20 pt · exposition -0,85 pt` : le n° 1 de la règle D."""

        def points(value: float) -> str:
            unit = "pt" if abs(round(value, 2)) < 2 else "pts"
            return f"{value:+.2f}".replace(".", ",") + f" {unit}"

        print(f"  [D] {champion} : connu {points(known)} · exposition {points(exposure)}")

    def _base_probability(self, allies: List[Placed], enemies: List[Placed]) -> Optional[float]:
        """Probabilité de victoire de la position actuelle, référence des écarts du classement."""
        try:
            return self.m.evaluator.win_probability(allies, enemies)
        except Exception:  # pylint: disable=broad-exception-caught
            return None

    def _provide(self, state: DraftState, analysis: Analysis) -> None:
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
            strategy = strategy_of(self.m)
            print(f"\n[PICKS] RECOMMANDATIONS DE COUNTERPICK ({strategy.name}) :")
            print("-" * 50)

            # SPEC-04 B4 §4.3 : notre lane (LCU) et celles inférées côté
            # ennemi, qui pondèrent les paires dans l'évaluateur.
            player_lane = state.ally_positions.get(state.local_player_cell_id)
            allies = self._placed(ally_picks, state)
            enemies = self._placed(enemy_picks, state)
            banned = [
                self.m._get_display_name(ban_id) for ban_id in state.ally_bans + state.enemy_bans
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
                    personal=lambda name: strategy.mastery * term_of(self.m).logit(name),
                    anticipate=strategy.search,
                )
                results = self._calibrated(results, allies, enemies, strategy)
                analysis.parts = self._parts(results, allies, enemies, strategy)
                if strategy.tree:
                    results, analysis.exposure = self._exposure_order(
                        results, allies, enemies, banned, player_lane
                    )

            analysis.player_lane = player_lane
            analysis.direct_counter = direct_counter_name
            analysis.results = results
            analysis.games_by_champion = games_by_champion
            analysis.skipped = skipped
            analysis.base_probability = self._base_probability(allies, enemies)

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
                    reason = "À vous de jouer" if is_our_turn else "Mise à jour d'un pick ennemi"
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

        advice = self._advice(state)
        if advice:
            print(f"\n[ADVICE] {advice}")


_SIDES = {"blue": "bleu", "red": "rouge"}


def _pick_line_text(advice) -> str:
    """Le conseil de place en une ligne de console, sans emoji (SPEC-53 §4.3)."""
    head = f"{advice.lane} côté {_SIDES.get(advice.side, advice.side)}, {advice.mode}"
    if advice.current == advice.target:
        return f"{head}, tu es à ta place (n° {advice.target})"
    return f"{head}, vise le n° {advice.target} (tu es n° {advice.current})"
