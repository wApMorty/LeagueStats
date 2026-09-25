"""Menu 5 -- constructeur d'équipe optimal (duos/trios, évaluation holistique).

Extrait de src/ui/lol_coach_legacy.py (SPEC-07 E9).
"""

from typing import List, Optional

from src.assistant import Assistant
from src.utils.console import clear_console
from src.utils.display import format_games_count
from src.ui.pool_selection_ui import _select_pool_for_analysis


def _games_tag(assistant: Assistant, champion: str, lane: Optional[str]) -> str:
    """SPEC-09 E5: volume de games derrière un champion affiché, même
    convention que le Live Coach (recommendations.py, "· 91 696 games").

    Best-effort : un champion sans données (ou une erreur de lookup) ne doit
    jamais faire échouer l'affichage du résultat d'optimisation — retourne
    simplement une chaîne vide.
    """
    try:
        matchups = assistant.get_matchups_for_draft(champion, lane=lane)
        total_games = sum(m.games for m in matchups) if matchups else 0
        return f" · {format_games_count(total_games)} games"
    except Exception:
        return ""


def run_optimal_team_builder():
    """Lance les outils de construction d'équipe optimale."""
    clear_console()  # Efface la console au démarrage
    print("[INFO] Constructeur d'équipe optimale")
    print("\nOptions disponibles :")
    print("1. Trouver le trio optimal depuis la pool (traditionnel - blind pick + counterpicks)")
    print("2. Trouver le duo optimal pour un champion spécifique")
    print("3. Trouver les combinaisons de trios optimales (évaluation holistique)")

    choice = input("Choisissez une option (1-3) : ").strip()

    try:
        from src.pool_manager import PoolManager

        ast = Assistant()

        # Sélection de pool enrichie via PoolManager
        selected_pool_info = _select_pool_for_analysis()
        if not selected_pool_info:
            print("[WARNING] Aucune pool sélectionnée, utilisation de la pool Top SoloQ par défaut")
            selected_pool = ast.select_extended_champion_pool()
            pool_lane = None
        else:
            pool_name, pool_champions, pool_lane = selected_pool_info
            selected_pool = pool_champions
            print(f"\nUtilisation de la pool : {pool_name} ({len(pool_champions)} champions)")

        if choice == "1":
            print(f"\n" + "=" * 60)
            print(f"ANALYSE DU TRIO OPTIMAL")
            print("=" * 60)
            result = ast.optimal_trio_from_pool(selected_pool, lane=pool_lane)
            blind, counter1, counter2, score = result
            print(f"\nRÉSULTAT FINAL :")
            print(f"Blind Pick : {blind}{_games_tag(ast, blind, pool_lane)}")
            print(
                f"Counterpicks : {counter1}{_games_tag(ast, counter1, pool_lane)}, "
                f"{counter2}{_games_tag(ast, counter2, pool_lane)}"
            )
            print(f"Score total : {score:.2f}")

            # Proposer de sauvegarder le trio comme nouveau pool
            _offer_save_optimization_result(
                [blind, counter1, counter2], f"Trio optimal (Score : {score:.2f})", lane=pool_lane
            )

        elif choice == "2":
            champion = input("Entrez le nom du champion : ").strip()
            if champion:
                print(f"\n" + "=" * 60)
                print(f"DUO OPTIMAL POUR {champion.upper()}")
                print("=" * 60)
                duo_result = ast.optimal_duo_for_champion(champion, selected_pool, lane=pool_lane)

                # Si la méthode retourne un résultat, proposer de le sauvegarder
                if duo_result and isinstance(duo_result, tuple) and len(duo_result) == 4:
                    # Extrait les 3 champions (sans le score)
                    fixed_champ, companion1, companion2, score = duo_result
                    duo_champions = [fixed_champ, companion1, companion2]
                    _offer_save_optimization_result(
                        duo_champions,
                        f"Duo optimal pour {champion} (Score : {score:.2f})",
                        lane=pool_lane,
                    )
            else:
                print("[ERROR] Aucun nom de champion fourni")

        elif choice == "3":
            print(f"\n" + "=" * 60)
            print(f"ANALYSE HOLISTIQUE DES COMBINAISONS DE TRIOS")
            print("=" * 60)
            print(f"Analyse de toutes les combinaisons de trios possibles depuis votre pool...")
            print(
                f"Cette analyse évalue les trios comme des unités complètes plutôt "
                f"qu'en blind pick + counterpicks"
            )

            trio_results = ast.find_optimal_trios_holistic(
                selected_pool, num_results=5, lane=pool_lane
            )
            _display_holistic_trio_results(trio_results)

            # Propose de sauvegarder le meilleur trio
            if trio_results:
                best_trio = trio_results[0]["trio"]
                best_score = trio_results[0]["total_score"]
                _offer_save_optimization_result(
                    list(best_trio),
                    f"Trio holistique (Gain : {best_score:+.2f} pts)",
                    lane=pool_lane,
                )

        else:
            print("[ERROR] Option invalide")

        ast.close()

    except Exception as e:
        print(f"[ERROR] Erreur du constructeur d'équipe : {e}")


