"""Menu 3 -- scraping / analyse de statistiques.

Extrait de src/ui/lol_coach_legacy.py (SPEC-07 E9).
"""

from src.config import config
from src.constants import TOP_SOLOQ_POOL
from src.utils.console import clear_console
from src.ui.pool_selection_ui import _select_pool_for_parsing


def _get_patch_version():
    """Demande à l'utilisateur la version du patch à analyser."""
    from src.config import config

    print(f"\nPatch actuel dans la config : {config.CURRENT_PATCH}")
    print("Options :")
    print("1. Utiliser le patch actuel de la config")
    print("2. Spécifier un patch différent")
    print("3. Retour au menu principal")

    choice = input("\nChoisissez une option (1-3) : ").strip()

    if choice == "1":
        return config.CURRENT_PATCH
    elif choice == "2":
        patch_input = input(f"Entrez la version du patch (ex. {config.CURRENT_PATCH}) : ").strip()
        if patch_input:
            # Valide le format du patch (validation basique)
            parts = patch_input.split(".")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return patch_input
            else:
                print(
                    f"[ERROR] Format de patch invalide. Utilisez un format comme {config.CURRENT_PATCH}"
                )
                return None
        else:
            print("[ERROR] La version du patch ne peut pas être vide")
            return None
    elif choice == "3":
        return None
    else:
        print("[ERROR] Option invalide")
        return None


def parse_match_statistics():
    """Parse les statistiques de matchs depuis les sources web avec sous-menu."""
    clear_console()  # Efface la console au démarrage
    print("[INFO] Analyseur de statistiques de matchs")

    # Demande d'abord la version du patch
    patch_version = _get_patch_version()
    if not patch_version:
        return

    print(f"\nPatch sélectionné : {patch_version}")
    print("\nOptions d'analyse :")
    print("MATCHUPS :")
    print("1. Analyser les matchups (Pool SoloQ)      - Rapide (~1 min)")
    print("2. Analyser les matchups (Tous champions)  - Complet (~6-8 min)")
    print("\nSYNERGIES :")
    print("3. Analyser les synergies (Pool SoloQ)      - Rapide (~1 min)")
    print("4. Analyser les synergies (Tous champions)  - Complet (~6-8 min)")
    print("\nCOMPLET :")
    print("5. Analyser toutes les données (Pool SoloQ)     - Matchups + Synergies (~2 min)")
    print("6. Analyser toutes les données (Tous champions) - Matchups + Synergies (~12-16 min)")
    print("\n7. Retour au menu principal")

    choice = input("\nChoisissez une option (1-7) : ").strip()

    if choice == "1":
        parse_champion_pool(patch_version)
    elif choice == "2":
        parse_all_champions(patch_version)
    elif choice == "3":
        parse_synergies_pool(patch_version)
    elif choice == "4":
        parse_synergies_all(patch_version)
    elif choice == "5":
        parse_all_data_pool(patch_version)
    elif choice == "6":
        parse_all_data_all(patch_version)
    elif choice == "7":
        return
    else:
        print("[ERROR] Option invalide")


def _run_pool_pipeline(
    pool_name, pool_champions, patch_version, include_matchups, include_synergies
):
    """Corps commun aux quatre options de menu parse_* limitées à une pool.

    Délègue à src.pipeline.run_pipeline() (SPEC-01 A2) pour que le menu
    bénéficie du même contrôle de complétude, des écritures db_meta, du
    fichier de log et des notifications que scripts/update_all.py, au lieu
    d'un scraping fait à la main.
    """
    from src.pipeline import run_pipeline

    result = run_pipeline(
        champions=pool_champions,
        include_matchups=include_matchups,
        include_synergies=include_synergies,
        patch=patch_version,
    )

    if result.status != "ok":
        print(f"[ERROR] Erreur d'analyse : {result.error}")
        return

    stats = result.scrape_stats
    print("\n" + "=" * 60)
    print("SCRAPING TERMINÉ")
    print("=" * 60)
    print(f"Pool : {pool_name}")
    print(f"Pages : {stats['success']}/{stats['total']} ok ({stats['failed']} échecs)")
    print(f"Durée : {result.duration_min:.1f} min")
    print("=" * 60)
    print(
        f"[SUCCESS] Données de {pool_name} mises à jour ! "
        f"({stats['success']} pages scrapées, {result.scores_count} champions scorés)"
    )


def _run_full_pipeline(label, patch_version, include_matchups, include_synergies):
    """Corps commun aux deux options de menu parse_* pour tous les champions."""
    from src.pipeline import run_pipeline

    result = run_pipeline(
        include_matchups=include_matchups,
        include_synergies=include_synergies,
        patch=patch_version,
    )

    if result.status != "ok":
        print(f"[ERROR] Erreur d'analyse : {result.error}")
        return

    stats = result.scrape_stats
    print("\n" + "=" * 60)
    print("SCRAPING TERMINÉ")
    print("=" * 60)
    print(f"Pages : {stats['success']}/{stats['total']} ok ({stats['failed']} échecs)")
    print(f"Durée : {result.duration_min:.1f} min")
    print("=" * 60)
    print(
        f"[SUCCESS] {label} mis à jour ! "
        f"({stats['success']} pages scrapées, {result.scores_count} champions scorés)"
    )


