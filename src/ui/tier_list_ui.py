"""Menu 4 -- point d'entrée pour l'analyse de champions & le coaching de tournoi, tier lists.

Extrait de src/ui/lol_coach_legacy.py (SPEC-07 E9).
"""

from typing import List

from src.utils.console import clear_console
from src.ui.pool_selection_ui import _select_pool_for_analysis
from src.ui.tournament_coach_ui import run_tournament_draft_coach


def run_champion_analysis():
    """Lance l'analyse de champions et le coaching de tournoi."""
    clear_console()  # Efface la console au démarrage
    print("[INFO] Analyse de champions & coaching de tournoi")
    print("\nOptions disponibles :")
    print("1. Générer une tier list    - Créer des tier lists blind pick ou counter pick")
    print("2. Coach de draft tournoi   - Coaching manuel pour tournois externes")
    print("3. Retour au menu principal")

    choice = input("\nChoisissez une option (1-3) : ").strip()

    if choice == "1":
        run_tier_list_generator()
    elif choice == "2":
        run_tournament_draft_coach()
    elif choice == "3":
        return
    else:
        print("[ERROR] Option invalide")


def run_tier_list_generator():
    """Génère des tier lists pour les pools de champions."""
    clear_console()  # Efface la console au démarrage
    print("[INFO] Générateur de tier list")

    try:
        from src.assistant import Assistant

        # Étape 1 : sélectionner la pool de champions
        print("\n" + "=" * 60)
        print("ÉTAPE 1 : SÉLECTIONNER LA POOL DE CHAMPIONS")
        print("=" * 60)

        selected_pool_info = _select_pool_for_analysis()
        if not selected_pool_info:
            print("[ERROR] Aucune pool sélectionnée")
            return

        pool_name, champion_pool, pool_lane = selected_pool_info
        lane_desc = pool_lane or "toutes lanes agrégées"
        print(f"\n[SUCCESS] Pool sélectionnée : {pool_name} ({len(champion_pool)} champions)")
        print(f"[INFO] Scores scopés à : {lane_desc}")

        # Étape 2 : sélectionner le type d'analyse
        print("\n" + "=" * 60)
        print("ÉTAPE 2 : SÉLECTIONNER LE TYPE D'ANALYSE")
        print("=" * 60)
        print("\nChoisissez le type de tier list :")
        print("  1. Blind Pick    - Champions à performance constante sur tous les matchups")
        print("  2. Counter Pick  - Champions avec de forts pics sur des matchups spécifiques")
        print("  3. Annuler")

        type_choice = input("\nChoix (1-3) : ").strip()

        if type_choice == "1":
            analysis_type = "blind_pick"
            type_name = "BLIND PICK"
        elif type_choice == "2":
            analysis_type = "counter_pick"
            type_name = "COUNTER PICK"
        elif type_choice == "3":
            print("[INFO] Annulé par l'utilisateur")
            return
        else:
            print("[ERROR] Choix invalide")
            return

        # Étape 3 : générer la tier list
        print("\n" + "=" * 60)
        print(f"GÉNÉRATION DE LA TIER LIST {type_name}...")
        print("=" * 60)

        assistant = Assistant()
        tier_list = assistant.generate_tier_list(champion_pool, analysis_type, lane=pool_lane)
        assistant.close()

        if not tier_list:
            print("[WARNING] Aucun champion avec suffisamment de données trouvé dans la pool")
            return

        # Étape 4 : afficher les résultats
        _display_tier_list(tier_list, pool_name, type_name, analysis_type, lane_desc)

    except Exception as e:
        print(f"[ERROR] Erreur de génération de tier list : {e}")
        import traceback

        traceback.print_exc()


