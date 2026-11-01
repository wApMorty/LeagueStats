"""Classement des candidats de mon pool pour le prochain pick (SPEC-12, SPEC-48).

Chaque candidat est noté sur la draft telle qu'elle est, avec ``src/analysis/game_eval.py``. Une
stratégie à anticipation (``Strategy.search``) ajoute un pli : si mon vis-à-vis n'est pas vu et qu'un
tour ennemi reste à venir, il joue sa meilleure réponse parmi les ``SEARCH_TOP_N`` champions les plus
joués de ma lane (SPEC-17 §4.1). Un pick fort qui offre un contre-pick évident recule donc.

Le calcul s'arrête à ce pli. Rejoué sur 219 parties (SPEC-48 §1), un arbre complet ne battait pas le
calcul immédiat, et ce que WIN LANE en tirait tenait à la réponse du vis-à-vis.

Convention de signe : tous les logits manipulés ici sont DU POINT DE VUE ALLIÉ.
"""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from ..config_constants import scraping_config
from ..analysis.game_eval import GameEvaluator, Placed
from ..analysis.mastery import to_win_points


@dataclass(frozen=True)
class PickTurn:
    """Un pick encore à venir dans la draft."""

    is_ally: bool
    is_local_player: bool = False
    # Lane assignée par la file (alliés seulement, SPEC-17 §4.2). None côté
    # ennemi, dont l'assignedPosition est masquée, et en normal blind.
    lane: Optional[str] = None


@dataclass
class SearchResult:
    """Issue du classement pour un candidat de notre pool."""

    champion: str
    lane: Optional[str]
    win_probability: float
    # SPEC-48 : réponse attendue du vis-à-vis, None sans anticipation.
    reply: Optional[Placed] = None
    # SPEC-41 : part de ma maîtrise du champion dans `win_probability`, en points de victoire à 50 %.
    personal_points: float = 0.0
    # SPEC-46 : valeur qui a classé le candidat sous la stratégie ; `win_probability` reste calibrée.
    score: Optional[float] = None


def _no_term(_name: str) -> float:
    """Aucun terme personnel : le classement d'avant SPEC-41."""
    return 0.0


class CandidatePool:
    """Les champions qu'un adversaire jouerait vraiment.

    Classés par popularité sur la lane (somme des games, SPEC-17 §4.1), pas par
    la tier list : le haut de ``champion_scores.avg_delta2`` est occupé par des
    picks hors rôle à très faible échantillon (Kassadin top), qui couvraient 1
    à 12 % des parties réelles.
    """

    def __init__(self, db, top_n: int, verbose: bool = False) -> None:
        self.db = db
        self.top_n = top_n
        self.verbose = verbose
        self._by_lane: Dict[str, List[str]] = {}

    def _ranked(self, lane: str) -> List[str]:
        if lane not in self._by_lane:
            self._by_lane[lane] = list(self.db.get_lane_popularity(lane) or [])
            if self.verbose:
                print(f"[SEARCH] Candidats lane={lane} : {len(self._by_lane[lane])} champions")
        return self._by_lane[lane]

    def best(self, lane: str, taken: Set[str]) -> List[str]:
        """Les ``top_n`` champions les plus joués encore disponibles sur ``lane``."""
        available = []
        for name in self._ranked(lane):
            if name.lower() in taken:
                continue
            available.append(name)
            if len(available) >= self.top_n:
                break
        return available


class DraftSearch:
    """Classe mon pool, avec au plus la réponse du vis-à-vis (SPEC-48)."""

    def __init__(
        self,
        evaluator: GameEvaluator,
        candidates: CandidatePool,
        verbose: bool = False,
    ) -> None:
        self.evaluator = evaluator
        self.candidates = candidates
        self.verbose = verbose

    @staticmethod
    def _free_lanes(team: Sequence[Placed]) -> List[str]:
        used = {lane for _, lane in team if lane}
        return [lane for lane in scraping_config.LANES if lane not in used]

    def _reply(
        self, me: Placed, allies: Sequence[Placed], enemies: Sequence[Placed], taken: Set[str]
    ) -> Tuple[Optional[Placed], float]:
        """Meilleure réponse du vis-à-vis à `me`, et ce qu'elle change au logit allié."""
        lane = me[1]
        team = list(allies) + [me]
        best: Optional[Placed] = None
        worst = 0.0
        for name in self.candidates.best(lane, taken | {me[0].lower()}):
            value = -self.evaluator.contribution((name, lane), enemies, team)
            if best is None or value < worst:
                best, worst = (name, lane), value
        return best, worst

    def rank(
        self,
        allies: Sequence[Placed],
        enemies: Sequence[Placed],
        pool: Sequence[str],
        remaining_turns: Sequence[PickTurn],
        banned: Sequence[str] = (),
        player_lane: Optional[str] = None,
        personal: Callable[[str], float] = _no_term,
        anticipate: bool = False,
    ) -> List[SearchResult]:
        """Classe les champions de ``pool`` pour notre prochain pick.

        ``remaining_turns[0]`` est notre propre tour — l'appelant écarte les
        tours qui le précèdent (cf. ``DraftRecommender``). ``personal(nom)`` est
        le log-odds de ma maîtrise du champion (SPEC-41), ajouté à mon seul pick.
        ``anticipate`` ajoute la réponse du vis-à-vis non vu (SPEC-48).

        Returns:
            Un ``SearchResult`` par candidat jouable, du meilleur au pire.
        """
        if not remaining_turns:
            return []

        base_allies = list(allies)
        base_enemies = list(enemies)
        base_logit = self.evaluator.team_logit(base_allies, base_enemies)
        taken = {name.lower() for name, _ in base_allies}
        taken |= {name.lower() for name, _ in base_enemies}
        taken |= {name.lower() for name in banned}

        free_lanes = self._free_lanes(base_allies)
        lane = player_lane or (free_lanes[0] if free_lanes else None)
        expects_reply = (
            anticipate
            and lane is not None
            and any(not turn.is_ally for turn in remaining_turns[1:])
            and all(enemy_lane != lane for _, enemy_lane in base_enemies)
        )

        results: List[SearchResult] = []
        for name in pool:
            if name.lower() in taken:
                continue
            me = (name, lane)
            term = personal(name)
            value = base_logit + self.evaluator.contribution(me, base_allies, base_enemies) + term
            reply: Optional[Placed] = None
            if expects_reply:
                reply, change = self._reply(me, base_allies, base_enemies, taken)
                value += change
            results.append(
                SearchResult(
                    champion=name,
                    lane=lane,
                    win_probability=self.evaluator.probability(value),
                    reply=reply,
                    personal_points=to_win_points(term),
                )
            )

        results.sort(key=lambda r: -r.win_probability)
        if self.verbose and results:
            print(
                f"[SEARCH] Meilleur : {results[0].champion} "
                f"({results[0].win_probability * 100:.2f}%)"
            )
        return results
