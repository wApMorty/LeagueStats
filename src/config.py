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
        # Mode exécutable
        exe_dir = os.path.dirname(sys.executable)
        external_path = os.path.join(exe_dir, relative_path)
        if os.path.exists(external_path):
            return external_path
    
    # Mode développement ou fallback final
    # Chercher d'abord dans data/, puis dans le répertoire racine
    project_root = os.path.dirname(os.path.dirname(__file__))  # Remonter de src/ vers racine
    data_path = os.path.join(project_root, "data", relative_path)
    if os.path.exists(data_path):
        return data_path
    
    dev_path = os.path.join(project_root, relative_path)
    return dev_path

@dataclass
class Config:
    """Configuration settings for the League Stats application."""
    
    # Database settings - utilise le chemin résolu pour PyInstaller
    DATABASE_PATH: str = get_resource_path("db.db")
    
    # Firefox settings
    FIREFOX_PATH: str = os.getenv('FIREFOX_PATH', r'C:\Program Files\Mozilla Firefox\firefox.exe')
    
    # Scraping settings
    CURRENT_PATCH: str = "15.15"
    MIN_GAMES_THRESHOLD: int = 2000
    MIN_GAMES_COMPETITIVE: int = 10000
    MIN_PICKRATE: float = 0.5
    MIN_MATCHUP_GAMES: int = 200
    
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

# Global config instance
config = Config()