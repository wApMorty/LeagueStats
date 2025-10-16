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
    if hasattr(sys, 'frozen'):
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
    FIREFOX_PATH: str = os.getenv('FIREFOX_PATH', r'C:\Program Files\Mozilla Firefox\firefox.exe')

    # Brave settings
    BRAVE_PATH: str = os.getenv('BRAVE_PATH', r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe')

    # Draft completion browser opening
    OPEN_ONETRICKS_ON_DRAFT_END: bool = True

    # Scraping settings
    CURRENT_PATCH: str = "15.17"
    MIN_GAMES_THRESHOLD: int = 2000  # Minimum total games for a champion to be included in tier lists
    MIN_GAMES_COMPETITIVE: int = 10000  # Higher threshold for competitive analysis
    MIN_PICKRATE: float = 0.5  # Minimum pickrate percentage for matchup inclusion
    MIN_MATCHUP_GAMES: int = 200  # Minimum games for individual matchup reliability

    # UI settings
    DEFAULT_RESULTS_COUNT: int = 10

    # Delays for web scraping (in seconds)
    SCROLL_DELAY: float = 2.0
    PAGE_LOAD_DELAY: float = 2.0

    @classmethod
    def get_firefox_path(cls) -> str:
        """Get Firefox path with fallback options."""
        paths = [
            os.getenv('FIREFOX_PATH'),
            r'C:\Program Files\Mozilla Firefox\firefox.exe',
            r'C:\Program Files (x86)\Mozilla Firefox\firefox.exe',
        ]
        
        for path in paths:
            if path and os.path.exists(path):
                return path
        
        raise FileNotFoundError("Firefox executable not found. Please install Firefox or set FIREFOX_PATH environment variable.")
    
    @classmethod
    def get_brave_path(cls) -> str:
        """Get Brave browser path with fallback options."""
        paths = [
            os.getenv('BRAVE_PATH'),
            r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe',
            r'C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe',
            r'C:\Users\{}\AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe'.format(os.environ.get('USERNAME', '')),
        ]
        
        for path in paths:
            if path and os.path.exists(path):
                return path
        
        raise FileNotFoundError("Brave browser executable not found. Please install Brave or set BRAVE_PATH environment variable.")

@dataclass
class TierListConfig:
    """Configuration for tier list generation and scoring."""

    # ========== Matchup Thresholds ==========
    DECENT_MATCHUP_THRESHOLD: float = 0.0      # Matchup is acceptable (delta2 > 0)
    GOOD_MATCHUP_THRESHOLD: float = 1.0        # Good matchup
    EXCELLENT_MATCHUP_THRESHOLD: float = 2.5   # Excellent matchup

    # ========== Blind Pick Weights (must sum to 1.0) ==========
    BLIND_AVG_WEIGHT: float = 0.5              # Weight for average performance
    BLIND_STABILITY_WEIGHT: float = 0.3        # Weight for stability (low variance)
    BLIND_COVERAGE_WEIGHT: float = 0.2         # Weight for coverage of decent matchups

    # ========== Counter Pick Weights (must sum to 1.0) ==========
    COUNTER_PEAK_WEIGHT: float = 0.5           # Weight for peak impact in good matchups
    COUNTER_VOLATILITY_WEIGHT: float = 0.3     # Weight for high variance (volatility)
    COUNTER_TARGETS_WEIGHT: float = 0.2        # Weight for proportion of viable targets

    # ========== Normalization Ranges ==========
    # For avg_delta2 normalization
    MIN_DELTA2: float = -3.0
    MAX_DELTA2: float = 3.0

    # For variance normalization (adjust based on observed data)
    MAX_VARIANCE: float = 10.0

    # For peak_impact normalization (adjust based on observed data)
    MAX_PEAK_IMPACT: float = 2.0

    # ========== Tier Thresholds (0-100 scale) ==========
    S_TIER_THRESHOLD: float = 75.0             # S-Tier: 75-100
    A_TIER_THRESHOLD: float = 50.0             # A-Tier: 50-75
    B_TIER_THRESHOLD: float = 25.0             # B-Tier: 25-50
    # C-Tier: 0-25

# Global config instances
config = Config()
tierlist_config = TierListConfig()