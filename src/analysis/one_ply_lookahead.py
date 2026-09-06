"""SPEC-11 (étage b, portée "1 ply glouton") — robustesse face à la
meilleure réponse ennemie plausible.

Constat (SPEC-11 §2) : le modèle log-odds actuel est une évaluation
statique — il note un candidat contre le board *actuel*, jamais contre ce
que l'ennemi pourrait encore jouer. La valeur d'un pick, surtout early,
c'est sa robustesse face à la pire réponse *réaliste*, pas juste son score
contre ce qui est déjà posé.

Conception (et un piège évité) : la première version de ce module
simulait "l'ennemi ajoute son pire pick plausible à l'équipe" en rejouant
score_against_team() avec ce candidat ajouté à `team`. Écrit puis testé,
ça s'est révélé **non monotone** : retirer le pire candidat du pool
"aveugle" pour le rendre "connu" peut faire *remonter* la moyenne de ce
qu'il reste dans ce pool, au point de rendre le score final *meilleur*
qu'avant l'ajout -- l'inverse de ce qu'un pire cas doit garantir. Vérifié
empiriquement en écrivant les tests de ce module (tests/test_one_ply_
lookahead.py), pas supposé.

Le calcul retenu ici évite ce piège : c'est un terme additionnel, jamais
une resimulation. `worst_case_term()` calcule la moyenne des `top_k` pires
delta2 plausibles restants et la retourne comme AJOUT à la contribution des
slots inconnus de score_against_team() (voir son câblage dans
src/analysis/scoring.py), sans jamais retirer quoi que ce soit du pool qui
sert à la moyenne existante. Puisque min/moyenne d'un sous-ensemble est
toujours <= moyenne de l'ensemble, ce terme ne peut par construction que
dégrader ou laisser inchangé le score -- jamais l'améliorer. Coût nul en
requêtes DB supplémentaires : tout est déjà chargé dans `available_matchups`.

Toujours pas un vrai minimax multi-plis (SPEC-11 §4, hors périmètre) : un
seul terme de risque, pas de récursion, pas de modélisation de l'ordre des
tours de pick/ban.

Garde-fou (@pj35, 2026-09-06) : partage l'interrupteur de l'étage a
(ChampionScorer._is_lane_restante_enabled(), même seuil
analysis_config.MIN_ROWS_FOR_CALIBRATION) -- pas de seuil séparé.
"""

from typing import List, Tuple

from ..config_constants import analysis_config
from ..models import Matchup


def worst_case_term(scorer, available_matchups: List[Matchup], top_k: int) -> Tuple[float, float]:
    """(delta2, poids) du terme de risque à ajouter à la contribution des
    slots ennemis encore inconnus dans score_against_team().

    Moyenne des `top_k` pires delta2 parmi les matchups plausibles
    (filter_valid_matchups -- même seuil pickrate/games que le reste du
    scoring), poids fixe `analysis_config.LOOKAHEAD_WEIGHT`. (0.0, 0.0) si
    aucun candidat plausible ne reste (rien à ajouter, jamais une valeur
    inventée).
    """
    valid = scorer.filter_valid_matchups(available_matchups)
    if not valid:
        return 0.0, 0.0

    worst = sorted(valid, key=lambda m: m.delta2)[:top_k]
    worst_avg = sum(m.delta2 for m in worst) / len(worst)
    return worst_avg, float(analysis_config.LOOKAHEAD_WEIGHT)