def _select_pool_or_default():
    """Sélection de pool commune aux options parse_* limitées à une pool."""
    selected_pool_info = _select_pool_for_parsing()
    if not selected_pool_info:
        print("[WARNING] Aucune pool sélectionnée, utilisation de la pool Top SoloQ par défaut")
        return "Top SoloQ (Défaut)", TOP_SOLOQ_POOL
    return selected_pool_info


def parse_champion_pool(patch_version=None):
    """Parse les statistiques de matchs pour la pool de champions sélectionnée via le pipeline partagé."""
    print("[INFO] Analyseur de statistiques de pool de champions")

    pool_name, pool_champions = _select_pool_or_default()
    print(f"\nAnalyse des statistiques pour : {pool_name}")
    print(f"Version du patch : {patch_version or 'défaut'}")
    print(f"Champions à traiter : {', '.join(pool_champions)}")

    confirm = (
        input(f"\nContinuer l'analyse de {len(pool_champions)} champions ? (y/N) : ")
        .strip()
        .lower()
    )
    if confirm != "y":
        print("[INFO] Analyse annulée.")
        return

    _run_pool_pipeline(
        pool_name, pool_champions, patch_version, include_matchups=True, include_synergies=False
    )


def parse_all_champions(patch_version=None):
    """Parse les statistiques de matchs pour tous les champions via le pipeline partagé."""
    print("[INFO] Analyse de TOUS les champions via le pipeline partagé")

    confirm = input("\nÊtes-vous sûr de vouloir continuer ? (y/N) : ").strip().lower()
    if confirm != "y":
        print("[INFO] Annulé par l'utilisateur")
        return

    _run_full_pipeline(
        "Statistiques de tous les champions",
        patch_version,
        include_matchups=True,
        include_synergies=False,
    )


def parse_synergies_pool(patch_version=None):
    """Parse les synergies pour la pool de champions sélectionnée via le pipeline partagé."""
    print("[INFO] Analyseur de synergies de pool de champions")

    pool_name, pool_champions = _select_pool_or_default()
    print(f"\nAnalyse des synergies pour : {pool_name}")
    print(f"Version du patch : {patch_version or 'défaut'}")
    print(f"Champions à traiter : {', '.join(pool_champions)}")

    confirm = (
        input(
            f"\nContinuer l'analyse des synergies pour {len(pool_champions)} champions ? (y/N) : "
        )
        .strip()
        .lower()
    )
    if confirm != "y":
        print("[INFO] Analyse annulée.")
        return

    _run_pool_pipeline(
        pool_name, pool_champions, patch_version, include_matchups=False, include_synergies=True
    )


def parse_synergies_all(patch_version=None):
    """Parse les synergies pour tous les champions via le pipeline partagé."""
    print("[INFO] Analyse des synergies pour TOUS les champions")

    confirm = input("\nÊtes-vous sûr de vouloir continuer ? (y/N) : ").strip().lower()
    if confirm != "y":
        print("[INFO] Annulé par l'utilisateur")
        return

    _run_full_pipeline(
        "Statistiques de synergies", patch_version, include_matchups=False, include_synergies=True
    )


def parse_all_data_pool(patch_version=None):
    """Parse les matchups et synergies pour la pool de champions sélectionnée via le pipeline partagé."""
    print("[INFO] Analyse de TOUTES les données (matchups + synergies) pour la pool de champions")

    pool_name, pool_champions = _select_pool_or_default()
    print(f"\nAnalyse des données complètes pour : {pool_name}")
    print(f"Version du patch : {patch_version or 'défaut'}")
    print(f"Champions à traiter : {', '.join(pool_champions)}")

    confirm = (
        input(
            f"\nContinuer l'analyse des matchups + synergies pour {len(pool_champions)} "
            f"champions ? (y/N) : "
        )
        .strip()
        .lower()
    )
    if confirm != "y":
        print("[INFO] Analyse annulée.")
        return

    _run_pool_pipeline(
        pool_name, pool_champions, patch_version, include_matchups=True, include_synergies=True
    )


def parse_all_data_all(patch_version=None):
    """Parse les matchups et synergies pour tous les champions via le pipeline partagé."""
    print("[INFO] Analyse de TOUTES les données (matchups + synergies) pour TOUS les champions")

    confirm = input("\nÊtes-vous sûr de vouloir continuer ? (y/N) : ").strip().lower()
    if confirm != "y":
        print("[INFO] Annulé par l'utilisateur")
        return

    _run_full_pipeline(
        "Toutes les données (matchups + synergies)",
        patch_version,
        include_matchups=True,
        include_synergies=True,
    )
