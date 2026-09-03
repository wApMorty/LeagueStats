import os
import sys
from dataclasses import dataclass
from typing import Optional


def get_resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller."""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
        internal_path = os.path.join(base_path, relative_path)

        # Si le fichier existe dans _MEIPASS, l'utiliser
        if os.path.exists(internal_path):
            return internal_path
    except AttributeError:
        pass

    # Fallback: chercher dans le répertoire de l'exécutable ou développement
    if hasattr(sys, "frozen"):
        # Mode exécutable - fichier à côté de l'exe
        exe_dir = os.path.dirname(sys.executable)
        external_path = os.path.join(exe_dir, relative_path)
        if os.path.exists(external_path):
            return external_path

    # Mode développement - chercher dans data/ en priorité
    project_root = os.path.dirname(os.path.dirname(__file__))  # Remonter de src/ vers racine

    # Pour db.db, toujours chercher dans data/ en développement
    if relative_path == "db.db":
        data_path = os.path.join(project_root, "data", "db.db")
        if os.path.exists(data_path):
            return data_path
        # Si data/db.db n'existe pas, le créer à cet emplacement
        return data_path

    # Pour les autres fichiers, chercher normalement
    data_path = os.path.join(project_root, "data", relative_path)
    if os.path.exists(data_path):
        return data_path

    # Fallback final
    dev_path = os.path.join(project_root, relative_path)
    return dev_path


@dataclass
class Config:
    """Configuration settings for the League Stats application."""

    # Database settings - utilise le chemin résolu pour PyInstaller
    DATABASE_PATH: str = get_resource_path("db.db")

    # Firefox settings
    FIREFOX_PATH: str = os.getenv("FIREFOX_PATH", r"C:\Program Files\Mozilla Firefox\firefox.exe")

    # Brave settings
    BRAVE_PATH: str = os.getenv(
        "BRAVE_PATH", r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
    )

    # Scraping settings
    # "14" = 14 derniers jours (évite effets de bord lors de sortie de patch + pas besoin de mettre à jour)
    CURRENT_PATCH: str = "14"

    # Tier lolalytics utilisé pour toutes les URLs de scraping (paramètre "tier=").
    # "master_plus" = Master + Grandmaster + Challenger.
    LOLALYTICS_TIER: str = "master_plus"

    @classmethod
    def get_firefox_path(cls) -> str:
        """Get Firefox path with fallback options."""
        paths = [
            os.getenv("FIREFOX_PATH"),
            r"C:\Program Files\Mozilla Firefox\firefox.exe",
            r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        ]

        for path in paths:
            if path and os.path.exists(path):
                return path

        raise FileNotFoundError(
            "Firefox executable not found. Please install Firefox or set FIREFOX_PATH environment variable."
        )

    @classmethod
    def get_brave_path(cls) -> str:
        """Get Brave browser path with fallback options."""
        paths = [
            os.getenv("BRAVE_PATH"),
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Users\{}\AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe".format(
                os.environ.get("USERNAME", "")
            ),
        ]

        for path in paths:
            if path and os.path.exists(path):
                return path

        raise FileNotFoundError(
            "Brave browser executable not found. Please install Brave or set BRAVE_PATH environment variable."
        )


# Global config instance (analysis/scoring constants live in config_constants.py)
config = Config()
