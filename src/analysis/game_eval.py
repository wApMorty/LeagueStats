"""Probabilité de victoire d'une game complète, décomposée en termes de paires.

Remplace, pour le Live Coach, l'empilement ``score_against_team`` (par
champion, bidirectionnel) + ``estimate_win_probability`` (somme des log-odds
par champion) : le même matchup y était compté deux fois, une fois depuis
chaque camp, et la normalisation ``allié / (allié + ennemi)`` de l'analyse
finale n'était pas une probabilité.

Forme retenue — une seule somme, sur les PAIRES et non sur les champions :

    logit(P_alliés) = Σ_{i allié, j ennemi} w(i,j) · c(i,j) · K_MATCHUP · δ(i,j)
                    + K_SYNERGY · ( Σ_{paires alliées} s − Σ_{paires ennemies} s )

    δ(i,j) = (delta2(i→j) − delta2(j→i)) / 2        antisymétrique : δ(j,i) = −δ(i,j)
    s(a,b) = (syn(a→b) + syn(b→a)) / 2              symétrique
    w(i,j) = SAME_LANE_WEIGHT si même lane, sinon OTHER_LANE_WEIGHT
    c(i,j) = confidence(games, K)                   shrink des faibles échantillons,
                                                    K mesuré par type (SPEC-13)

Trois propriétés, dont dépend ``src/draft/search.py`` :

1. **Antisymétrie** : échanger les deux équipes retourne le signe du logit. Le
   double comptage disparaît par construction, pas par soustraction.
2. **Décomposition** : ``contribution()`` donne le log-odds qu'ajoute UN
   champion aux paires déjà posées. La recherche ne réévalue donc jamais une
   composition entière — sans quoi le minimax serait injouable en Python.
3. **Indépendance de l'ordre** : empiler les contributions dans n'importe quel
   ordre donne le même total que ``team_logit()`` sur la composition finale
   (vérifié par tests/test_game_eval.py).

Les tables de paires sont chargées en masse par lane, une fois, et gardées en
mémoire : la recherche fait des dizaines de milliers de lookups et ne peut pas
passer par SQL.
"""

from typing import Dict, Iterable, Optional, Sequence, Tuple

from ..config_constants import analysis_config, role_inference_config
from .probability import confidence, sigmoid, winrate_points_to_logit
from .shrink import read_shrink_k

# (delta2 pondéré, games) par paire de noms en minuscules.
PairTable = Dict[Tuple[str, str], Tuple[float, int]]

# Un champion posé sur le board : (nom, lane) — lane None quand inconnue.
Placed = Tuple[str, Optional[str]]


