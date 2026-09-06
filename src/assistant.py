"""
Main Assistant class - Coordinator for champion analysis and recommendations.

This is the new modular version that delegates to specialized modules while
maintaining backward compatibility with the original API.
"""

from typing import Dict, List, Optional

from .config import config
from .config_constants import analysis_config, draft_config
from .db import Database
from .models import Matchup

# Import specialized modules
from .analysis.scoring import ChampionScorer
from .draft.scoring import DraftScorer
from .analysis.tier_list import TierListGenerator
from .analysis.recommendations import RecommendationEngine
from .analysis.team_analysis import TeamAnalyzer
from .analysis.champion_scores import GlobalScoreCalculator
from .analysis.ban_recommendations import BanRecommender
from .analysis.trio_weights import AdaptiveWeightCalculator
from .analysis.trio_holistic import HolisticTrioFinder
from .analysis.trio_tactics import TrioTacticsReporter
from .analysis.trio_counterpick import CounterpickTrioFinder
from .analysis.matchup_cache import MatchupCache
from .assistant_trio_facade import _TrioFacadeMixin
from .utils.champion_utils import (
    validate_champion_name,
    validate_champion_data,
    validate_champion_pool,
    select_champion_pool,
    select_extended_champion_pool,
    print_champion_list,
)


