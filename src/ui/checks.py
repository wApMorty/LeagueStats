"""Vérifications de démarrage (dépendances, présence de la base de données).

Extrait de src/ui/lol_coach_legacy.py (SPEC-07 E9).
"""

import os

from src.config import config


def check_dependencies():
    """Vérifie si les dépendances requises sont disponibles."""
    missing_deps = []

    try:
        import requests
    except ImportError:
        missing_deps.append("requests")

    try:
        import psutil
    except ImportError:
        missing_deps.append("psutil")

    if missing_deps:
        print("[ERROR] DÉPENDANCES MANQUANTES :")
        for dep in missing_deps:
            print(f"  - {dep}")
        print(f"\nInstallez avec : pip install {' '.join(missing_deps)}")
        return False

    return True


def check_database():
    """Vérifie si le fichier de base de données existe."""
    db_path = config.DATABASE_PATH
    if not os.path.exists(db_path):
        print("[ERROR] BASE DE DONNÉES INTROUVABLE :")
        print(f"  - Manquant : {db_path}")
        print("  - Lancez d'abord le parsing des données : python main.py")
        return False

    return True
