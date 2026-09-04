"""Menu 5 -- constructeur d'équipe optimal (duos/trios, évaluation holistique).

Extrait de src/ui/lol_coach_legacy.py (SPEC-07 E9).
"""

from typing import List

from src.assistant import Assistant
from src.utils.console import clear_console
from src.ui.pool_selection_ui import _select_pool_for_analysis


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
        else:
            pool_name, pool_champions, _pool_lane = selected_pool_info
            selected_pool = pool_champions
            print(f"\nUtilisation de la pool : {pool_name} ({len(pool_champions)} champions)")

        if choice == "1":
            print(f"\n" + "=" * 60)
            print(f"ANALYSE DU TRIO OPTIMAL")
            print("=" * 60)
            result = ast.optimal_trio_from_pool(selected_pool)
            blind, counter1, counter2, score = result
            print(f"\nRÉSULTAT FINAL :")
            print(f"Blind Pick : {blind}")
            print(f"Counterpicks : {counter1}, {counter2}")
            print(f"Score total : {score:.2f}")

            # Proposer de sauvegarder le trio comme nouveau pool
            _offer_save_optimization_result(
                [blind, counter1, counter2], f"Trio optimal (Score : {score:.2f})"
            )

        elif choice == "2":
            champion = input("Entrez le nom du champion : ").strip()
            if champion:
                print(f"\n" + "=" * 60)
                print(f"DUO OPTIMAL POUR {champion.upper()}")
                print("=" * 60)
                duo_result = ast.optimal_duo_for_champion(champion, selected_pool)

                # Si la méthode retourne un résultat, proposer de le sauvegarder
                if duo_result and isinstance(duo_result, tuple) and len(duo_result) == 4:
                    # Extrait les 3 champions (sans le score)
                    fixed_champ, companion1, companion2, score = duo_result
                    duo_champions = [fixed_champ, companion1, companion2]
                    _offer_save_optimization_result(
                        duo_champions, f"Duo optimal pour {champion} (Score : {score:.2f})"
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

            # Demande à l'utilisateur un profil de scoring
            scoring_profile = _select_scoring_profile()

            # Lance l'analyse holistique des trios
            trio_results = ast.find_optimal_trios_holistic(
                selected_pool, num_results=5, profile=scoring_profile
            )

            # Affiche les résultats
            _display_holistic_trio_results(trio_results, scoring_profile)

            # Propose de sauvegarder le meilleur trio
            if trio_results:
                best_trio = trio_results[0]["trio"]
                best_score = trio_results[0]["total_score"]
                _offer_save_optimization_result(
                    list(best_trio), f"Trio holistique (Score : {best_score:.2f})"
                )

        else:
            print("[ERROR] Option invalide")

        ast.close()

    except Exception as e:
        print(f"[ERROR] Erreur du constructeur d'équipe : {e}")


def _offer_save_optimization_result(champions: List[str], suggested_name: str):
    """Propose de sauvegarder les résultats d'optimisation comme nouvelle pool de champions."""
    if not champions:
        return

    # Affiche les recommandations de ban pour cette pool optimisée
    _show_ban_recommendations(champions)

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


def _select_scoring_profile() -> str:
    """Demande à l'utilisateur de choisir un profil de scoring pour l'analyse des trios."""
    print(f"\n" + "=" * 50)
    print("SÉLECTIONNER UN PROFIL DE SCORING")
    print("=" * 50)
    print("Choisissez votre style d'analyse préféré :")
    print()
    print("  1. SAFE       - Priorise la régularité et l'équilibre plutôt que la performance brute")
    print("                  Idéal pour : joueurs prudents, montée en ranked")
    print()
    print("  2. META       - Se concentre sur la performance face aux champions populaires")
    print("                  Idéal pour : adaptation au patch actuel, jeu en haut elo")
    print()
    print("  3. AGGRESSIVE - Maximise la couverture et la diversité des profils de champions")
    print("                  Idéal pour : joueurs proactifs, flexibilité d'équipe")
    print()
    print("  4. BALANCED   - Pondérations mathématiques sans biais")
    print("                  Idéal pour : choix par défaut, usage général")
    print()

    profile_map = {"1": "safe", "2": "meta", "3": "aggressive", "4": "balanced"}

    while True:
        choice = input("Choisissez un profil de scoring (1-4) : ").strip()

        if choice in profile_map:
            selected_profile = profile_map[choice]
            profile_names = {
                "safe": "SAFE",
                "meta": "META",
                "aggressive": "AGGRESSIVE",
                "balanced": "BALANCED",
            }
            print(f"\nProfil sélectionné : {profile_names[selected_profile]}")
            return selected_profile
        else:
            print("[ERROR] Choix invalide. Sélectionnez entre 1 et 4.")


def _display_holistic_trio_results(trio_results: List[dict], profile: str = "balanced"):
    """Affiche les résultats de l'analyse holistique des trios de façon claire."""
    try:
        if not trio_results:
            print("Aucun trio viable trouvé")
            return

        # Affiche les infos du profil
        profile_names = {
            "safe": "SAFE (Focus régularité)",
            "meta": "META (Focus champions populaires)",
            "aggressive": "AGGRESSIVE (Focus couverture)",
            "balanced": "BALANCED (Pondérations mathématiques)",
        }

        print(f"\nMEILLEURES COMBINAISONS DE TRIOS TROUVÉES :")
        print(f"Profil d'analyse : {profile_names.get(profile, profile.upper())}")
        print("=" * 80)

        for i, result in enumerate(trio_results, 1):
            trio = result["trio"]
            total = result["total_score"]
            coverage = result["coverage_score"]
            balance = result["balance_score"]
            consistency = result["consistency_score"]
            meta = result["meta_score"]

            print(f"\n{i}. {trio[0]} + {trio[1]} + {trio[2]}")
            print(f"   Score total : {total:>5.2f}/100")
            print(f"   Couverture :  {coverage:>5.2f}/100  (Couverture des matchups adverses)")
            print(f"   Équilibre :   {balance:>5.2f}/100  (Diversité des profils)")
            print(f"   Régularité :  {consistency:>5.2f}/100  (Performance fiable)")
            print(f"   Méta :        {meta:>5.2f}/100  (Face aux picks populaires)")

            # Affiche quelques exemples de couverture ennemie pour le meilleur trio
            if i == 1 and "enemy_coverage" in result:
                coverage_data = result["enemy_coverage"]
                if coverage_data:
                    print(f"   Meilleurs matchups : ", end="")
                    top_matchups = sorted(
                        coverage_data.items(), key=lambda x: x[1][0], reverse=True
                    )[:3]
                    matchup_strs = [
                        f"{enemy}(+{delta2:.2f})"
                        for enemy, (delta2, _) in top_matchups
                        if delta2 > 0
                    ]
                    print(", ".join(matchup_strs[:3]) if matchup_strs else "Aucun significatif")

        print("\n" + "=" * 80)
        print("INTERPRÉTATION :")
        print("   - Score plus élevé = meilleure performance globale du trio")
        print("   - Couverture = capacité du trio à gérer tous les adversaires")
        print("   - Équilibre = diversité pour éviter des faiblesses communes")
        print("   - Régularité = performance fiable sur l'ensemble des matchups")
        print("   - Méta = performance face aux champions actuellement populaires")

    except Exception as e:
        print(f"[ERROR] Erreur lors de l'affichage des résultats des trios : {e}")


def _show_ban_recommendations(champions: List[str]):
    """Affiche les recommandations de ban pour une pool de champions."""
    try:
        print(f"\n" + "=" * 60)
        print("RECOMMANDATIONS DE BAN STRATÉGIQUES")
        print("=" * 60)
        print(f"Pour votre pool optimisée : {', '.join(champions)}")

        from src.assistant import Assistant

        assistant = Assistant()

        ban_recommendations = assistant.get_ban_recommendations(champions, num_bans=5)

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