class Assistant(_TrioFacadeMixin):
    """
    Main coordinator for League of Legends draft analysis.

    Delegates to specialized modules while maintaining backward compatibility
    with the original monolithic API.

    Data access goes through a local SQLite ``Database`` — the only supported
    backend since the remote PostgreSQL/Neon layer was decommissioned (H2).
    """

    def __init__(self, db: Optional[Database] = None, verbose: bool = False) -> None:
        """
        Initialize Assistant and all sub-components.

        Args:
            db: Optional Database instance to use for data access. Defaults to
                a Database on ``config.DATABASE_PATH``. Connected on init.
            verbose: Enable verbose logging

        Examples:
            >>> # Default: local SQLite at config.DATABASE_PATH
            >>> assistant = Assistant()

            >>> # Explicit database (e.g. a test fixture)
            >>> from src.db import Database
            >>> assistant = Assistant(Database("data/db.db"))
        """
        self.MIN_GAMES = analysis_config.MIN_GAMES_THRESHOLD
        self.verbose = verbose

        self.db = db if db is not None else Database(config.DATABASE_PATH)
        self.db.connect()

    @property
    def db(self) -> Database:
        return self._db

    @db.setter
    def db(self, value: Database) -> None:
        """Rebranche self._db et reconstruit tous les composants spécialisés.

        Rebrancher self.db (fixtures de test, ex. tests/test_ban_recommendations.py)
        sans reconstruire scorer/ban_recommender/etc. laisserait ces composants
        pointer vers l'ancienne base (souvent celle de production) : le setter
        garantit qu'un seul point de vérité (_init_components) les tient à jour.
        """
        self._db = value
        self._init_components()

    def _init_components(self) -> None:
        """(Re)initialise les composants spécialisés à partir de self.db/self.verbose."""
        self.scorer = ChampionScorer(self._db, verbose=self.verbose)
        # DraftScorer blends matchup + synergy the same way the Live Coach does
        # (src/draft_monitor.py). display_name=None is safe here: name-based
        # callers (calculate_synergy_score_by_names, final_score) never touch it —
        # only the id-based calculate_synergy_score, unused outside the Live Coach.
        self.draft_scorer = DraftScorer(
            self, None, draft_config.DEFAULT_SYNERGY_WEIGHT, verbose=self.verbose
        )
        self.tier_list_gen = TierListGenerator(self._db, self.scorer)
        self.recommender = RecommendationEngine(self._db, self.scorer, self.draft_scorer)
        self.team_analyzer = TeamAnalyzer(self._db, self.scorer)
        self.global_scores = GlobalScoreCalculator(self._db, self.scorer, verbose=self.verbose)
        self.ban_recommender = BanRecommender(self._db, verbose=self.verbose)
        self.trio_weights = AdaptiveWeightCalculator(self._db, verbose=self.verbose)
        self.trio_finder = HolisticTrioFinder(self._db, self.trio_weights, verbose=self.verbose)
        self.trio_tactics = TrioTacticsReporter(self._db, verbose=self.verbose)
        self.trio_counterpick = CounterpickTrioFinder(
            self._db, self.trio_tactics, verbose=self.verbose
        )
        self.matchup_cache = MatchupCache(self._db)

    def close(self) -> None:
        """Close database connection."""
        self.db.close()

    # ==================== Cache Management (Performance) ====================
    # Delegated to analysis.matchup_cache.MatchupCache. The five private
    # attributes below stay proxied as properties: tests/test_assistant_cache.py
    # reads AND reassigns them directly on the Assistant instance (not just
    # via warm_cache()/clear_cache()), so a plain facade method wouldn't be
    # enough — get/set must reach the same MatchupCache instance every time.

    def warm_cache(self, champion_pool: List[str]) -> None:
        """Pre-load matchups for all champions in pool into cache (bidirectional)."""
        self.matchup_cache.warm(champion_pool)

    def clear_cache(self) -> None:
        """Clear matchup caches (both direct and reverse) and disable caching."""
        self.matchup_cache.clear()

    def print_cache_stats(self) -> None:
        """Print cache performance statistics (bidirectional cache)."""
        self.matchup_cache.print_stats()

    def get_cached_matchups(self, champion: str) -> List[tuple]:
        """Get matchups from cache if available, otherwise fetch from database."""
        return self.matchup_cache.get_matchups(champion)

    def get_cached_matchup_delta2(self, champion: str, enemy: str) -> Optional[float]:
        """Get delta2 for a specific matchup using bidirectional cache."""
        return self.matchup_cache.get_delta2(champion, enemy)

    def get_matchups_for_draft(self, champion: str, lane: Optional[str] = None) -> List[Matchup]:
        """Get matchups for draft analysis (optimized with cache support).

        lane: None = all lanes combined (unchanged default). Given = restrict
              to that lane, so a multi-lane champion's off-role matchups don't
              dilute the score/volume for the lane actually being played.
        """
        return self.matchup_cache.get_matchups_for_draft(champion, lane=lane)

    def _convert_draft_matchups_to_standard(self, draft_matchups: List) -> List[Matchup]:
        """Convert draft format (4 cols) to Matchup objects for scoring methods."""
        return self.matchup_cache._convert_draft_matchups_to_standard(draft_matchups)

    @property
    def _matchups_cache(self) -> Dict[str, List[tuple]]:
        return self.matchup_cache._matchups_cache

    @_matchups_cache.setter
    def _matchups_cache(self, value: Dict[str, List[tuple]]) -> None:
        self.matchup_cache._matchups_cache = value

    @property
    def _reverse_cache(self) -> Dict[str, List[tuple]]:
        return self.matchup_cache._reverse_cache

    @_reverse_cache.setter
    def _reverse_cache(self, value: Dict[str, List[tuple]]) -> None:
        self.matchup_cache._reverse_cache = value

    @property
    def _cache_enabled(self) -> bool:
        return self.matchup_cache._cache_enabled

    @_cache_enabled.setter
    def _cache_enabled(self, value: bool) -> None:
        self.matchup_cache._cache_enabled = value

    @property
    def _cache_hits(self) -> int:
        return self.matchup_cache._cache_hits

    @_cache_hits.setter
    def _cache_hits(self, value: int) -> None:
        self.matchup_cache._cache_hits = value

    @property
    def _cache_misses(self) -> int:
        return self.matchup_cache._cache_misses

    @_cache_misses.setter
    def _cache_misses(self, value: int) -> None:
        self.matchup_cache._cache_misses = value

    # ==================== Champion Pool Selection ====================
    # Delegated to utils.champion_utils

    def select_champion_pool(self) -> List[str]:
        """Interactive pool selection for the user."""
        return select_champion_pool()

    def select_extended_champion_pool(self) -> List[str]:
        """Interactive extended pool selection for Team Builder analysis."""
        return select_extended_champion_pool()

    def validate_champion_name(self, name: str) -> Optional[str]:
        """Validate and normalize champion name with fuzzy matching."""
        return validate_champion_name(name)

    def _validate_champion_data(self, champion: str, lane: Optional[str] = None) -> tuple:
        """Validate if a champion has sufficient data in database."""
        return validate_champion_data(self.db, champion, lane=lane)

    def _validate_champion_pool(
        self, champion_pool: List[str], lane: Optional[str] = None
    ) -> tuple:
        """Validate entire champion pool and return viable champions."""
        return validate_champion_pool(self.db, champion_pool, lane=lane)

    def print_champion_list(self, champion_list: List[tuple]) -> None:
        """Print formatted champion list."""
        print_champion_list(champion_list)

    # ==================== Scoring Methods ====================
    # Delegated to analysis.scoring.ChampionScorer

    def score_against_team(
        self,
        matchups: List[tuple],
        team: List[str],
        champion_name: str = None,
        banned_champions: List[str] = None,
        lane: Optional[str] = None,
        enemy_lanes: Optional[dict] = None,
        player_lane: Optional[str] = None,
    ) -> float:
        """Calculate advantage against a team composition."""
        return self.scorer.score_against_team(
            matchups,
            team,
            champion_name,
            banned_champions,
            lane=lane,
            enemy_lanes=enemy_lanes,
            player_lane=player_lane,
        )

    def effective_model_version(self) -> str:
        """SPEC-11 : analysis_config.MODEL_VERSION, suffixé quand la
        pondération par lane restante (self.scorer) est active. À utiliser
        au lieu de la constante brute partout où une prédiction est
        journalisée, pour que scripts/calibrate_model.py ne mélange jamais
        les deux régimes de scoring."""
        return self.scorer.effective_model_version()

    def score_with_synergy(
        self,
        matchups: List[tuple],
        enemy_team: List[str],
        ally_team: List[str],
        champion_name: str,
        banned_champions: List[str] = None,
        lane: Optional[str] = None,
    ) -> float:
        """Bidirectional matchup score against enemy_team, blended with a
        synergy score from ally_team — the same matchup+synergy blend the
        Live Coach uses (DraftScorer.final_score), applied here to plain
        champion names for callers with no LCU champion IDs (Tournament Coach).

        Args:
            lane: Lane optionnelle transmise au scoring matchup/synergie.
                  None = agrégation toutes lanes, comportement inchangé.
        """
        matchup_score = self.scorer.score_against_team(
            matchups, enemy_team, champion_name, banned_champions, lane=lane
        )
        synergy_score = self.draft_scorer.calculate_synergy_score_by_names(
            champion_name, ally_team, lane=lane
        )
        return self.draft_scorer.final_score(matchup_score, synergy_score)

    def _calculate_team_winrate(self, individual_winrates: List[float]) -> dict:
        """Calculate team win probability from individual champion winrates."""
        return self.scorer.calculate_team_winrate(individual_winrates)

    # ==================== Tier List Generation ====================
    # Delegated to analysis.tier_list.TierListGenerator

    def tierlist_delta2(self, champion_list: List[str]) -> List[tuple]:
        """Generate tier list ranked by average delta2."""
        return self.tier_list_gen.generate_by_delta2(champion_list)

    def generate_tier_list(
        self, champion_pool: List[str], analysis_type: str = "blind_pick", lane: str = None
    ) -> List[dict]:
        """
        Generate tier list with S/A/B/C classification using global normalization.

        lane: Optional lane filter (scraping_config.LANES value, e.g. "middle").
              None = toutes lanes agrégées (comportement historique).

        Delegates to TierListGenerator for actual implementation.
        """
        return self.tier_list_gen.generate_tier_list(
            champion_pool, analysis_type, lane=lane, verbose=self.verbose
        )

    # ==================== Recommendations ====================
    # Delegated to analysis.recommendations.RecommendationEngine
    # NOTE: draft() is NOT delegated — the active implementation lives in the
    # "Draft & Competitive Methods" section below (a shadowed duplicate that
    # delegated to recommender.draft_simple was removed; pylint E0102).

    def _calculate_and_display_recommendations(
        self,
        enemy_team: List[str],
        ally_team: List[str],
        nb_results: int,
        champion_pool: List[str] = None,
        banned_champions: List[str] = None,
        lane: Optional[str] = None,
    ) -> List[tuple]:
        """Calculate champion recommendations and display top results."""
        return self.recommender.calculate_and_display_recommendations(
            enemy_team, ally_team, nb_results, champion_pool, banned_champions, lane=lane
        )

    # ==================== Team Analysis ====================
    # Delegated to analysis.team_analysis.TeamAnalyzer

    # ==================== Global Score Calculation ====================

    def calculate_global_scores(self) -> int:
        """
        Calculate and save scores for all champions in the database, both as a
        toutes-lanes aggregate and scoped to each lane they're played in.

        Should be called after parsing/updating matchup data.

        Returns:
            Number of (champion, lane) rows scored and saved
        """
        return self.global_scores.calculate_all()

    # ==================== Ban Recommendations ====================

    def get_ban_recommendations(
        self, champion_pool: List[str], num_bans: int = 5, lane: Optional[str] = None
    ) -> List[tuple]:
        """
        Get ban recommendations against a specific champion pool using reverse lookup.

        For each potential enemy pick, finds your BEST response from your pool.
        Prioritizes banning enemies where even your best response is insufficient.

        Returns:
            List of tuples (enemy_name, threat_score, best_response_delta2,
                           best_response_champion, matchups_count)
            Sorted by threat_score (descending)
        """
        return self.ban_recommender.get_ban_recommendations(champion_pool, num_bans, lane=lane)

    def precalculate_pool_bans(
        self, pool_name: str, champion_pool: List[str], lane: Optional[str] = None
    ) -> bool:
        """
        Pre-calculate and store ban recommendations for a champion pool in database.

        Should be called during data updates.

        Returns:
            True if successful, False otherwise
        """
        return self.ban_recommender.precalculate_pool_bans(pool_name, champion_pool, lane=lane)

    def precalculate_all_custom_pool_bans(self) -> Dict[str, int]:
        """
        Pre-calculate ban recommendations for all custom (user-created) pools.

        System pools are skipped because they're too large for meaningful ban calculations
        and aren't typically used for draft.

        Returns:
            Dictionary mapping pool names to number of bans calculated
        """
        return self.ban_recommender.precalculate_all_custom_pool_bans()
