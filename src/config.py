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

# Champion name normalization for URLs
def normalize_champion_name_for_url(champion_name: str) -> str:
    """
    Normalize champion names for use in LoLalytics URLs.
    
    LoLalytics uses lowercase champion names with specific formatting:
    - Remove spaces and special characters
    - Convert to lowercase
    - Handle special cases like Roman numerals
    """
    # Handle special cases first
    special_cases = {
        'JarvanIV': 'jarvaniv',
        'AurelionSol': 'aurelionsol', 
        'DrMundo': 'drmundo',
        'KhaZix': 'khazix',
        'LeeSin': 'leesin',
        'KaiSa': 'kaisa',
        'MissFortune': 'missfortune',
        'TwistedFate': 'twistedfate',
        'XinZhao': 'xinzhao',
        'ChoGath': 'chogath',
        'KogMaw': 'kogmaw',
        'RekSai': 'reksai',
        'TahmKench': 'tahmkench',
        'VelKoz': 'velkoz',
        'BelVeth': 'belveth',
        'KSante': 'ksante',
        'MasterYi': 'masteryi',
        'MonkeyKing': 'wukong'
    }
    
    # Check if it's a special case
    if champion_name in special_cases:
        return special_cases[champion_name]
    
    # Default normalization: lowercase, remove spaces and special chars
    normalized = champion_name.lower()
    # Remove apostrophes and spaces
    normalized = normalized.replace("'", "").replace(" ", "")
    
    return normalized

def denormalize_champion_name_from_url(url_name: str) -> str:
    """
    Convert a normalized champion name from URL back to the display name.
    
    This is the reverse mapping of normalize_champion_name_for_url.
    Used when parsing champion names from LoLalytics URLs.
    """
    # Reverse mapping from URL names to display names
    url_to_display = {
        'jarvaniv': 'JarvanIV',
        'aurelionsol': 'AurelionSol', 
        'drmundo': 'DrMundo',
        'khazix': 'KhaZix',
        'leesin': 'LeeSin',
        'kaisa': 'KaiSa',
        'missfortune': 'MissFortune',
        'twistedfate': 'TwistedFate',
        'xinzhao': 'XinZhao',
        'chogath': 'ChoGath',
        'kogmaw': 'KogMaw',
        'reksai': 'RekSai',
        'tahmkench': 'TahmKench',
        'velkoz': 'VelKoz',
        'belveth': 'BelVeth',
        'ksante': 'KSante',
        'masteryi': 'MasterYi',
        'wukong': 'MonkeyKing'
    }
    
    # Check if it's a special case that needs conversion
    if url_name.lower() in url_to_display:
        return url_to_display[url_name.lower()]
    
    # For regular champions, capitalize first letter
    return url_name.capitalize()

def normalize_champion_name_for_onetricks(champion_name: str) -> str:
    """
    Normalize champion names for use in Onetricks.gg URLs.
    
    Onericks.gg uses proper case champion names in URLs like:
    /champions/ranking/ChampionName
    """
    # Handle special cases for OneTriks.gg
    special_cases = {
        'JarvanIV': 'JarvanIV',
        'Jarvan IV': 'JarvanIV',
        'AurelionSol': 'AurelionSol',
        'Aurelion Sol': 'AurelionSol', 
        'DrMundo': 'DrMundo',
        'Dr. Mundo': 'DrMundo',
        'KhaZix': 'KhaZix',
        "Kha'Zix": 'KhaZix',
        'LeeSin': 'LeeSin',
        'Lee Sin': 'LeeSin',
        'KaiSa': 'KaiSa',
        "Kai'Sa": 'KaiSa',
        'MissFortune': 'MissFortune',
        'Miss Fortune': 'MissFortune',
        'TwistedFate': 'TwistedFate',
        'Twisted Fate': 'TwistedFate',
        'XinZhao': 'XinZhao',
        'Xin Zhao': 'XinZhao',
        'ChoGath': 'ChoGath',
        "Cho'Gath": 'ChoGath',
        'KogMaw': 'KogMaw',
        "Kog'Maw": 'KogMaw',
        'RekSai': 'RekSai',
        "Rek'Sai": 'RekSai',
        'TahmKench': 'TahmKench',
        'Tahm Kench': 'TahmKench',
        'VelKoz': 'VelKoz',
        "Vel'Koz": 'VelKoz',
        'BelVeth': 'BelVeth',
        "Bel'Veth": 'BelVeth',
        'KSante': 'KSante',
        "K'Sante": 'KSante',
        'MasterYi': 'MasterYi',
        'Master Yi': 'MasterYi',
        'MonkeyKing': 'Wukong',
        'Wukong': 'Wukong'
    }
    
    # Check if it's a special case
    if champion_name in special_cases:
        return special_cases[champion_name]
    
    # Default: remove spaces and apostrophes, keep proper case
    normalized = champion_name.replace(" ", "").replace("'", "")
    return normalized

# Global config instance
config = Config()