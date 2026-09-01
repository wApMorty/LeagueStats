"""Per-champion draft scoring (matchup + synergy blend).

Extracted from src/draft_monitor.py (SPEC-07 E10, lot 7) : déplacement
verbatim, aucun changement de comportement.
"""

from typing import Callable, Dict, List, Optional


class DraftScorer:
    """Blend matchup and synergy scores for a candidate champion.

    ``display_name`` is injected as a callable (``DraftMonitor._get_display_name``)
    rather than a captured dict, since ``champion_id_to_name`` is rebound after
    construction (``_load_champion_mappings`` and test fixtures).
    """

    def __init__(
        self,
        assistant,
        display_name: Callable[[int], str],
        synergy_weight: float,
        verbose: bool = False,
    ) -> None:
        self.assistant = assistant
        self._display_name = display_name
        self.synergy_weight = synergy_weight
        self.verbose = verbose

    def calculate_score_against_team(
        self,
        matchups: List[tuple],
        enemy_team: List[int],
        champion_name: str,
        banned_champion_ids: List[int] = None,
        lane: Optional[str] = None,
        enemy_lanes: Optional[Dict[str, str]] = None,
        player_lane: Optional[str] = None,
    ) -> float:
        """Calculate score against enemy team using Assistant's method.

        Args:
            lane: Lane optionnelle transmise aux requêtes inverses internes
                  (cf. ChampionScorer.score_against_team). None = comportement
                  inchangé. La détection automatique de la lane est hors
                  périmètre ici (SPEC-04) : la valeur arrive de l'extérieur.
            enemy_lanes: Enemy display name -> inferred lane (SPEC-04 §4.3),
                  from state.inferred_roles. Weights the enemy sharing our
                  lane above the rest of the enemy team.
            player_lane: Our own (the local player's) lane.
        """
        if not matchups or not enemy_team:
            return 0.0

        # Convert enemy IDs to champion names for the assistant method
        enemy_names = []
        for enemy_id in enemy_team:
            enemy_name = self._display_name(enemy_id)
            if enemy_name:
                enemy_names.append(enemy_name)

        if not enemy_names:
            return 0.0

        # Convert banned champion IDs to names
        banned_names = []
        if banned_champion_ids:
            for banned_id in banned_champion_ids:
                banned_name = self._display_name(banned_id)
                if banned_name:
                    banned_names.append(banned_name)

        # Use the assistant's scoring method which includes blind pick logic
        return self.assistant.score_against_team(
            matchups,
            enemy_names,
            champion_name,
            banned_names if banned_names else None,
            lane=lane,
            enemy_lanes=enemy_lanes,
            player_lane=player_lane,
        )

    def calculate_synergy_score(
        self, champion_name: str, ally_team: List[int], lane: Optional[str] = None
    ) -> float:
        """Calculate synergy score as sum of delta2 with allied champions.

        Args:
            champion_name: Name of the champion to evaluate
            ally_team: List of allied champion IDs already picked
            lane: Lane optionnelle transmise à get_synergy_delta2. None =
                  comportement inchangé (agrégation toutes lanes).

        Returns:
            Sum of delta2 values for synergies with allies (0.0 if no allies)
        """
        if not ally_team:
            return 0.0

        synergy_score = 0.0

        for ally_id in ally_team:
            ally_name = self._display_name(ally_id)
            if ally_name:
                delta2 = self.assistant.db.get_synergy_delta2(champion_name, ally_name, lane=lane)
                if delta2 is not None:
                    synergy_score += delta2
                    if self.verbose:
                        print(f"[DEBUG] Synergy: {champion_name} + {ally_name} = {delta2:+.2f}")

        return synergy_score

    def final_score(self, matchup_score: float, synergy_score: float) -> float:
        """Blend matchup and synergy scores using the configurable synergy weight.

        Formula: final_score = matchup_score * min(1, 2 * (1 - synergy_weight))
                              + synergy_score * min(1, 2 * synergy_weight)

        The min(1, ...) clamp is what makes all three pinned cases exact:
        - synergy_weight=0.5 (default): both coefficients clamp to 1
          -> final_score = matchup_score + synergy_score (unchanged historical behavior).
        - synergy_weight=0.0: matchup coefficient clamps to 1, synergy coefficient is 0
          -> final_score = matchup_score (synergy fully ignored).
        - synergy_weight=1.0: synergy coefficient clamps to 1, matchup coefficient is 0
          -> final_score = synergy_score (matchup fully ignored).
        (The naive matchup_score * (1 - w) * 2 + synergy_score * w * 2, without the
        clamp, would double-count at w=0 and w=1, so the clamp is required.)
        """
        matchup_weight = min(1.0, 2 * (1 - self.synergy_weight))
        synergy_weight = min(1.0, 2 * self.synergy_weight)
        return matchup_score * matchup_weight + synergy_score * synergy_weight
