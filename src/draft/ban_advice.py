"""Ban recommendation display and auto-ban-hover.

Extracted from src/draft_monitor.py (SPEC-07 E10, lot 10) : déplacement
verbatim, aucun changement de comportement.

Back-reference to the monitor: reads pool_name/current_pool/assistant/
verbose, writes last_ban_recommendation, and calls back into the monitor's
own facades (_is_player_ban_turn, _auto_hover_champion, _get_display_name)
because several tests replace those facades directly on the monitor
instance (``draft_monitor._is_player_ban_turn = Mock(...)``) and expect
this code to observe the replacement.

The three "pre-calculated bans in DB, else real-time" blocks below are
near-identical on purpose: they differ in their verbose logging branches,
and factoring them would be a behavior change, not a pure move (dette
signalée dans le plan d'extraction, hors périmètre de ce lot).

Dette SPEC-10 corrigée : handle_auto_ban_hover et show_adaptive_ban_recommendations
filtrent désormais les champions déjà bannis/pickés (camp allié ou ennemi) --
côté source pour le calcul temps réel (exclude_champions, porté par
BanRecommender), côté consommateur pour les bans précalculés en base (qui ne
peuvent pas connaître l'état live). show_ban_recommendations_draft n'a pas
cette dette : son unique appel se fait avant le début du draft (hover initial),
quand rien n'est encore banni ni pické.
"""

import sys

from .state import DraftState


