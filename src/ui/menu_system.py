"""Main menu system and application banner."""


def print_banner() -> None:
    """Print application banner."""
    banner = """
==================================================================
                      LEAGUE OF LEGENDS COACH

  Boîte à outils complète pour l'analyse de champions et l'aide au draft
  - Suivi du draft en temps réel
  - Gestion des données de champions
  - Analyse statistique et tier lists
==================================================================
"""
    print(banner)


def print_main_menu() -> str:
    """
    Print the main menu options and get user choice.

    Returns:
        User's menu choice as string
    """
    menu = """
MENU PRINCIPAL :
  1. Draft Coach en temps réel  - Suivre le champion select et recevoir des recommandations
  2. Mettre à jour les données  - Récupérer les derniers champions depuis l'API Riot
  3. Analyser des statistiques  - Scraper les données de matchups (Pool SoloQ ou tous les champions)
  4. Analyse & Tournoi          - Analyse statistique et coaching manuel de tournoi
  5. Constructeur d'équipe      - Trouver les meilleures combinaisons de champions
  6. Gérer les pools            - Créer, modifier et gérer des pools de champions personnalisées
  7. Quitter

Choisissez une option (1-7) : """
    return input(menu).strip()


def print_requirements() -> None:
    """Print system requirements for real-time draft coach."""
    print("\nPRÉREQUIS :")
    print("- Le client League of Legends doit être lancé")
    print("- Vous devez être en champion select")
    print()
