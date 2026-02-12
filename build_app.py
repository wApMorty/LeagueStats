#!/usr/bin/env python3
"""
Script de build simple pour la nouvelle architecture
"""

import os
import shutil
import subprocess
import sys

def main():
    """Build l'application avec la nouvelle structure."""
    print("LEAGUE STATS COACH - BUILD (nouvelle architecture)")
    print("="*60)
    
    # Nettoie les anciens builds
    for dir_name in ['dist', '__pycache__', 'build/build_config']:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print(f"Nettoye: {dir_name}")
    
    # Build avec PyInstaller using LeagueStatsCoach.spec
    # Le .spec contient la configuration PostgreSQL Direct (asyncpg binaries)
    print("\nConstruction de l'executable avec LeagueStatsCoach.spec...")

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--clean',
        'LeagueStatsCoach.spec'
    ]
    
    try:
        result = subprocess.run(cmd, check=True)
        print("Build executable reussi!")
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors du build: {e}")
        return False
    
    # Créer le dossier de release
    release_dir = "LeagueStatsCoach_Release"
    if os.path.exists(release_dir):
        shutil.rmtree(release_dir)
    
    os.makedirs(release_dir)
    
    # Copier l'exécutable
    exe_path = "dist/LeagueStatsCoach.exe"
    if os.path.exists(exe_path):
        shutil.copy2(exe_path, f"{release_dir}/LeagueStatsCoach.exe")
        print(f"Executable copie dans {release_dir}/")
    else:
        print("Erreur: executable non trouve")
        return False
    
    # Copier la base de données explicitement à côté de l'exe
    if os.path.exists("data/db.db"):
        shutil.copy2("data/db.db", f"{release_dir}/db.db")
        print("Base de donnees copiee (data/db.db -> release/db.db)")
    else:
        print("ATTENTION: data/db.db introuvable - l'exe ne fonctionnera pas!")
        return False
    
    # Copier la documentation
    doc_files = [
        ('docs/CLAUDE.md', 'CLAUDE.md'),
        ('README.md', 'README.md')
    ]
    for src, dst in doc_files:
        if os.path.exists(src):
            shutil.copy2(src, f"{release_dir}/{dst}")
            print(f"{dst} copie")
    
    # Créer instructions
    instructions = """LEAGUE STATS COACH - INSTRUCTIONS

INSTALLATION:
- Aucune installation requise
- Decompresser tous les fichiers dans un dossier

PREREQUIS:
- League of Legends installe
- Firefox browser installe

UTILISATION:
- Double-cliquer sur LeagueStatsCoach.exe

PREMIERE UTILISATION:
1. Option 2: "Update Champion Data" 
2. Option 3: "Parse Match Statistics"
3. Option 1: "Real-time Draft Coach"

FONCTIONNALITES:
- Draft Coach temps reel avec pools multiples
- Team Builder avec pools elargis
- Parsing automatique des statistiques

Version: 1.0.0 - Architecture reorganisee
"""
    
    with open(f"{release_dir}/INSTRUCTIONS.txt", 'w', encoding='utf-8') as f:
        f.write(instructions)
    
    print("Instructions creees")
    print("\n" + "="*60)
    print("BUILD REUSSI!")
    print("="*60)
    print(f"Package pret dans: {release_dir}/")
    
    return True

if __name__ == "__main__":
    main()