class GameEvaluator:
    """Évalue une composition 5v5 (même partielle) en probabilité de victoire.

    Les lanes sont facultatives partout : sans lane, la paire est cherchée dans
    la table toutes-lanes et pondérée par ``OTHER_LANE_WEIGHT``, ce qui redonne
    le comportement d'avant SPEC-04.

    Les termes de paires sont mémorisés (SPEC-17 §4.3) : la recherche
    recalcule les mêmes paires des centaines de milliers de fois. Le cache vit
    aussi longtemps que l'évaluateur, comme les tables et les K de shrink qu'il
    garde déjà : une mise à jour des données en cours de session n'est pas vue,
    ni avant ni après ce cache. Pas d'éviction : au pire (173 × 5)² entrées,
    quelques dizaines de milliers en pratique sur une draft.
    """

    def __init__(self, db, verbose: bool = False) -> None:
        self.db = db
        self.verbose = verbose
        self._matchups: Dict[str, PairTable] = {}
        self._synergies: Dict[str, PairTable] = {}
        self._matchup_cache: Dict[Tuple[Placed, Placed], float] = {}
        self._synergy_cache: Dict[Tuple[Placed, Placed], float] = {}
        # SPEC-13 : demi-poids mesuré sur les données au dernier scrape, lu une
        # seule fois — la recherche fait des dizaines de milliers d'appels à
        # confidence() et ne peut pas relire db_meta à chacun.
        self._k_matchup = read_shrink_k(db, "matchups")
        self._k_synergy = read_shrink_k(db, "synergies")
        if verbose:
            print(
                f"[EVAL] Shrink mesuré : matchups K={self._k_matchup:.0f}, "
                f"synergies K={self._k_synergy:.0f}"
            )

    # ---------- chargement paresseux des tables ----------

    def _table(self, cache: Dict[str, PairTable], loader, lane: Optional[str]) -> PairTable:
        """Table de paires pour ``lane``, chargée à la première demande.

        Seules les lanes réellement en jeu sont chargées : une draft en touche
        au plus 5, et la table toutes-lanes ne sert que de repli quand la lane
        d'un champion est inconnue.
        """
        key = lane or analysis_config.ALL_LANES_KEY
        if key not in cache:
            cache[key] = loader(lane=lane, with_games=True) or {}
            if self.verbose:
                print(f"[EVAL] Table {loader.__name__} lane={key!r} : {len(cache[key])} paires")
        return cache[key]

    def _matchup_table(self, lane: Optional[str]) -> PairTable:
        return self._table(self._matchups, self.db.get_all_matchups_bulk, lane)

    def _synergy_table(self, lane: Optional[str]) -> PairTable:
        return self._table(self._synergies, self.db.get_all_synergies_bulk, lane)

    def warm(self, lanes: Iterable[Optional[str]]) -> None:
        """Pré-charge les tables des lanes données (début de draft).

        Purement une optimisation : sans cet appel, les mêmes tables seraient
        chargées à la première recherche, mais au beau milieu du chrono de pick.
        """
        for lane in lanes:
            self._matchup_table(lane)
            self._synergy_table(lane)

    # ---------- termes de paires ----------

    @staticmethod
    def _lane_weight(lane_a: Optional[str], lane_b: Optional[str]) -> float:
        """SPEC-04 §4.3 : l'adversaire de notre lane pèse plus que les autres."""
        if lane_a and lane_b and lane_a == lane_b:
            return role_inference_config.SAME_LANE_WEIGHT
        return role_inference_config.OTHER_LANE_WEIGHT

    def matchup_logit(self, champion: Placed, enemy: Placed) -> float:
        """Log-odds apporté aux alliés par la paire (champion allié, ennemi)."""
        value = self._matchup_cache.get((champion, enemy))
        if value is None:
            value = self._matchup_cache[(champion, enemy)] = self._matchup_logit(champion, enemy)
        return value

    def _matchup_logit(self, champion: Placed, enemy: Placed) -> float:
        """Calcul non mémorisé de ``matchup_logit``."""
        weight = self._lane_weight(champion[1], enemy[1])
        points = self.duel_points(champion, enemy) * analysis_config.K_MATCHUP
        return winrate_points_to_logit(points) * weight

    def duel_points(self, champion: Placed, enemy: Placed) -> float:
        """Avantage de ``champion`` sur ``enemy``, en points de winrate rétrécis
        (SPEC-13), sans pondération de lane : la valeur d'un duel seul (SPEC-18).

        δ antisymétrique : la valeur est la demi-différence des deux points de
        vue quand les deux existent. Quand un seul côté a des données, on le
        prend tel quel plutôt que de le diviser par deux — diviser reviendrait à
        traiter l'absence de données comme un avantage nul mesuré, alors que
        c'est une absence de mesure.
        """
        name, lane = champion
        enemy_name, enemy_lane = enemy
        forward = self._matchup_table(lane).get((name.lower(), enemy_name.lower()))
        reverse = self._matchup_table(enemy_lane).get((enemy_name.lower(), name.lower()))

        if forward and reverse:
            delta2 = (forward[0] - reverse[0]) / 2.0
            games = min(forward[1], reverse[1])
        elif forward:
            delta2, games = forward
        elif reverse:
            delta2, games = -reverse[0], reverse[1]
        else:
            return 0.0
        return delta2 * confidence(games, self._k_matchup)

    def has_matchup_data(self, champion: Placed, enemy: Placed) -> bool:
        """Vrai si au moins un des deux points de vue de la paire est mesuré.

        ``matchup_logit`` renvoie 0.0 aussi bien pour une égalité mesurée que
        pour une absence de mesure : l'affichage a besoin de les distinguer
        (SPEC-14 §2.2).
        """
        name, lane = champion
        enemy_name, enemy_lane = enemy
        return (name.lower(), enemy_name.lower()) in self._matchup_table(lane) or (
            enemy_name.lower(),
            name.lower(),
        ) in self._matchup_table(enemy_lane)

    def synergy_logit(self, champion: Placed, ally: Placed) -> float:
        """Log-odds apporté à l'équipe qui possède les deux champions."""
        value = self._synergy_cache.get((champion, ally))
        if value is None:
            value = self._synergy_cache[(champion, ally)] = self._synergy_logit(champion, ally)
        return value

    def _synergy_logit(self, champion: Placed, ally: Placed) -> float:
        """Calcul non mémorisé de ``synergy_logit``.

        Symétrique : s(a,b) = s(b,a). Le signe est appliqué par l'appelant —
        positif pour une paire alliée, négatif pour une paire ennemie.
        """
        name, lane = champion
        ally_name, ally_lane = ally
        forward = self._synergy_table(lane).get((name.lower(), ally_name.lower()))
        reverse = self._synergy_table(ally_lane).get((ally_name.lower(), name.lower()))

        if forward and reverse:
            delta2 = (forward[0] + reverse[0]) / 2.0
            games = min(forward[1], reverse[1])
        elif forward:
            delta2, games = forward
        elif reverse:
            delta2, games = reverse
        else:
            return 0.0

        return winrate_points_to_logit(delta2 * analysis_config.K_SYNERGY) * confidence(
            games, self._k_synergy
        )

    # ---------- composition ----------

    def contribution(
        self, champion: Placed, own_team: Sequence[Placed], opposing_team: Sequence[Placed]
    ) -> float:
        """Log-odds qu'ajoute ``champion`` aux paires déjà posées, DU POINT DE
        VUE DE SON PROPRE CAMP.

        L'appelant l'ajoute au logit allié si le champion est allié, le
        soustrait s'il est ennemi. ``own_team``/``opposing_team`` ne doivent pas
        déjà contenir ``champion`` : chaque paire n'est comptée qu'une fois, au
        moment où son second membre arrive.
        """
        total = sum(self.matchup_logit(champion, enemy) for enemy in opposing_team)
        total += sum(self.synergy_logit(champion, ally) for ally in own_team)
        return total

    def team_logit(self, allies: Sequence[Placed], enemies: Sequence[Placed]) -> float:
        """Log-odds de victoire alliée pour une composition (même partielle).

        Forme directe de la formule du docstring de module. La recherche utilise
        ``contribution()`` à la place, pour l'incrémental ; les deux doivent
        toujours coïncider (test d'indépendance de l'ordre).
        """
        total = 0.0
        for index, champion in enumerate(allies):
            total += self.contribution(champion, allies[:index], enemies)
        for index, champion in enumerate(enemies):
            total -= self.contribution(champion, enemies[:index], ())
        return total

    def win_probability(self, allies: Sequence[Placed], enemies: Sequence[Placed]) -> float:
        """Probabilité de victoire alliée, dans ]0, 1[."""
        return sigmoid(self.team_logit(allies, enemies))

    @staticmethod
    def probability(logit: float) -> float:
        """Conversion logit -> probabilité, pour les appelants qui composent
        eux-mêmes leur logit via ``contribution()`` (la recherche)."""
        return sigmoid(logit)
