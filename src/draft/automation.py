"""Auto-hover automation (champion select blind-pick assist).

Extracted from src/draft_monitor.py (SPEC-07 E10, lot 9) : déplacement
verbatim, aucun changement de comportement.

Back-reference to the monitor: reads lcu/current_pool/champion_id_to_name/
assistant, writes last_recommendation, and calls into the ban-advice domain
(``_show_ban_recommendations_draft``, extracted separately in lot 10) — too
many cross-domain touches for plain composition.
"""

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

            # Calculate scores for pool champions (blind pick scenario)
            scores = []
            for champion_id in champion_ids:
                champion_name = self.m._get_display_name(champion_id)
                matchups = self.m.assistant.get_matchups_for_draft(champion_name)
                if matchups and sum(m.games for m in matchups) >= draft_config.MIN_CHAMPION_GAMES:
                    # Use blind pick scoring (empty enemy team)
                    score = self.m.assistant.score_against_team(matchups, [], champion_name)
                    scores.append((champion_name, score))

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
