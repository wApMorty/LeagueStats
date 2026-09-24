"""Recherche minimax sur les picks restants de la draft (SPEC-12).

Remplace le classement par delta du Live Coach : au lieu de noter un candidat
sur la draft telle qu'elle est, on déroule la fin de la draft en supposant que
les deux équipes jouent leur meilleur coup, et on note la position obtenue avec
``src/analysis/game_eval.py``. Un pick fort mais qui offre un contre-pick
évident à l'adversaire cesse ainsi d'être recommandé en aveugle.

Trois mécaniques, empruntées aux moteurs d'échecs :

- **Approfondissement itératif sous budget temps.** On cherche à profondeur 1,
  puis 2, 3… et on rend toujours le meilleur coup de la dernière profondeur
  terminée. Le facteur de branchement d'une draft (jusqu'à 8 candidats × 5
  lanes libres) rend toute profondeur fixe intenable : ici, un pool large coûte
  de la profondeur, jamais un blocage.
- **Élagage alpha-bêta.** Exact, jamais une approximation : il ne coupe que les
  branches qui ne peuvent plus changer la valeur de la racine.
- **Coups candidats.** Nos picks viennent de notre pool, ceux des autres des
  ``SEARCH_TOP_N`` champions les plus joués de chaque lane libre (SPEC-17
  §4.1). Le générateur répond à « que pourrait jouer l'adversaire ? », le
  minimax à « quel est son meilleur coup ? » : trier les candidats par force
  mélangerait les deux, et sur des échantillons minuscules.

Convention de signe : tous les logits manipulés ici sont DU POINT DE VUE ALLIÉ.
L'équipe alliée maximise, l'ennemie minimise.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from ..config_constants import draft_config, scraping_config
from ..analysis.game_eval import GameEvaluator, Placed


class _SearchTimeout(Exception):
    """Budget temps épuisé : la profondeur en cours est abandonnée."""


@dataclass(frozen=True)
class PickTurn:
    """Un pick encore à venir dans la draft."""

    is_ally: bool
    is_local_player: bool = False


@dataclass
class SearchResult:
    """Issue de la recherche pour un candidat de notre pool."""

    champion: str
    lane: Optional[str]
    win_probability: float
    # Suite de coups supposée optimale après ce pick (le nôtre exclu).
    principal_variation: List[Placed] = field(default_factory=list)
    depth: int = 0


class CandidatePool:
    """Les champions qu'un adversaire (ou un allié hors pool) jouerait vraiment.

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
    """Minimax alpha-bêta sur la fin de la draft."""

    def __init__(
        self,
        evaluator: GameEvaluator,
        candidates: CandidatePool,
        verbose: bool = False,
    ) -> None:
        self.evaluator = evaluator
        self.candidates = candidates
        self.verbose = verbose
        self.nodes = 0

    # ---------- génération des coups ----------

    @staticmethod
    def _free_lanes(team: Sequence[Placed]) -> List[str]:
        used = {lane for _, lane in team if lane}
        return [lane for lane in scraping_config.LANES if lane not in used]

    def _moves(
        self,
        turn: PickTurn,
        team: Sequence[Placed],
        taken: Set[str],
        pool: Sequence[str],
        player_lane: Optional[str],
    ) -> List[Placed]:
        """Coups candidats pour ce tour, chacun étiqueté de la lane qu'il occupe."""
        if turn.is_local_player:
            # Notre propre pick : on ne jouera jamais hors de notre pool.
            lanes = [player_lane] if player_lane else self._free_lanes(team)[:1]
            lane = lanes[0] if lanes else None
            return [(name, lane) for name in pool if name.lower() not in taken]

        moves: List[Placed] = []
        for lane in self._free_lanes(team):
            moves.extend((name, lane) for name in self.candidates.best(lane, taken))
        return moves

    # ---------- recherche ----------

    def _minimax(
        self,
        logit: float,
        turns: Sequence[PickTurn],
        index: int,
        allies: List[Placed],
        enemies: List[Placed],
        taken: Set[str],
        pool: Sequence[str],
        player_lane: Optional[str],
        alpha: float,
        beta: float,
        deadline: float,
    ) -> Tuple[float, List[Placed]]:
        """Valeur alliée de la position, et variante principale depuis ce nœud."""
        if index >= len(turns):
            return logit, []

        # Le contrôle du budget est au nœud, pas à la feuille : une branche
        # profonde ne doit pas pouvoir dépasser le chrono de pick à elle seule.
        if time.monotonic() > deadline:
            raise _SearchTimeout()

        turn = turns[index]
        own, opposing = (allies, enemies) if turn.is_ally else (enemies, allies)
        moves = self._moves(turn, own, taken, pool, player_lane)
        if not moves:
            # Plus rien de jouable (pool épuisé) : les slots restants comptent
            # pour 0, comme les slots au-delà de la profondeur atteinte.
            return logit, []

        # Ordre des coups : par gain immédiat, décroissant pour le camp qui
        # maximise. L'élagage alpha-bêta ne coupe efficacement que si les bons
        # coups passent en premier.
        scored = [(move, self.evaluator.contribution(move, own, opposing)) for move in moves]
        scored.sort(key=lambda item: -item[1])

        best_value = float("-inf") if turn.is_ally else float("inf")
        best_line: List[Placed] = []

        for move, contribution in scored:
            self.nodes += 1
            child_logit = logit + (contribution if turn.is_ally else -contribution)
            own.append(move)
            taken.add(move[0].lower())
            try:
                value, line = self._minimax(
                    child_logit,
                    turns,
                    index + 1,
                    allies,
                    enemies,
                    taken,
                    pool,
                    player_lane,
                    alpha,
                    beta,
                    deadline,
                )
            finally:
                own.pop()
                taken.discard(move[0].lower())

            if turn.is_ally:
                if value > best_value:
                    best_value, best_line = value, [move] + line
                alpha = max(alpha, best_value)
            else:
                if value < best_value:
                    best_value, best_line = value, [move] + line
                beta = min(beta, best_value)
            if alpha >= beta:
                break

        return best_value, best_line

    def rank(
        self,
        allies: Sequence[Placed],
        enemies: Sequence[Placed],
        pool: Sequence[str],
        remaining_turns: Sequence[PickTurn],
        banned: Sequence[str] = (),
        player_lane: Optional[str] = None,
        budget_seconds: Optional[float] = None,
    ) -> List[SearchResult]:
        """Classe les champions de ``pool`` pour notre prochain pick.

        ``remaining_turns[0]`` est notre propre tour — l'appelant écarte les
        tours qui le précèdent (cf. ``DraftRecommender``).

        Returns:
            Un ``SearchResult`` par candidat jouable, du meilleur au pire.
        """
        if not remaining_turns:
            return []

        budget = (
            budget_seconds if budget_seconds is not None else draft_config.SEARCH_BUDGET_SECONDS
        )
        deadline = time.monotonic() + budget
        self.nodes = 0

        base_allies = list(allies)
        base_enemies = list(enemies)
        base_logit = self.evaluator.team_logit(base_allies, base_enemies)
        taken = {name.lower() for name, _ in base_allies}
        taken |= {name.lower() for name, _ in base_enemies}
        taken |= {name.lower() for name in banned}

        root_moves = self._moves(remaining_turns[0], base_allies, taken, pool, player_lane)
        if not root_moves:
            return []

        results: List[SearchResult] = []
        max_depth = min(len(remaining_turns), draft_config.SEARCH_MAX_DEPTH)

        # ponytail: effet pair/impair, l'équivalent draft du même biais aux
        # échecs. Si la recherche s'arrête après deux picks adverses et un
        # seul des nôtres, la probabilité rendue est pessimiste — le camp qui
        # a joué le plus de coups dans la fenêtre est avantagé. Le CLASSEMENT
        # reste juste (tous les candidats sont évalués à la même profondeur),
        # seul le chiffre absolu penche, et l'affichage annonce la profondeur
        # atteinte pour que ce soit lisible. Corriger demanderait de ne
        # retenir que les profondeurs où les deux camps ont joué autant de
        # picks, donc de jeter du travail déjà fait.
        for depth in range(1, max_depth + 1):
            try:
                deeper = self._rank_at_depth(
                    depth,
                    root_moves,
                    base_logit,
                    base_allies,
                    base_enemies,
                    taken,
                    pool,
                    player_lane,
                    remaining_turns,
                    deadline,
                )
            except _SearchTimeout:
                break
            results = deeper
            # L'itération suivante essaie d'abord le meilleur coup connu : même
            # rôle que la variante principale aux échecs, l'élagage en dépend.
            root_moves = [(r.champion, r.lane) for r in results]

        if self.verbose and results:
            print(
                f"[SEARCH] profondeur {results[0].depth}, {self.nodes} nœuds, "
                f"meilleur : {results[0].champion} "
                f"({results[0].win_probability * 100:.2f}%)"
            )
        return results

    def _rank_at_depth(
        self,
        depth: int,
        root_moves: Sequence[Placed],
        base_logit: float,
        base_allies: List[Placed],
        base_enemies: List[Placed],
        base_taken: Set[str],
        pool: Sequence[str],
        player_lane: Optional[str],
        remaining_turns: Sequence[PickTurn],
        deadline: float,
    ) -> List[SearchResult]:
        """Une itération complète d'approfondissement, à profondeur fixée."""
        turns = list(remaining_turns[:depth])
        results: List[SearchResult] = []

        for move in root_moves:
            contribution = self.evaluator.contribution(move, base_allies, base_enemies)
            self.nodes += 1
            base_allies.append(move)
            base_taken.add(move[0].lower())
            try:
                value, line = self._minimax(
                    base_logit + contribution,
                    turns,
                    1,
                    base_allies,
                    base_enemies,
                    base_taken,
                    pool,
                    player_lane,
                    float("-inf"),
                    float("inf"),
                    deadline,
                )
            finally:
                base_allies.pop()
                base_taken.discard(move[0].lower())

            results.append(
                SearchResult(
                    champion=move[0],
                    lane=move[1],
                    win_probability=self.evaluator.probability(value),
                    principal_variation=line,
                    depth=depth,
                )
            )
            # Pas d'élagage sur alpha à la racine : on a besoin de la valeur
            # exacte de CHAQUE candidat pour l'afficher, pas seulement du
            # meilleur. C'est le prix du classement complet à l'écran.

        results.sort(key=lambda r: -r.win_probability)
        return results
