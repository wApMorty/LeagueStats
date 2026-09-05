import sqlite3
from sqlite3 import Error
from typing import Dict, List, Optional, Tuple, Union

from .config_constants import analysis_config
from .models import Matchup, MatchupDraft, Synergy
from .repositories.champions import ChampionsRepository
from .repositories.champion_scores import ChampionScoresRepository
from .repositories.matchups import MatchupsRepository
from .repositories.matchups_draft import MatchupsDraftRepository
from .repositories.meta import MetaRepository
from .repositories.pool_bans import PoolBansRepository
from .repositories.predictions import PredictionsRepository
from .repositories.synergies import SynergiesRepository


class Database:
    """Façade de la couche données SQLite.

    Délègue à un repository par domaine de table (``src/repositories/``) :
    ``ChampionsRepository``, ``MatchupsRepository``, ``SynergiesRepository``,
    ``ChampionScoresRepository``, ``PoolBansRepository``,
    ``PredictionsRepository``, ``MetaRepository``. Extraction verbatim
    (dette de code, TODO.md P4) : la surface publique et le comportement de
    ``Database`` n'ont pas changé, seule l'implémentation a été répartie.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self.connection = None

    def connect(self) -> None:
        try:
            self.connection = sqlite3.connect(self.path)
            # Enable foreign key constraints
            self.connection.execute("PRAGMA foreign_keys = ON")
            print("Connection to SQLite DB successful")
            self._init_repositories()
            # Ensure indexes exist for optimal performance (only if tables exist)
            try:
                self.create_database_indexes()
            except Error:
                # Tables might not exist yet, indexes will be created when tables are initialized
                pass
        except Error as e:
            print(f"The error '{e}' occurred")

    def _init_repositories(self) -> None:
        """(Re)initialise les repositories à partir de self.connection."""
        self._champions = ChampionsRepository(self)
        self._matchups = MatchupsRepository(self)
        self._matchups_draft = MatchupsDraftRepository(self)
        self._synergies = SynergiesRepository(self)
        self._champion_scores = ChampionScoresRepository(self)
        self._pool_bans = PoolBansRepository(self)
        self._predictions = PredictionsRepository(self)
        self._meta = MetaRepository(self)

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()

    def create_database_indexes(self) -> None:
        """Create database indexes for performance optimization."""
        cursor = self.connection.cursor()

        try:
            # Get existing indexes
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
            existing_indexes = {row[0] for row in cursor.fetchall()}

            # Check if tables exist before creating indexes
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('champions', 'matchups')"
            )
            existing_tables = {row[0] for row in cursor.fetchall()}

            created_indexes = []

            if "champions" in existing_tables:
                # Index on champions.name for faster name lookups
                if "idx_champions_name" not in existing_indexes:
                    cursor.execute("CREATE INDEX idx_champions_name ON champions(name)")
                    created_indexes.append("idx_champions_name")

                # Index insensible à la casse : les jointures filtrent sur
                # `c1.name = ? COLLATE NOCASE`, que idx_champions_name ne peut
                # pas servir (SPEC-06 C4 — 6,68 ms/appel -> 0,11 ms/appel).
                if "idx_champions_name_nocase" not in existing_indexes:
                    cursor.execute(
                        "CREATE INDEX idx_champions_name_nocase "
                        "ON champions(name COLLATE NOCASE)"
                    )
                    created_indexes.append("idx_champions_name_nocase")

            if "matchups" in existing_tables:
                # Indexes on matchups table for faster queries
                if "idx_matchups_champion" not in existing_indexes:
                    cursor.execute("CREATE INDEX idx_matchups_champion ON matchups(champion)")
                    created_indexes.append("idx_matchups_champion")

                if "idx_matchups_enemy" not in existing_indexes:
                    cursor.execute("CREATE INDEX idx_matchups_enemy ON matchups(enemy)")
                    created_indexes.append("idx_matchups_enemy")

                if "idx_matchups_pickrate" not in existing_indexes:
                    cursor.execute("CREATE INDEX idx_matchups_pickrate ON matchups(pickrate)")
                    created_indexes.append("idx_matchups_pickrate")

                # Composite index for common query pattern (champion + pickrate filter)
                if "idx_matchups_champion_pickrate" not in existing_indexes:
                    cursor.execute(
                        "CREATE INDEX idx_matchups_champion_pickrate ON matchups(champion, pickrate)"
                    )
                    created_indexes.append("idx_matchups_champion_pickrate")

                # Composite index for reverse lookups (enemy + pickrate)
                if "idx_matchups_enemy_pickrate" not in existing_indexes:
                    cursor.execute(
                        "CREATE INDEX idx_matchups_enemy_pickrate ON matchups(enemy, pickrate)"
                    )
                    created_indexes.append("idx_matchups_enemy_pickrate")

                # Lane-aware composite indexes (Horizon 1 — multi-lane pipeline).
                # Only created if the lane column exists (post-migration b7e41c9a3f02).
                cursor.execute("PRAGMA table_info(matchups)")
                matchup_columns = {col[1] for col in cursor.fetchall()}
                if "lane" in matchup_columns:
                    if "idx_matchups_champion_lane_pickrate" not in existing_indexes:
                        cursor.execute(
                            "CREATE INDEX idx_matchups_champion_lane_pickrate "
                            "ON matchups(champion, lane, pickrate)"
                        )
                        created_indexes.append("idx_matchups_champion_lane_pickrate")
                    if "idx_matchups_enemy_lane_pickrate" not in existing_indexes:
                        cursor.execute(
                            "CREATE INDEX idx_matchups_enemy_lane_pickrate "
                            "ON matchups(enemy, lane, pickrate)"
                        )
                        created_indexes.append("idx_matchups_enemy_lane_pickrate")

                    # SPEC-03 B8: uniqueness per (champion, enemy, lane).
                    # init_matchups_table() rebuilds the table with DROP/CREATE,
                    # bypassing Alembic entirely, so this index must also be
                    # (re)created here or a full rescrape would lose it.
                    if "idx_matchups_unique" not in existing_indexes:
                        cursor.execute(
                            "CREATE UNIQUE INDEX idx_matchups_unique "
                            "ON matchups(champion, enemy, lane)"
                        )
                        created_indexes.append("idx_matchups_unique")

            self.connection.commit()

            # Only log if indexes were actually created
            if created_indexes:
                print("[INFO] Created database indexes for performance optimization:")
                for idx_name in created_indexes:
                    print(f"[INFO]   - {idx_name}")

        except Error as e:
            print(f"[WARNING] Error creating indexes: {e}")

    def execute_query(self, query: str, commit: bool = True) -> None:
        cursor = self.connection.cursor()
        try:
            cursor.execute(query)
            if commit:
                self.connection.commit()
            print(f"Query executed successfully : {query}")
        except Error as e:
            print(f"The error '{e}' occurred")

    # ========== Champions ==========

    def init_champion_table(self) -> None:
        self._champions.init_champion_table()

    def get_champion_id(self, champion: str) -> int:
        return self._champions.get_champion_id(champion)

    def get_champion_by_id(self, id: int) -> str:
        return self._champions.get_champion_by_id(id)

    def get_champion_base_winrate(self, champion_name: str) -> float:
        return self._champions.get_champion_base_winrate(champion_name)

    def update_champions_from_riot_api(self) -> bool:
        return self._champions.update_champions_from_riot_api()

    def create_riot_champions_table(self) -> bool:
        return self._champions.create_riot_champions_table()

    def get_all_champion_names(self) -> Dict[int, str]:
        return self._champions.get_all_champion_names()

    def build_champion_cache(self) -> Dict[str, int]:
        return self._champions.build_champion_cache()

    def save_champion_lane_distribution(
        self, champion_id: int, distribution: Dict[str, float]
    ) -> None:
        self._champions.save_champion_lane_distribution(champion_id, distribution)

    def get_all_champion_lane_distributions(self) -> Dict[int, Dict[str, float]]:
        return self._champions.get_all_champion_lane_distributions()

    # ========== Matchups ==========

    def init_matchups_table(self) -> None:
        self._matchups.init_matchups_table()

    def add_matchup(
        self,
        champion: str,
        enemy: str,
        winrate: float,
        delta1: float,
        delta2: float,
        pickrate: float,
        games: int,
    ) -> None:
        self._matchups.add_matchup(champion, enemy, winrate, delta1, delta2, pickrate, games)

    def get_champion_matchups(self, champion_id: int) -> List[tuple]:
        return self._matchups.get_champion_matchups(champion_id)

    def get_champion_matchups_by_name(
        self, champion_name: str, as_dataclass: bool = True, lane: Optional[str] = None
    ) -> Union[List[Matchup], List[tuple]]:
        return self._matchups.get_champion_matchups_by_name(
            champion_name, as_dataclass=as_dataclass, lane=lane
        )

    def get_champion_matchups_for_draft(
        self, champion_name: str, as_dataclass: bool = True, lane: Optional[str] = None
    ) -> Union[List[MatchupDraft], List[tuple]]:
        return self._matchups_draft.get_champion_matchups_for_draft(
            champion_name, as_dataclass=as_dataclass, lane=lane
        )

    def get_reverse_matchups_for_draft(
        self, champion_name: str, as_dataclass: bool = True, lane: Optional[str] = None
    ) -> Union[List[MatchupDraft], List[tuple]]:
        return self._matchups_draft.get_reverse_matchups_for_draft(
            champion_name, as_dataclass=as_dataclass, lane=lane
        )

    def add_matchups_batch(
        self,
        matchup_data: List[tuple],
        champion_cache: Dict[str, int] = None,
        lane: Optional[str] = None,
    ) -> int:
        return self._matchups.add_matchups_batch(
            matchup_data, champion_cache=champion_cache, lane=lane
        )

    def clear_matchups_for_champion(
        self, champion_name: str, champion_cache: Dict[str, int] = None
    ) -> bool:
        return self._matchups.clear_matchups_for_champion(
            champion_name, champion_cache=champion_cache
        )

    def get_matchup_delta2(
        self, champion_name: str, enemy_name: str, lane: Optional[str] = None
    ) -> Optional[float]:
        return self._matchups.get_matchup_delta2(champion_name, enemy_name, lane=lane)

    def get_all_matchups_bulk(self, lane: Optional[str] = None) -> dict:
        return self._matchups.get_all_matchups_bulk(lane=lane)

    # ========== Synergies ==========

    def init_synergies_table(self) -> None:
        self._synergies.init_synergies_table()

    def add_synergy(
        self,
        champion: str,
        ally: str,
        winrate: float,
        delta1: float,
        delta2: float,
        pickrate: float,
        games: int,
    ) -> None:
        self._synergies.add_synergy(champion, ally, winrate, delta1, delta2, pickrate, games)

    def get_champion_synergies_by_name(
        self, champion_name: str, as_dataclass: bool = True, lane: Optional[str] = None
    ) -> Union[List["Synergy"], List[tuple]]:
        return self._synergies.get_champion_synergies_by_name(
            champion_name, as_dataclass=as_dataclass, lane=lane
        )

    def add_synergies_batch(
        self,
        synergies: List[Tuple[str, str, float, float, float, float, int]],
        lane: Optional[str] = None,
    ) -> None:
        self._synergies.add_synergies_batch(synergies, lane=lane)

    def clear_synergies_for_champion(self, champion_name: str) -> None:
        self._synergies.clear_synergies_for_champion(champion_name)

    def get_synergy_delta2(
        self, champion_name: str, ally_name: str, lane: Optional[str] = None
    ) -> Optional[float]:
        return self._synergies.get_synergy_delta2(champion_name, ally_name, lane=lane)

    def get_all_synergies_bulk(self, lane: Optional[str] = None) -> dict:
        return self._synergies.get_all_synergies_bulk(lane=lane)

    # ========== db_meta (fraîcheur) ==========

    def set_meta(self, key: str, value: str) -> None:
        self._meta.set_meta(key, value)

    def get_meta(self, key: str) -> Optional[str]:
        return self._meta.get_meta(key)

    # ========== Champion Scores ==========

    def init_champion_scores_table(self) -> None:
        self._champion_scores.init_champion_scores_table()

    def save_champion_scores(
        self,
        champion_id: int,
        avg_delta2: float,
        variance: float,
        coverage: float,
        peak_impact: float,
        volatility: float,
        target_ratio: float,
        lane: str = analysis_config.ALL_LANES_KEY,
    ) -> None:
        self._champion_scores.save_champion_scores(
            champion_id,
            avg_delta2,
            variance,
            coverage,
            peak_impact,
            volatility,
            target_ratio,
            lane=lane,
        )

    def get_champion_scores(
        self, champion_id: int, lane: str = analysis_config.ALL_LANES_KEY
    ) -> Optional[Dict[str, float]]:
        return self._champion_scores.get_champion_scores(champion_id, lane=lane)

    def get_champion_scores_by_name(
        self, champion_name: str, lane: str = analysis_config.ALL_LANES_KEY
    ) -> Optional[Dict[str, float]]:
        return self._champion_scores.get_champion_scores_by_name(champion_name, lane=lane)

    def get_all_champion_scores(self, lane: str = analysis_config.ALL_LANES_KEY) -> List[tuple]:
        return self._champion_scores.get_all_champion_scores(lane=lane)

    def champion_scores_table_exists(self) -> bool:
        return self._champion_scores.champion_scores_table_exists()

    # ========== Pool Ban Recommendations ==========

    def init_pool_ban_recommendations_table(self) -> None:
        self._pool_bans.init_pool_ban_recommendations_table()

    def save_pool_ban_recommendations(self, pool_name: str, ban_data: List[tuple]) -> int:
        return self._pool_bans.save_pool_ban_recommendations(pool_name, ban_data)

    def get_pool_ban_recommendations(self, pool_name: str, limit: int = 5) -> List[tuple]:
        return self._pool_bans.get_pool_ban_recommendations(pool_name, limit=limit)

    def pool_has_ban_recommendations(self, pool_name: str) -> bool:
        return self._pool_bans.pool_has_ban_recommendations(pool_name)

    def clear_pool_ban_recommendations(self, pool_name: str = None) -> int:
        return self._pool_bans.clear_pool_ban_recommendations(pool_name)

    # ========== Predictions (SPEC-05 B7) ==========

    def insert_prediction(
        self,
        ally_champions: List[int],
        enemy_champions: List[int],
        ally_lanes: Optional[Dict[int, str]],
        predicted_probability: float,
        model_version: str,
    ) -> Optional[int]:
        return self._predictions.insert_prediction(
            ally_champions, enemy_champions, ally_lanes, predicted_probability, model_version
        )

    def update_prediction_outcome(self, prediction_id: int, outcome: int) -> bool:
        return self._predictions.update_prediction_outcome(prediction_id, outcome)

    def get_latest_prediction_id(self) -> Optional[int]:
        return self._predictions.get_latest_prediction_id()
