#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de nettoyage des fichiers de base de données obsolètes.
ATTENTION: Ce script supprimera définitivement les fichiers db.db obsolètes.
"""

import os
import sys
import shutil
from datetime import datetime

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def cleanup_database_files():
    """Nettoie les fichiers de base de données obsolètes."""
    print("="*60)
    print("NETTOYAGE DES FICHIERS DATABASE OBSOLÈTES")
    print("="*60)

    # Chemin légitime de la base de données
    legitimate_db = "data/db.db"

    # Fichiers à supprimer
    obsolete_files = [
        "db.db",                                  # Reliquat à la racine
        "db_2.db",                                # Backup obsolète
        "LeagueStatsCoach_Release/db.db",         # Build ancien
    ]

    # Dossiers de build à nettoyer
    build_dirs = [
        "build",
        "dist",
        "__pycache__",
        "LeagueStatsCoach_Release"
    ]

    print(f"\n✅ Base de données légitime: {legitimate_db}")
    if os.path.exists(legitimate_db):
        size_mb = os.path.getsize(legitimate_db) / (1024 * 1024)
        mod_time = datetime.fromtimestamp(os.path.getmtime(legitimate_db))
        print(f"   Taille: {size_mb:.2f} MB")
        print(f"   Modifié: {mod_time.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        print("   ⚠️ ATTENTION: Base de données légitime introuvable!")
        response = input("   Continuer quand même? (y/N): ")
        if response.lower() != 'y':
            print("Annulé.")
            return

    print("\n🗑️ Fichiers obsolètes à supprimer:")
    files_to_remove = []
    for filepath in obsolete_files:
        if os.path.exists(filepath):
            size_mb = os.path.getsize(filepath) / (1024 * 1024)
            print(f"   - {filepath} ({size_mb:.2f} MB)")
            files_to_remove.append(filepath)
        else:
            print(f"   - {filepath} (déjà absent)")

    print("\n📁 Dossiers de build à nettoyer:")
    dirs_to_remove = []
    for dirpath in build_dirs:
        if os.path.exists(dirpath):
            print(f"   - {dirpath}/")
            dirs_to_remove.append(dirpath)
        else:
            print(f"   - {dirpath}/ (déjà absent)")

    if not files_to_remove and not dirs_to_remove:
        print("\n✅ Rien à nettoyer - le projet est déjà propre!")
        return

    print("\n" + "="*60)
    response = input("Confirmer la suppression? (y/N): ")

    if response.lower() != 'y':
        print("Nettoyage annulé.")
        return

    # Supprimer les fichiers obsolètes
    for filepath in files_to_remove:
        try:
            os.remove(filepath)
            print(f"✅ Supprimé: {filepath}")
        except Exception as e:
            print(f"❌ Erreur lors de la suppression de {filepath}: {e}")

    # Supprimer les dossiers de build
    for dirpath in dirs_to_remove:
        try:
            shutil.rmtree(dirpath)
            print(f"✅ Supprimé: {dirpath}/")
        except Exception as e:
            print(f"❌ Erreur lors de la suppression de {dirpath}: {e}")

    print("\n" + "="*60)
    print("✅ NETTOYAGE TERMINÉ")
    print("="*60)
    print(f"\n📊 Structure correcte:")
    print(f"   data/db.db        ← Base de données principale")
    print(f"   src/              ← Code source")
    print(f"   lol_coach.py      ← Point d'entrée")
    print(f"   build_app.py      ← Script de build")

if __name__ == "__main__":
    cleanup_database_files()
