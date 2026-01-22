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

    # ========== Backward Compatibility Properties ==========
    # These redirect to config_constants.py for centralized management
    # Kept here for backward compatibility with existing code

    @property
    def MIN_GAMES_THRESHOLD(self) -> int:
        """Redirect to config_constants.analysis_config"""
        from .config_constants import analysis_config

        return analysis_config.MIN_GAMES_THRESHOLD

    @property
    def MIN_GAMES_COMPETITIVE(self) -> int:
        """Redirect to config_constants.analysis_config"""
        from .config_constants import analysis_config

        return analysis_config.MIN_GAMES_COMPETITIVE

    @property
    def MIN_PICKRATE(self) -> float:
        """Redirect to config_constants.analysis_config"""
        from .config_constants import analysis_config

        return analysis_config.MIN_PICKRATE

    @property
    def MIN_MATCHUP_GAMES(self) -> int:
        """Redirect to config_constants.analysis_config"""
        from .config_constants import analysis_config

        return analysis_config.MIN_MATCHUP_GAMES

    @property
    def DEFAULT_RESULTS_COUNT(self) -> int:
        """Redirect to config_constants.ui_config"""
        from .config_constants import ui_config

        return ui_config.DEFAULT_RESULTS_COUNT

    @property
    def SCROLL_DELAY(self) -> float:
        """Redirect to config_constants.scraping_config"""
        from .config_constants import scraping_config

        return scraping_config.SCROLL_DELAY

    @property
    def PAGE_LOAD_DELAY(self) -> float:
        """Redirect to config_constants.scraping_config"""
        from .config_constants import scraping_config

        return scraping_config.PAGE_LOAD_DELAY

    @property
    def OPEN_LOLTHEORY_ON_DRAFT_END(self) -> bool:
        """Redirect to config_constants.draft_config"""
        from .config_constants import draft_config

        return draft_config.OPEN_LOLTHEORY_ON_DRAFT_END

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


@dataclass
class TierListConfig:
    """Configuration for tier list generation and scoring."""

    # ========== Matchup Thresholds ==========
    DECENT_MATCHUP_THRESHOLD: float = 0.0  # Matchup is acceptable (delta2 > 0)
    GOOD_MATCHUP_THRESHOLD: float = 1.0  # Good matchup
    EXCELLENT_MATCHUP_THRESHOLD: float = 2.5  # Excellent matchup

    # ========== Blind Pick Weights (must sum to 1.0) ==========
    BLIND_AVG_WEIGHT: float = 0.5  # Weight for average performance
    BLIND_STABILITY_WEIGHT: float = 0.3  # Weight for stability (low variance)
    BLIND_COVERAGE_WEIGHT: float = 0.2  # Weight for coverage of decent matchups

    # ========== Counter Pick Weights (must sum to 1.0) ==========
    COUNTER_PEAK_WEIGHT: float = 0.5  # Weight for peak impact in good matchups
    COUNTER_VOLATILITY_WEIGHT: float = 0.3  # Weight for high variance (volatility)
    COUNTER_TARGETS_WEIGHT: float = 0.2  # Weight for proportion of viable targets

    # ========== Normalization Ranges ==========
    # For avg_delta2 normalization
    MIN_DELTA2: float = -3.0
    MAX_DELTA2: float = 3.0

    # For variance normalization (adjust based on observed data)
    MAX_VARIANCE: float = 10.0

    # For peak_impact normalization (adjust based on observed data)
    MAX_PEAK_IMPACT: float = 2.0

    # ========== Tier Thresholds (0-100 scale) ==========
    S_TIER_THRESHOLD: float = 75.0  # S-Tier: 75-100
    A_TIER_THRESHOLD: float = 50.0  # A-Tier: 50-75
    B_TIER_THRESHOLD: float = 25.0  # B-Tier: 25-50
    # C-Tier: 0-25


# Global config instances
config = Config()
tierlist_config = TierListConfig()
