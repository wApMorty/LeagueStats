"""Per-champion draft scoring (matchup + synergy blend).

Extracted from src/draft_monitor.py (SPEC-07 E10, lot 7) : déplacement
verbatim, aucun changement de comportement.
"""

from typing import List, Optional


class DraftScorer:
    """Blend matchup and synergy scores for a candidate champion.

    Ne sert plus au Live Coach : depuis SPEC-12 celui-ci évalue par
    ``src/analysis/game_eval.py`` + la recherche. Seul ``Assistant.draft_scorer``
    l'instancie encore, pour le Team Builder et ``RecommendationEngine``.

    Les variantes par IDs de champion (``calculate_score_against_team``,
    ``calculate_synergy_score``) ont disparu avec le curseur synergie/matchup :
    leur unique appelant était ``DraftMonitor``, et elles étaient la seule
    raison d'injecter un ``display_name``.
    """

    def __init__(
        self,
        assistant,
        synergy_weight: float,
        verbose: bool = False,
    ) -> None:
        self.assistant = assistant
        self.synergy_weight = synergy_weight
        self.verbose = verbose

    def calculate_synergy_score_by_names(
        self, champion_name: str, ally_names: List[str], lane: Optional[str] = None
    ) -> float:
        """Somme des delta2 de synergie entre ``champion_name`` et ses alliés.

        Prend des noms d'affichage plutôt que des IDs Riot — c'est ce dont
        disposent ses appelants (Team Builder, Tournament Coach), qui ne passent
        jamais par une table id -> nom.

        Args:
            champion_name: Name of the champion to evaluate
            ally_names: List of allied champion display names already picked
            lane: Lane optionnelle transmise à get_synergy_delta2. None =
                  comportement inchangé (agrégation toutes lanes).

        Returns:
            Sum of delta2 values for synergies with allies (0.0 if no allies)
        """
        if not ally_names:
            return 0.0

        synergy_score = 0.0

        for ally_name in ally_names:
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
