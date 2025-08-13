#!/usr/bin/env python3
"""
Script pour créer le package ZIP final
"""

import os
import zipfile

def create_distribution():
    """Crée le package ZIP pour distribution."""
    release_dir = "LeagueStatsCoach_Release"
    zip_name = "LeagueStatsCoach_Portable.zip"
    
    if not os.path.exists(release_dir):
        print("Erreur: Dossier de release non trouve. Lancez d'abord build_app.py")
        return False
    
    # Supprime l'ancien ZIP
    if os.path.exists(zip_name):
        os.remove(zip_name)
    
    # Crée le ZIP
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(release_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, os.path.dirname(release_dir))
                zipf.write(file_path, arcname)
                print(f"Ajoute: {arcname}")
    
    # Statistiques
    zip_size = os.path.getsize(zip_name) / (1024 * 1024)
    
    print(f"\nPackage ZIP cree: {zip_name}")
    print(f"Taille: {zip_size:.1f} MB")
    print("\nPret pour Gaming House!")
    
    return True

if __name__ == "__main__":
    create_distribution()