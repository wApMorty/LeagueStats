#!/usr/bin/env python3
"""
Script pour créer le package ZIP final
"""

import os
import shutil


def create_distribution():
    """Crée le package ZIP pour distribution."""
    release_dir = "LeagueStatsCoach_Release"
    zip_name = "LeagueStatsCoach_Portable.zip"

    if not os.path.exists(release_dir):
        print("Erreur: Dossier de release non trouve. Lancez d'abord build_app.py")
        return False

    # shutil.make_archive écrase l'ancien ZIP et conserve LeagueStatsCoach_Release/
    # comme dossier racine dans l'archive
    shutil.make_archive(zip_name.removesuffix(".zip"), "zip", ".", release_dir)

    zip_size = os.path.getsize(zip_name) / (1024 * 1024)
    print(f"\nPackage ZIP cree: {zip_name}")
    print(f"Taille: {zip_size:.2f} MB")
    print("\nPret pour Gaming House!")

    return True


if __name__ == "__main__":
    create_distribution()
