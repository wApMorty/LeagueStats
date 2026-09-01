"""Menu 6 -- gestion des pools de champions : menu principal, listing, statistiques.

Extrait de src/ui/lol_coach_legacy.py (SPEC-07 E9). Les opérations CRUD
(création/édition/suppression/duplication) se trouvent dans src/ui/pools_crud_ui.py.
"""

from src.utils.console import clear_console
from src.ui.pool_selection_ui import _select_pool_interactive
from src.ui.pools_crud_ui import create_new_pool, edit_pool, delete_pool, duplicate_pool


def manage_champion_pools():
    """Gère les pools de champions via une interface interactive."""
    clear_console()  # Efface la console au démarrage
    from src.pool_manager import PoolManager
    from src.assistant import Assistant

    print("[INFO] Gestionnaire de pools de champions")

    try:
        pool_manager = PoolManager()
        assistant = Assistant()
        available_champions = set(assistant.db.get_all_champion_names().values())

        while True:
            print("\n" + "=" * 60)
            print("GESTION DES POOLS DE CHAMPIONS")
            print("=" * 60)

            menu = """
Options de gestion des pools :
  1. Lister toutes les pools
  2. Voir les détails d'une pool
  3. Créer une nouvelle pool
  4. Modifier une pool existante
  5. Supprimer une pool
  6. Dupliquer une pool
  7. Rechercher des pools
  8. Statistiques des pools
  9. Retour au menu principal

Choisissez une option (1-9) : """

            choice = input(menu).strip()

            if choice == "1":
                list_pools(pool_manager)
            elif choice == "2":
                view_pool_details(pool_manager)
            elif choice == "3":
                create_new_pool(pool_manager, available_champions)
            elif choice == "4":
                edit_pool(pool_manager, available_champions)
            elif choice == "5":
                delete_pool(pool_manager)
            elif choice == "6":
                duplicate_pool(pool_manager)
            elif choice == "7":
                search_pools(pool_manager)
            elif choice == "8":
                show_pool_statistics(pool_manager)
            elif choice == "9":
                pool_manager.save_custom_pools()
                print("[INFO] Pools personnalisées enregistrées !")
                break
            else:
                print("[ERROR] Option invalide. Veuillez choisir 1-9.")

        assistant.close()

    except Exception as e:
        print(f"[ERROR] Erreur du gestionnaire de pools : {e}")
        if hasattr(e, "__traceback__"):
            import traceback

            traceback.print_exc()


def list_pools(pool_manager):
    """Liste toutes les pools disponibles."""
    print("\n" + "=" * 50)
    print("TOUTES LES POOLS DE CHAMPIONS")
    print("=" * 50)

    pools = pool_manager.get_all_pools()
    if not pools:
        print("Aucune pool trouvée.")
        return

    # Regrouper par type
    system_pools = []
    custom_pools = []

    for name, pool in pools.items():
        if pool.created_by == "system":
            system_pools.append((name, pool))
        else:
            custom_pools.append((name, pool))

    if system_pools:
        print("\nPOOLS SYSTÈME :")
        for name, pool in sorted(system_pools):
            print(
                f"  {name:<20} | {pool.role:<8} | {pool.size():>2} champions | {pool.description}"
            )

    if custom_pools:
        print("\nPOOLS PERSONNALISÉES :")
        for name, pool in sorted(custom_pools):
            print(
                f"  {name:<20} | {pool.role:<8} | {pool.size():>2} champions | {pool.description}"
            )

    if not custom_pools:
        print("\nPOOLS PERSONNALISÉES : Aucune créée pour le moment")


