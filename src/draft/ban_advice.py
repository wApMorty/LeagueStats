"""Ban recommendation display and auto-ban-hover.

Extracted from src/draft_monitor.py (SPEC-07 E10, lot 10).

Back-reference to the monitor: reads pool_name/current_pool/assistant/
verbose, writes last_ban_recommendation, and calls back into the monitor's
own facades (_is_player_ban_turn, _auto_hover_champion, _get_display_name)
because several tests replace those facades directly on the monitor
instance (``draft_monitor._is_player_ban_turn = Mock(...)``) and expect
this code to observe the replacement.

SPEC-18 §4 : en soloQ, les bans sont simultanés et à l'aveugle. Le meilleur ban
est la pire menace de la lane jouée pour la pool (``BanRecommender``). Encore
faut-il connaître cette lane : un pool ``custom`` n'en déclare pas, et le calcul
agrégeait alors toutes les lanes (un pool de tanks top se voyait conseiller des
ADC). La lane se résout désormais dans cet ordre : rôle du pool, poste assigné
par le client, lane dominante des champions du pool.

Les champions déjà bannis/pickés sont filtrés (dette SPEC-10) : côté source
pour le calcul temps réel (exclude_champions), côté consommateur pour les bans
précalculés en base, qui ne connaissent pas l'état live.
"""

import sys
from typing import List, Optional

from ..analysis.pool_value import dominant_lane
from .state import DraftState

# Candidats lus en base avant filtrage des indisponibles : assez pour qu'il en
# reste 3 même après les bans alliés et ennemis.
_PRECALCULATED_LIMIT = 15
_SHOWN_BANS = 3


class BanAdvisor:
    """Ban recommendations: auto-hover during the ban phase, and display."""

    def __init__(self, monitor) -> None:
        self.m = monitor

    def _unavailable_champions(self, state: DraftState) -> list:
        """Champions déjà bannis ou pickés (camp allié ou ennemi) — plus
        candidats valides à un ban. `state.*_picks`/`*_bans` portent des
        champion_id malgré le type hint `List[str]` (voir state_parser.py)."""
        return [self.m._get_display_name(cid) for cid in state.get_all_actions()]

    def _ban_lane(self, state: Optional[DraftState] = None) -> Optional[str]:
        """Lane pour laquelle bannir : rôle du pool, sinon poste assigné par le
        client, sinon lane dominante des champions du pool."""
        if getattr(self.m, "pool_lane", None):
            return self.m.pool_lane
        state = state or getattr(self.m, "last_draft_state", None)
        if state is not None:
            position = state.ally_positions.get(state.local_player_cell_id)
            if position:
                return position
        try:
            return dominant_lane(self.m.assistant.db, self.m.current_pool)
        except Exception as e:  # repli best-effort : jamais d'exception dans la draft
            print(f"[WARNING] Lane dominante du pool introuvable, bans toutes lanes : {e}")
            return None

    def _recommendations(self, state: Optional[DraftState] = None) -> List[tuple]:
        """Les meilleurs bans disponibles pour la pool, pire menace d'abord.

        Les bans précalculés en base ne servent que pour un pool à rôle déclaré :
        c'est la seule lane pour laquelle ils ont été calculés.
        """
        unavailable = self._unavailable_champions(state) if state else []
        unavailable_lower = {name.lower() for name in unavailable}

        if getattr(self.m, "pool_name", None) and getattr(self.m, "pool_lane", None):
            stored = self.m.assistant.db.get_pool_ban_recommendations(
                self.m.pool_name, limit=_PRECALCULATED_LIMIT
            )
            usable = [r for r in stored or [] if r[0].lower() not in unavailable_lower]
            if usable:
                if self.m.verbose:
                    print(f"[DEBUG] Using pre-calculated bans for pool '{self.m.pool_name}'")
                return usable[:_SHOWN_BANS]

        return self.m.assistant.get_ban_recommendations(
            self.m.current_pool,
            num_bans=_SHOWN_BANS,
            lane=self._ban_lane(state),
            exclude_champions=unavailable,
        )

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

            unavailable_lower = {name.lower() for name in self._unavailable_champions(state)}
            ban_recommendations = self._recommendations(state)

            if not ban_recommendations:
                print("[DEBUG] No ban recommendations available")
                return

            if self.m.verbose:
                print(f"[DEBUG] Got {len(ban_recommendations)} ban recommendations")

            # Get the top ban recommendation
            top_ban, threat_score = ban_recommendations[0][:2]

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

            lane = self._ban_lane()
            if lane:
                print(f"Lane : {lane}")
            ban_recommendations = self._recommendations()

            if ban_recommendations:
                print(f"Envisagez de bannir ces menaces pour votre pool :")
                # Tuple : (enemy, threat, best_response_value, best_champ, matchup_count)
                for i, (enemy, threat_score, best_value, best_champ, _) in enumerate(
                    ban_recommendations, 1
                ):
                    print(
                        f"  {i}. {enemy:<12} | Menace : {threat_score:>5.2f} | "
                        f"Meilleure réponse : {best_champ} ({best_value:+.1f} pts)"
                    )
                print("[INFO] Menace : winrate gagné sur 100 parties en le bannissant")
            else:
                if self.m.verbose:
                    print(f"[ALERTE] Aucune donnée de ban disponible pour votre pool")

        except Exception as e:
            if self.m.verbose:
                print(f"[WARNING] Erreur lors de l'affichage des recommandations de ban: {e}")