def _offer_save_optimization_result(
    champions: List[str], suggested_name: str, lane: Optional[str] = None
):
    """Propose de sauvegarder les résultats d'optimisation comme nouvelle pool de champions."""
    if not champions:
        return

    # Affiche les recommandations de ban pour cette pool optimisée
    _show_ban_recommendations(champions, lane=lane)

    save_choice = input(f"\nSauvegarder ce résultat comme nouvelle pool ? (y/N) : ").strip().lower()
    if save_choice != "y":
        return

    try:
        from src.pool_manager import PoolManager

        pool_manager = PoolManager()

        print(f"\nSauvegarde de la pool avec les champions : {', '.join(champions)}")

        # Suggère un nom mais permet de le personnaliser
        default_name = suggested_name
        pool_name = input(f"Nom de la pool (ou Entrée pour '{default_name}') : ").strip()
        if not pool_name:
            pool_name = default_name

        # Vérifie si le nom existe déjà
        if pool_manager.get_pool(pool_name):
            print(f"[WARNING] La pool '{pool_name}' existe déjà.")
            overwrite = input("Écraser la pool existante ? (y/N) : ").strip().lower()
            if overwrite != "y":
                return
            pool_manager.delete_pool(pool_name)  # Supprime l'existante

        description = input("Description (optionnel) : ").strip()
        if not description:
            description = f"Générée depuis une analyse d'optimisation"

        # Détermine le rôle en fonction des champions (heuristique simple)
        role = "custom"

        # Tags
        tags = ["optimization", "generated"]

        if pool_manager.create_pool(pool_name, champions, description, role, tags):
            print(f"[SUCCESS] Pool '{pool_name}' créée avec {len(champions)} champions !")

            # Sauvegarde immédiatement
            if pool_manager.save_custom_pools():
                print(f"[SUCCESS] Pool sauvegardée avec succès !")
            else:
                print(
                    f"[WARNING] Pool créée mais la sauvegarde a échoué. "
                    f"Utilisez le menu 'Gérer les pools' pour sauvegarder manuellement."
                )
        else:
            print(f"[ERROR] Échec de la création de la pool '{pool_name}'")

    except Exception as e:
        print(f"[ERROR] Erreur lors de la sauvegarde du résultat d'optimisation : {e}")


def _display_holistic_trio_results(trio_results: List[dict]):
    """Affiche les meilleurs trios du pool (SPEC-18 §4)."""
    if not trio_results:
        print("Aucun trio viable trouvé")
        return

    print("\nMEILLEURS TRIOS DU POOL :")
    print("=" * 80)
    for i, result in enumerate(trio_results, 1):
        blind, counter1, counter2 = result["trio"]
        print(f"\n{i}. {blind} (blind) + {counter1} + {counter2}")
        print(
            f"   Gain en contre-pick : {result['total_score']:+.2f} pts | "
            f"Couverture : {result['coverage']:.0%} des games | "
            f"Blind : {result['blind_strength']:+.2f} pts vs moyenne"
        )

    print("\n" + "=" * 80)
    print("INTERPRÉTATION :")
    print("   - Gain = avantage moyen quand on contre-pick avec le meilleur du trio,")
    print("     ennemis pondérés par leur popularité sur la lane")
    print("   - Couverture = part des games où le trio a un contre-pick au-dessus de la moyenne")


def _show_ban_recommendations(champions: List[str], lane: Optional[str] = None):
    """Affiche les recommandations de ban pour une pool de champions."""
    try:
        print(f"\n" + "=" * 60)
        print("RECOMMANDATIONS DE BAN STRATÉGIQUES")
        print("=" * 60)
        print(f"Pour votre pool optimisée : {', '.join(champions)}")

        from src.assistant import Assistant

        assistant = Assistant()

        ban_recommendations = assistant.get_ban_recommendations(champions, num_bans=5, lane=lane)

        if ban_recommendations:
            print(f"\nMenaces principales à bannir :")
            # Format tuple : (enemy, threat_score, best_delta2, best_champ, matchup_count)
            for i, (enemy, threat_score, _best_delta2, _best_champ, matchup_count) in enumerate(
                ban_recommendations, 1
            ):
                print(
                    f"  {i}. {enemy:<15} | Menace : {threat_score:>5.2f} | Contre {matchup_count}/{len(champions)} champions"
                )

            print(f"\nCes champions sont statistiquement forts contre votre pool.")
            print(f"Les bannir améliorera la répartition globale de vos matchups.")
        else:
            print(f"Aucune recommandation de ban trouvée (données insuffisantes)")

        assistant.close()

    except Exception as e:
        print(f"[WARNING] Erreur lors de la génération des recommandations de ban : {e}")
