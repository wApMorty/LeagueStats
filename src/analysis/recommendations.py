"""Champion recommendation system for draft picks."""

from typing import List, Optional

from ..db import Database
from ..constants import CHAMPION_POOL, TOP_SOLOQ_POOL
from ..config import config
from ..config_constants import analysis_config
from .scoring import ChampionScorer
from ..models import Matchup


class RecommendationEngine:
    """Generates champion recommendations based on team compositions."""

    def __init__(self, db: Database, scorer: ChampionScorer, draft_scorer=None):
        """
        Initialize RecommendationEngine.

        Args:
            db: Database instance
            scorer: ChampionScorer instance
            draft_scorer: Optional DraftScorer instance (src/draft/scoring.py),
                used to blend a synergy score with ally_team into the ranking —
                same blend the Live Coach uses. None = matchup-only ranking
                (legacy behavior, kept for callers/tests that build this engine
                without one).
        """
        self.db = db
        self.scorer = scorer
        self.draft_scorer = draft_scorer

    def draft_simple(self, nb_results: int) -> None:
        """
        Interactive draft recommendation (legacy simple version).

        Args:
            nb_results: Number of recommendations to display initially
        """
        scores = []
        enemy_team = []
        _results = nb_results

        enemy = input("Champion 1 :")
        while enemy != "" and len(enemy_team) < 4:
            enemy_team.append(enemy)
            enemy = input(f"Champion {len(enemy_team) + 1} :")

        for champion in CHAMPION_POOL:
            if champion not in enemy_team:
                matchups = self.db.get_champion_matchups_by_name(champion)
                if sum(m.games for m in matchups) < analysis_analysis_config.MIN_GAMES_COMPETITIVE:
                    break
                score = self.scorer.score_against_team(matchups, enemy_team, champion_name=champion)
                scores.append((str(champion), score))
                scores.sort(key=lambda x: -x[1])

        for index in range(min(_results, len(CHAMPION_POOL))):
            print(scores[index])
        while input("Want more ?") == "y":
            _results += nb_results
            for index in range(_results):
                print(scores[index])

    def calculate_and_display_recommendations(
        self,
        enemy_team: List[str],
        ally_team: List[str],
        nb_results: int,
        champion_pool: Optional[List[str]] = None,
        banned_champions: Optional[List[str]] = None,
        lane: Optional[str] = None,
    ) -> List[tuple]:
        """
        Calculate champion recommendations and display top results.

        Args:
            enemy_team: List of enemy champions
            ally_team: List of ally champions
            nb_results: Number of results to display
            champion_pool: Pool to select from (defaults to TOP_SOLOQ_POOL)
            banned_champions: List of banned champions to exclude
            lane: Lane optionnelle transmise au scoring matchup/synergie
                  (SPEC-04, pool_manager.pool_role_to_lane sur champion_pool).
                  None = agrégation toutes lanes, comportement inchangé.

        Returns:
            List of (champion, advantage) tuples, sorted by score
        """
        if champion_pool is None:
            champion_pool = TOP_SOLOQ_POOL
        if banned_champions is None:
            banned_champions = []

        scores = []
        skipped_low_data = 0

        for champion in champion_pool:
            # Skip if already picked or banned
            if champion in enemy_team or champion in ally_team or champion in banned_champions:
                continue

            matchups = self.db.get_champion_matchups_by_name(champion, lane=lane)
            total_games = sum(m.games for m in matchups)

            if total_games < analysis_config.MIN_GAMES_COMPETITIVE:
                skipped_low_data += 1
                continue

            matchup_score = self.scorer.score_against_team(
                matchups, enemy_team, champion_name=champion, lane=lane
            )
            if self.draft_scorer is not None:
                synergy_score = self.draft_scorer.calculate_synergy_score_by_names(
                    champion, ally_team, lane=lane
                )
                score = self.draft_scorer.final_score(matchup_score, synergy_score)
            else:
                score = matchup_score
            scores.append((str(champion), score))

        scores.sort(key=lambda x: -x[1])

        # Display formatted results
        if scores:
            rank_labels = ["1.", "2.", "3."]
            for index in range(min(nb_results, len(scores))):
                champion, advantage = scores[index]
                rank = rank_labels[index] if index < 3 else f"  {index+1}."
                print(f"{rank} {champion:<15} | {advantage:+6.2f}% advantage")
        else:
            print("  [ALERTE] No recommendations available")
            if skipped_low_data > 0:
                print(f"     ({skipped_low_data} champions skipped - insufficient data)")

        return scores