def _display_tier_list(
    tier_list: List[dict], pool_name: str, type_name: str, analysis_type: str, lane_desc: str
):
    """Affiche les résultats formatés de la tier list."""
    from src.config_constants import analysis_config
    from src.utils.display import safe_print

    print("\n" + "=" * 80)
    if analysis_type == "blind_pick":
        safe_print(f"{type_name} TIER LIST - {pool_name} ({len(tier_list)} champions)")
        print("Focus : constance et stabilité sur tous les matchups")
    else:
        safe_print(f"{type_name} TIER LIST - {pool_name} ({len(tier_list)} champions)")
        print("Focus : puissance situationnelle et potentiel de counter")
    safe_print(f"Lane : {lane_desc}")
    print("=" * 80)

    # Regrouper par tier
    tiers = {"S": [], "A": [], "B": [], "C": []}
    for entry in tier_list:
        tiers[entry["tier"]].append(entry)

    # Afficher chaque tier
    tier_ranges = {
        "S": f"{analysis_config.TIER_THRESHOLDS["S"]:.0f}-100",
        "A": f"{analysis_config.TIER_THRESHOLDS["A"]:.0f}-{analysis_config.TIER_THRESHOLDS["S"]:.0f}",
        "B": f"{analysis_config.TIER_THRESHOLDS["B"]:.0f}-{analysis_config.TIER_THRESHOLDS["A"]:.0f}",
        "C": f"0-{analysis_config.TIER_THRESHOLDS["B"]:.0f}",
    }

    for tier_letter in ["S", "A", "B", "C"]:
        champions_in_tier = tiers[tier_letter]
        if not champions_in_tier:
            continue

        tier_desc = {
            "S": "Elite" if analysis_type == "blind_pick" else "Contre-picks premium",
            "A": "Solide" if analysis_type == "blind_pick" else "Contre-picks solides",
            "B": "Situationnel" if analysis_type == "blind_pick" else "Contre-picks de niche",
            "C": "Faible" if analysis_type == "blind_pick" else "Valeur limitée",
        }

        safe_print(f"\n{tier_letter}-TIER ({tier_ranges[tier_letter]}) - {tier_desc[tier_letter]}")

        for i, entry in enumerate(champions_in_tier, 1):
            champion = entry["champion"]
            score = entry["score"]
            metrics = entry["metrics"]

            print(f"  {i}. {champion:<15} | Score: {score:>5.1f} / 100")

            # Afficher les métriques selon le type d'analyse
            if analysis_type == "blind_pick":
                avg_delta2 = metrics["avg_delta2_raw"]
                variance = metrics["variance"]
                coverage = metrics["coverage_raw"]
                safe_print(f"     Delta2 moyen :   {avg_delta2:>+5.2f}  (Performance)")
                safe_print(
                    f"     Stabilité :      {metrics['stability']:>5.2f}  (Variance : {variance:.2f})"
                )
                safe_print(f"     Couverture :     {coverage:>5.1%}  (Matchups corrects)")

            elif analysis_type == "counter_pick":
                peak_impact = metrics["peak_impact_raw"]
                variance = metrics["variance"]
                target_ratio = metrics["target_ratio_raw"]
                safe_print(
                    f"     Pic d'impact :   {peak_impact:>5.2f}  (Matchups favorables pondérés)"
                )
                safe_print(f"     Volatilité :     {variance:>5.2f}  (Élevé = situationnel)")
                safe_print(
                    f"     Cibles :         {target_ratio:>5.1%}  (% de contre-picks viables)"
                )

            print()

    # Résumé en pied de page
    print("=" * 80)
    safe_print("CONFIGURATION DE LA TIER LIST :")
    if analysis_type == "blind_pick":
        safe_print(
            f"   • Pondérations : Performance {analysis_config.BLIND_AVG_WEIGHT:.0%}, "
            f"Stabilité {analysis_config.BLIND_STABILITY_WEIGHT:.0%}, "
            f"Couverture {analysis_config.BLIND_COVERAGE_WEIGHT:.0%}"
        )
    else:
        safe_print(
            f"   • Pondérations : Pic d'impact {analysis_config.COUNTER_PEAK_WEIGHT:.0%}, "
            f"Volatilité {analysis_config.COUNTER_VOLATILITY_WEIGHT:.0%}, "
            f"Cibles {analysis_config.COUNTER_TARGETS_WEIGHT:.0%}"
        )
    safe_print(
        f"   • Seuils : S≥{analysis_config.TIER_THRESHOLDS["S"]:.0f}, "
        f"A≥{analysis_config.TIER_THRESHOLDS["A"]:.0f}, "
        f"B≥{analysis_config.TIER_THRESHOLDS["B"]:.0f}"
    )
    print("=" * 80)
