"""Interface pour la gestion des données de champions (mise à jour depuis l'API Riot, recalcul des scores)."""

from ..db import Database
from ..config import config
from ..assistant import Assistant
from ..utils.console import clear_console


def update_champion_data() -> None:
    """Met à jour les données de champions via un sous-menu."""
    clear_console()  # Efface la console au démarrage
    print("\n" + "=" * 60)
    print("GESTION DES DONNÉES DE CHAMPIONS")
    print("=" * 60)
    print("\nOptions :")
    print(
        "1. Mettre à jour la liste des champions - Récupérer les derniers champions depuis l'API Riot"
    )
    print(
        "2. Recalculer les scores des champions  - Reconstruire les scores de tier list depuis les données existantes"
    )
    print("3. Retour au menu principal")

    choice = input("\nChoisissez une option (1-3) : ").strip()

    if choice == "1":
        update_champion_list_from_riot()
    elif choice == "2":
        recalculate_champion_scores()
    elif choice == "3":
        return
    else:
        print("[ERROR] Option invalide")


def update_champion_list_from_riot() -> None:
    """Met à jour la liste des champions depuis l'API Riot."""
    print("[INFO] Mise à jour des données de champions depuis l'API Riot...")

    try:
        db = Database(config.DATABASE_PATH)
        db.connect()

        # S'assurer que la structure de la table est correcte
        if not db.create_riot_champions_table():
            print("[ERROR] Échec de la création/mise à jour de la table des champions")
            return

        # Mise à jour depuis l'API Riot
        if db.update_champions_from_riot_api():
            # Afficher quelques statistiques
            champion_names = db.get_all_champion_names()
            print(f"[SUCCESS] {len(champion_names)} champions mis à jour dans la base de données")
        else:
            print("[ERROR] Échec de la mise à jour des données de champions")

        db.close()
    except Exception as e:
        print(f"[ERROR] Erreur de mise à jour : {e}")


def recalculate_champion_scores() -> None:
    """Recalcule les scores de champions pour les tier lists à partir des données de matchups existantes."""
    print("\n[INFO] Recalcul des scores de champions pour les tier lists")
    print("=" * 60)
    print(
        "\nCeci va recalculer tous les scores de champions à partir des données de matchups existantes."
    )
    print("Utile après modification de la configuration ou des seuils de tier list.")
    print("\nNote : Ceci ne récupère PAS de nouvelles données depuis le web.")
    print(
        "       Utilisez 'Analyser des statistiques' pour mettre à jour les données de matchups au préalable."
    )

    confirm = input("\nProcéder au calcul des scores ? (y/n) : ").strip().lower()
    if confirm != "y":
        print("[INFO] Annulé")
        return

    try:
        db = Database(config.DATABASE_PATH)
        db.connect()

        # Vérifier si des données de matchups existent
        cursor = db.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM matchups")
        matchup_count = cursor.fetchone()[0]

        if matchup_count == 0:
            print("\n[ERROR] Aucune donnée de matchup trouvée dans la base de données")
            print(
                "[INFO] Veuillez d'abord lancer 'Analyser des statistiques' pour peupler les données de matchups"
            )
            db.close()
            return

        print(f"\n[INFO] {matchup_count:,} matchups trouvés dans la base de données")

        # Initialiser la table champion_scores
        print("[INFO] Initialisation de la table champion_scores...")
        db.init_champion_scores_table()

        # Calculer les scores
        print("[INFO] Calcul des scores globaux de champions...")
        assistant = Assistant()
        champions_scored = assistant.calculate_global_scores()

        print(f"\n[SUCCESS] {champions_scored} champions notés avec succès")
        print("[INFO] Les tier lists sont maintenant prêtes à l'emploi")

        assistant.close()
        db.close()

    except Exception as e:
        print(f"[ERROR] Erreur de calcul : {e}")
        import traceback

        traceback.print_exc()