def view_pool_details(pool_manager):
    """Affiche les détails d'une pool spécifique."""
    pool = _select_pool_interactive(pool_manager, "Voir les détails d'une pool")
    if not pool:
        return

    print(f"\n" + "=" * 50)
    print(f"DÉTAILS DE LA POOL : {pool.name}")
    print("=" * 50)
    print(f"Rôle : {pool.role}")
    print(f"Description : {pool.description}")
    print(f"Créée par : {pool.created_by}")
    print(f"Tags : {', '.join(pool.tags) if pool.tags else 'Aucun'}")
    print(f"Champions ({pool.size()}) :")

    # Afficher les champions en colonnes
    champions = pool.champions
    cols = 3
    for i in range(0, len(champions), cols):
        row = champions[i : i + cols]
        print(f"  {' | '.join(f'{champ:<15}' for champ in row)}")


def search_pools(pool_manager):
    """Recherche des pools."""
    query = input("\nEntrez votre recherche : ").strip()
    matches = pool_manager.search_pools(query)

    if matches:
        print(f"\n{len(matches)} pool(s) trouvée(s) :")
        for name in matches:
            pool = pool_manager.get_pool(name)
            print(f"  {name} | {pool.role} | {pool.size()} champions")
    else:
        print("Aucune pool trouvée.")


def show_pool_statistics(pool_manager):
    """Affiche les statistiques des pools - analyse globale ou par pool."""
    print("\n" + "=" * 50)
    print("STATISTIQUES DES POOLS")
    print("=" * 50)

    menu = """
Options de statistiques :
  1. Statistiques globales des pools (comptage par type/rôle)
  2. Analyse de performance d'une pool individuelle
  3. Retour à la gestion des pools

Choisissez une option (1-3) : """

    choice = input(menu).strip()

    if choice == "1":
        # Statistiques globales (fonctionnalité originale)
        stats = pool_manager.get_pool_stats()

        print("\n" + "=" * 40)
        print("STATISTIQUES GLOBALES DES POOLS")
        print("=" * 40)
        print(f"Total des pools : {stats['total_pools']}")
        print(f"Pools personnalisées : {stats['custom_pools']}")
        print(f"Pools système : {stats['system_pools']}")

        print("\nPar rôle :")
        for key, value in stats.items():
            if key.endswith("_pools") and not key.startswith(("total", "custom", "system")):
                role = key.replace("_pools", "")
                print(f"  {role.capitalize()}: {value}")

    elif choice == "2":
        # Analyse de performance d'une pool individuelle (NOUVEAU)
        show_individual_pool_statistics(pool_manager)

    elif choice == "3":
        return

    else:
        print("[ERROR] Option invalide. Veuillez choisir 1-3.")


def show_individual_pool_statistics(pool_manager):
    """Affiche les statistiques de performance détaillées pour une pool de champions spécifique."""
    from src.analysis.pool_statistics import PoolStatisticsCalculator, format_pool_statistics
    from src.assistant import Assistant
    from src.utils.display import safe_print

    # Sélectionner une pool
    pool = _select_pool_interactive(pool_manager, "Sélectionner une pool pour les statistiques")
    if not pool:
        return

    safe_print(f"\n[INFO] Calcul des statistiques pour la pool : {pool.name}")
    print("[INFO] Cela peut prendre un moment...")

    try:
        # Initialiser le calculateur
        assistant = Assistant()
        calculator = PoolStatisticsCalculator(assistant.db)

        # Optimisation de performance : préchauffer le cache avant l'analyse (99% plus rapide)
        print("[INFO] Préchauffage du cache pour la performance...")
        assistant.warm_cache(pool.champions)

        # Calculer les statistiques
        stats = calculator.calculate_pool_statistics(pool.name, pool.champions)

        # Vider le cache pour libérer de la mémoire
        assistant.clear_cache()

        # Afficher la sortie formatée
        output = format_pool_statistics(stats)
        print("\n" + output)

        # Invite à continuer
        input("\nAppuyez sur Entrée pour continuer...")

        assistant.close()

    except Exception as e:
        print(f"[ERROR] Échec du calcul des statistiques de la pool : {e}")
        import traceback

        traceback.print_exc()
