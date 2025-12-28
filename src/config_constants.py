"""
Configuration constants for LeagueStats Coach.
Centralized configuration for all hardcoded values across the application.
"""

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class ScrapingConfig:
    """Configuration for web scraping operations."""

    # Cookie acceptance - coordinates hardcoded (TO BE FIXED in Tâche #4)
    COOKIE_CLICK_X: int = 1661
    COOKIE_CLICK_Y: int = 853
    COOKIE_BUTTON_DELAY: float = 0.3

    # Page interaction delays
    PAGE_LOAD_DELAY: float = 2.0
    SCROLL_DELAY: float = 2.0

    # Scraping loop delays
    SCRAPING_DELAY_BETWEEN_CHAMPIONS: int = 1
    RETRY_ATTEMPTS: int = 3
    TIMEOUT: int = 30

    # Scroll position for matchup data
    MATCHUP_SCROLL_Y: int = 1310

    # Scroll distance for horizontal matchup carousel
    MATCHUP_CAROUSEL_SCROLL_X: int = 460

    # Parallel scraping configuration
    DEFAULT_MAX_WORKERS: int = 10  # Optimal for i5-14600KF (20 threads, 50% usage)
    FIREFOX_STARTUP_DELAY: float = 1.0  # Minimal delay for Firefox initialization


@dataclass
class AnalysisConfig:
    """Configuration for champion analysis and tier list generation."""

    # Minimum thresholds for data quality
    MIN_GAMES_THRESHOLD: int = 2000  # Minimum total games for tier lists
    MIN_GAMES_COMPETITIVE: int = 10000  # Higher threshold for competitive
    MIN_PICKRATE: float = 0.5  # Minimum pickrate % for matchup inclusion
    MIN_MATCHUP_GAMES: int = 200  # Minimum games for matchup reliability

    # Tier thresholds (0-100 scale)
    TIER_THRESHOLDS: Dict[str, float] = field(
        default_factory=lambda: {
            "S": 75.0,  # S-Tier: 75-100
            "A": 50.0,  # A-Tier: 50-75
            "B": 25.0,  # B-Tier: 25-50
            "C": 0.0,  # C-Tier: 0-25
        }
    )

    # Blind Pick scoring weights (must sum to 1.0)
    BLIND_AVG_WEIGHT: float = 0.5  # Average performance
    BLIND_STABILITY_WEIGHT: float = 0.3  # Low variance
    BLIND_COVERAGE_WEIGHT: float = 0.2  # Coverage of decent matchups

    # Counter Pick scoring weights (must sum to 1.0)
    COUNTER_PEAK_WEIGHT: float = 0.5  # Peak impact in good matchups
    COUNTER_VOLATILITY_WEIGHT: float = 0.3  # High variance (volatility)
    COUNTER_TARGETS_WEIGHT: float = 0.2  # Proportion of viable targets

    # Matchup quality thresholds
    DECENT_MATCHUP_THRESHOLD: float = 0.0  # delta2 > 0
    GOOD_MATCHUP_THRESHOLD: float = 1.0  # Good matchup
    EXCELLENT_MATCHUP_THRESHOLD: float = 2.5  # Excellent matchup

    # Normalization ranges
    MIN_DELTA2: float = -3.0
    MAX_DELTA2: float = 3.0
    MAX_VARIANCE: float = 10.0
    MAX_PEAK_IMPACT: float = 2.0


@dataclass
class DraftConfig:
    """Configuration for real-time draft monitoring."""

    # Polling and interaction
    POLL_INTERVAL: float = 1.0  # Check draft state every N seconds
    AUTO_HOVER_DELAY: float = 0.5  # Delay before auto-hovering champion

    # Feature toggles
    AUTO_BAN_ENABLED: bool = True
    AUTO_ACCEPT_QUEUE_ENABLED: bool = False
    OPEN_ONETRICKS_ON_DRAFT_END: bool = True

    # Draft phase detection
    READY_CHECK_COOLDOWN: float = 2.0  # Seconds after accepting queue


@dataclass
class UIConfig:
    """Configuration for user interface and display."""

    # Results display
    DEFAULT_RESULTS_COUNT: int = 10
    MAX_RECOMMENDATIONS: int = 5

    # Table formatting
    TABLE_WIDTH: int = 80
    COLUMN_SEPARATOR: str = " | "

    # Console output
    VERBOSE_MODE: bool = False


@dataclass
class XPathConfig:
    """XPath selectors for web scraping (LoLalytics)."""

    # Matchup data paths
    WINRATE_XPATH: str = "/html/body/main/div[5]/div[1]/div[2]/div[3]/div/div/div[1]/div[1]/text()"
    GAMES_XPATH: str = "/html/body/main/div[5]/div[1]/div[2]/div[3]/div/div/div[2]/div[1]/text()"

    # Matchup row base path
    MATCHUP_ROW_BASE: str = "/html/body/main/div[6]/div[1]/div[{index}]/div[2]/div"


@dataclass
class PoolStatisticsConfig:
    """Configuration for pool statistics analysis."""

    # Minimum thresholds for data quality in pool statistics
    MIN_GAMES_THRESHOLD: int = 100  # Minimum total games for sufficient data
    MIN_PICKRATE: float = 0.5  # Minimum pickrate % for matchup inclusion


# Global configuration instances
scraping_config = ScrapingConfig()
analysis_config = AnalysisConfig()
draft_config = DraftConfig()
ui_config = UIConfig()
xpath_config = XPathConfig()
pool_stats_config = PoolStatisticsConfig()