class BanAdvisor:
    """Ban recommendations: auto-hover during the ban phase, and display."""

    def __init__(self, monitor) -> None:
        self.m = monitor

    def _unavailable_champions(self, state: DraftState) -> list:
        """Champions déjà bannis ou pickés (camp allié ou ennemi) — plus
        candidats valides à un ban. `state.*_picks`/`*_bans` portent des
        champion_id malgré le type hint `List[str]` (voir state_parser.py)."""
        return [self.m._get_display_name(cid) for cid in state.get_all_actions()]

    def handle_auto_ban_hover(self, state: DraftState) -> None:
        """Handle auto-ban-hover when it's our turn to ban."""
        if getattr(sys, "frozen", False):
            return  # Skip ban hover in .exe mode
        try:
            if self.m.verbose:
                print(
                    f"[DEBUG] Auto-ban-hover called: Phase='{state.phase}', Actor={state.current_actor}, Local={state.local_player_cell_id}"
                )

            # Only act if it's our turn to ban
            if not self.m._is_player_ban_turn(state):
                if self.m.verbose:
                    print(f"[DEBUG] Not player ban turn - skipping auto-ban-hover")
                return

            if self.m.verbose:
                print(
                    f"[DEBUG] It's our ban turn! Getting recommendations for pool size {len(self.m.current_pool)}"
                )

            unavailable = self._unavailable_champions(state)
            unavailable_lower = {name.lower() for name in unavailable}

            # Try to get pre-calculated bans from database first (fast).
            # Ces bans sont calculés hors contexte de draft (precalculate_pool_bans) :
            # ils ne peuvent pas connaître l'état live, d'où le filtrage ici.
            ban_recommendations = None
            if hasattr(self.m, "pool_name") and self.m.pool_name:
                raw_recommendations = self.m.assistant.db.get_pool_ban_recommendations(
                    self.m.pool_name, limit=3
                )
                if raw_recommendations:
                    ban_recommendations = [
                        r for r in raw_recommendations if r[0].lower() not in unavailable_lower
                    ]
                    if ban_recommendations and self.m.verbose:
                        print(
                            f"[DEBUG] Using pre-calculated bans from database for pool '{self.m.pool_name}'"
                        )

            # Fallback to real-time calculation if no pre-calculated data usable
            if not ban_recommendations:
                if self.m.verbose:
                    print(f"[DEBUG] No pre-calculated bans found, calculating in real-time...")
                ban_recommendations = self.m.assistant.get_ban_recommendations(
                    self.m.current_pool,
                    num_bans=3,
                    lane=getattr(self.m, "pool_lane", None),
                    exclude_champions=unavailable,
                )

            if not ban_recommendations:
                print("[DEBUG] No ban recommendations available")
                return

            if self.m.verbose:
                print(f"[DEBUG] Got {len(ban_recommendations)} ban recommendations")

            # Get the top ban recommendation
            # Tuple format: (enemy, threat_score, best_delta2, best_champ, matchup_count)
            top_ban_data = ban_recommendations[0]
            top_ban = top_ban_data[0]
            threat_score = top_ban_data[1]
            matchup_count = top_ban_data[4] if len(top_ban_data) >= 5 else 0

            if self.m.verbose:
                print(f"[DEBUG] Top ban recommendation: {top_ban} (threat: {threat_score:.2f})")

            # Only hover if it's a different recommendation or first time
            if top_ban != self.m.last_ban_recommendation:
                # Garde-fou final avant l'action : le filtrage ci-dessus couvre le
                # chemin production (BanRecommender.get_ban_recommendations, bans
                # précalculés), mais on ne hover jamais un champion indisponible
                # même si une source amont ne l'a pas filtré.
                if top_ban.lower() in unavailable_lower:
                    print(f"  [ALERTE] [AUTO-BAN-HOVER] {top_ban} déjà banni/pické, ignoré")
                    return

                print(f"[DEBUG] Attempting to hover {top_ban}...")
                if self.m._auto_hover_champion(top_ban, "Recommandation de ban"):
                    print(f"  [AUTO-BAN-HOVER] Survol de {top_ban} (Menace : {threat_score:.2f})")
                    self.m.last_ban_recommendation = top_ban
                else:
                    print(f"  [ALERTE] [AUTO-BAN-HOVER] Échec du survol de {top_ban}")
            else:
                if self.m.verbose:
                    print(f"[DEBUG] Same recommendation as before ({top_ban}), skipping")

        except Exception as e:
            print(f"[WARNING] Error handling auto-ban-hover: {e}")
            import traceback

            traceback.print_exc()

    def show_ban_recommendations_draft(self) -> None:
        """Show ban recommendations for current pool during draft."""
        if getattr(sys, "frozen", False):
            return  # Skip ban recommendations in .exe mode

        try:
            print(f"\n[BANS] RECOMMANDATIONS DE BAN STRATÉGIQUES")
            print("-" * 50)

            # Try to get pre-calculated bans from database first (fast)
            ban_recommendations = None
            if hasattr(self.m, "pool_name") and self.m.pool_name:
                ban_recommendations = self.m.assistant.db.get_pool_ban_recommendations(
                    self.m.pool_name, limit=3
                )
                if ban_recommendations and self.m.verbose:
                    print(
                        f"[DEBUG] Using pre-calculated bans from database for pool '{self.m.pool_name}'"
                    )

            # Fallback to real-time calculation if no pre-calculated data
            if not ban_recommendations:
                if self.m.verbose:
                    print(f"[DEBUG] No pre-calculated bans found, calculating in real-time...")
                ban_recommendations = self.m.assistant.get_ban_recommendations(
                    self.m.current_pool, num_bans=3, lane=getattr(self.m, "pool_lane", None)
                )

            if ban_recommendations:
                print(f"Envisagez de bannir ces menaces pour votre pool :")
                # Tuple format: (enemy, threat_score, best_delta2, best_champ, matchup_count)
                for i, (enemy, threat_score, _best_delta2, _best_champ, matchup_count) in enumerate(
                    ban_recommendations, 1
                ):
                    print(
                        f"  {i}. {enemy:<12} | Menace : {threat_score:>5.2f} | Counter {matchup_count}/{len(self.m.current_pool)} de vos champions"
                    )
                print(f"[INFO] Ces champions ont de bons matchups contre votre pool")
            else:
                if self.m.verbose:
                    print(f"[ALERTE] Aucune donnée de ban disponible pour votre pool")

        except Exception as e:
            if self.m.verbose:
                print(f"[WARNING] Erreur lors de l'affichage des recommandations de ban: {e}")

    def show_adaptive_ban_recommendations(self, state: DraftState) -> None:
        """Show ban recommendations adapted to enemy picks."""
        if getattr(sys, "frozen", False):
            return  # Skip adaptive bans in .exe mode
        try:
            if not state.enemy_picks:
                return

            print(f"\n[ADAPTIVE BANS] RECOMMANDATIONS DE BAN CIBLÉES")
            print("-" * 50)

            # Get enemy champion names
            enemy_names = [self.m._get_display_name(champ_id) for champ_id in state.enemy_picks]
            print(f"L'équipe ennemie a : {', '.join(enemy_names)}")

            unavailable = self._unavailable_champions(state)
            unavailable_lower = {name.lower() for name in unavailable}

            # Try to get pre-calculated bans from database first (fast). Filtrage
            # requis : ces bans sont calculés hors contexte de draft.
            ban_recommendations = None
            if hasattr(self.m, "pool_name") and self.m.pool_name:
                raw_recommendations = self.m.assistant.db.get_pool_ban_recommendations(
                    self.m.pool_name, limit=3
                )
                if raw_recommendations:
                    ban_recommendations = [
                        r for r in raw_recommendations if r[0].lower() not in unavailable_lower
                    ]

            # Fallback to real-time calculation if no pre-calculated data usable
            if not ban_recommendations:
                ban_recommendations = self.m.assistant.get_ban_recommendations(
                    self.m.current_pool,
                    num_bans=3,
                    lane=getattr(self.m, "pool_lane", None),
                    exclude_champions=unavailable,
                )

            if ban_recommendations:
                print(f"Bans prioritaires pour neutraliser les synergies ennemies :")
                for i, (enemy, threat_score, *_) in enumerate(ban_recommendations[:3], 1):
                    print(f"  {i}. {enemy:<12} | Menace : {threat_score:>5.2f}")
                print(f"[INFO] Ciblez les champions qui synergisent avec leurs picks")

        except Exception as e:
            if self.m.verbose:
                print(f"[WARNING] Erreur lors de l'affichage des bans ciblés: {e}")
