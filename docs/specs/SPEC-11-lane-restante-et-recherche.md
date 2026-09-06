# SPEC-11 — Pondération par lane restante, puis recherche façon Stockfish

**Statut** : 🟡 **Étage a ET étage b (portée "1 ply glouton") implémentés, en attente de
validation avant merge** (2026-09-06). Aucun des deux n'est encore sur master. Détail de ce qui a
été livré : §3bis (étage a), §3ter (étage b). Les deux partagent le même interrupteur automatique
plutôt qu'une attente manuelle — décision explicite de @pj35, qui révise la séquence d'origine du
§3 pour l'étage a, puis à nouveau pour l'étage b sous une forme volontairement réduite (§3ter).

**Le vrai minimax multi-plis (§2, §4) reste 🔵 non actionable.** Ce qui est livré pour l'étage b
n'est PAS ce minimax — c'est une version délibérément réduite ("1 ply glouton", choisie par
@pj35 parmi 3 options proposées), sans récursion ni modélisation de l'ordre des tours de draft. Le
vrai minimax multi-plis attend toujours une calibration réelle (§3).

**Origine** : @pj35 — « le modèle actuel fait une moyenne pondérée ; il faudrait au minimum une
moyenne pondérée par lane restante, et idéalement une recherche façon Stockfish qui anticipe les
meilleurs picks. »

---

## 1. Le constat sur le modèle actuel

`ChampionScorer.score_against_team()` (`src/analysis/scoring.py:178`) pondère chaque ennemi déjà
pické par proximité de lane via `_lane_weight()` (`src/analysis/scoring.py:160`) :
`SAME_LANE_WEIGHT = 2.0` pour l'ennemi qui partage notre lane, `OTHER_LANE_WEIGHT = 1.0` pour le
reste (`src/config_constants.py:263-264`). C'est une pondération sur le **board visible**.

Ce qui manque : rien ne représente le risque des **lanes ennemies pas encore pickées**. Un
candidat évalué comme excellent contre les 2-3 ennemis déjà posés peut être un pick fragile si la
lane la plus dangereuse pour lui reste ouverte côté adverse — ce risque n'entre nulle part dans le
calcul actuel. Un pick early engage contre des inconnues, pas seulement contre ce qui est visible.

Les données nécessaires existent déjà et ne demandent aucun nouveau scrape :
`champion_lanes.share` (table peuplée par `role_inference.py`, exploitée pour l'inférence de rôle
des champions **déjà pickés** — `_log_share()`, `src/role_inference.py:33`) donne, pour un
champion candidat côté ennemi, la distribution de probabilité de sa lane. Combinée à la liste des
lanes encore ouvertes, elle donne une vraie loi de probabilité sur "qui va arriver où" plutôt qu'un
board figé.

## 2. L'ambition Stockfish : ce qui existe déjà et ce qui manque

Le modèle log-odds actuel (`win_probability`, `K_MATCHUP`/`K_SYNERGY`,
`src/analysis/probability.py` + `src/analysis/scoring.py`) est **l'analogue exact de la fonction
d'évaluation statique de Stockfish** (son score centipawn) : une note de position à profondeur
zéro, sans anticipation. Ce qui manque, structurellement, ce n'est pas une nouvelle évaluation —
c'est la **recherche par-dessus**.

La draft s'y prête mieux qu'il n'y paraît :

- **Information parfaite** : aucun coup caché contrairement au poker, l'état est entièrement
  observable à chaque tour (à l'inférence de lane près, déjà gérée par `role_inference.py`).
- **Ordre de pick/ban fixe et connu** à l'avance (contrairement aux échecs où l'adversaire peut
  jouer n'importe quel coup légal, la séquence bans/picks de LoL est un arbre dont la forme est
  connue dès le départ).
- **Profondeur bornée nativement** : ~10 picks (5 par équipe) contre ~80 demi-coups pour une
  partie d'échecs complète — un ordre de grandeur plus court.
- **Facteur de branchement apparent élevé (~170 champions) mais qui s'effondre à l'élagage** :
  côté allié, seuls les champions de la pool active sont jouables (déjà filtré partout dans le
  code, `current_pool`) ; côté ennemi, on peut se restreindre aux N candidats plausibles par un
  score composite pickrate × probabilité de lane restante (§1) × position en tier list
  (`champion_scores`, déjà calculée). À 20-30 candidats par coup sur 4-6 plis utiles (on n'a pas
  besoin de dérouler toute la draft pour évaluer un premier pick), c'est calculable dans le temps
  d'une session de draft (~30 s par phase de pick, contrainte molle contrairement aux échecs en
  blitz).

Ce que la recherche minimax capturerait, que le modèle actuel ne peut pas capturer par
construction : la valeur d'un blind pick n'est pas son score contre le board actuel (vide, par
définition) mais sa **robustesse face à la meilleure réponse adverse** sur l'ensemble des
lanes/picks à venir — exactement la question qu'un joueur se pose en premier pick, et à laquelle
`get_best_champion_from_pool()` (`src/draft/automation.py`, SPEC-09 E3) ne répond aujourd'hui que
par un score statique.

## 3. Condition de déblocage — pourquoi la recherche (étage b) n'est pas actionable maintenant

**Une recherche amplifie les erreurs de son évaluation.** Chercher profond avec des
`K_MATCHUP`/`K_SYNERGY`/`SAME_LANE_WEIGHT` jamais calibrés (voir `docs/specs/SPEC-08-boucle-de-
mesure.md` — l'infra de mesure existe mais n'a produit sa première donnée que le 2026-09-06)
produirait des recommandations **très confiantes et potentiellement très fausses** — pire que le
modèle actuel, qui au moins reste modeste en ne cherchant pas. Cet argument reste entier pour
l'étage b, ci-dessous — c'est spécifiquement la composition d'une erreur sur plusieurs plis de
recherche qui l'amplifie, pas un raffinement d'éval à un seul niveau (voir §3bis pour pourquoi
l'étage a n'est pas soumis au même risque).

**Séquence d'origine (2026-09-06, matin), chaque étape validée sur le Brier score de la
précédente** (`scripts/calibrate_model.py`, `MIN_ROWS_FOR_CALIBRATION = 30`) :

1. ✅ **SPEC-08** (fermer la boucle de mesure) — mergée le 2026-09-06. Les résultats de partie
   entrent en base automatiquement.
2. ⏳ **Calibration réelle** — accumuler ~30 parties labellisées, exécuter
   `scripts/calibrate_model.py`, ajuster `K_MATCHUP`/`K_SYNERGY`/éventuellement
   `SAME_LANE_WEIGHT` si le score de Brier le justifie (bump `MODEL_VERSION` obligatoire).
3. ✅→🔵 **Pondération par lane restante** — **révisé le 2026-09-06 (soir)**, voir §3bis : au lieu
   d'attendre la fin de l'étape 2, @pj35 a demandé d'implémenter tout de suite, protégé par un
   interrupteur automatique sur le volume de données plutôt que par une attente manuelle.
4. ⏳ **Recherche minimax** (§2, ce document) — reste après une éval déjà calibrée (étape 2, puis
   étage a une fois lui-même mesuré). Sans quoi on chercherait profond sur un board faux.

Ce document existe pour que l'ambition de l'étage b ne se perde pas d'ici l'étape 2, pas pour être
exécuté maintenant.

## 3bis. Ce qui a été implémenté (étage a, 2026-09-06)

**Pourquoi ce n'est pas le même risque que l'étage b** : la mise en garde du §3 vise
spécifiquement une *recherche* qui composerait une erreur d'éval sur plusieurs plis. La
pondération lane restante n'est pas une recherche — c'est un raffinement local, à un seul niveau,
d'un calcul (la dilution des picks ennemis encore inconnus) qui utilisait déjà une moyenne neutre
tout aussi peu calibrée. Elle ne rend pas le modèle plus confiant dans l'absolu, elle rend juste
cette moyenne moins aveugle à une information déjà disponible (`champion_lanes.share`).

**Le garde-fou retenu** : plutôt qu'une attente manuelle avant d'écrire le code,
`src/analysis/lane_restante.is_enabled(db)` interroge `db.count_labelled_predictions()` à chaque
session et n'active le nouveau calcul qu'à partir de `analysis_config.MIN_ROWS_FOR_CALIBRATION`
(30, la même barre que la calibration). En dessous, le calcul reproduit exactement la formule
pré-SPEC-11 (vérifié par test : mêmes arguments avec/sans `player_lane` ⇒ même score).

**Traçabilité de la calibration** : `ChampionScorer.effective_model_version()` /
`Assistant.effective_model_version()` suffixent `analysis_config.MODEL_VERSION` en
`"<version>+lane-restante"` dès que l'interrupteur est actif, et
`src/draft/final_analysis.py` journalise désormais ce libellé (plus la constante brute) à chaque
prédiction. Une future exécution de `scripts/calibrate_model.py` peut donc filtrer par
`model_version` et comparer honnêtement les deux régimes sans qu'ils se mélangent — c'est ce qui
rend la révision de séquence du §3 acceptable : la validation a posteriori (Brier score par
régime) reste possible, seulement décalée après coup plutôt qu'exigée avant coup.

**Le calcul lui-même** (`src/analysis/lane_restante.py`, appelé depuis
`ChampionScorer.score_against_team()`) : parmi les slots ennemis encore inconnus (« blind
picks »), si notre lane (`player_lane`) n'est pas déjà occupée par un ennemi pické, un des slots
est traité comme « l'ennemi qui finira dans notre lane » — pondéré `SAME_LANE_WEIGHT` (au lieu de
`OTHER_LANE_WEIGHT`) et estimé par une moyenne de `delta2` pondérée non seulement par
`pickrate × confidence(games)` (comme l'existant) mais aussi par la plausibilité de chaque
candidat sur cette lane (`champion_lanes.share`, plancher `EPSILON` comme dans
`role_inference.py` — jamais un poids nul). Les autres slots inconnus gardent le calcul
inchangé. `Database.get_lane_distributions_by_name()` (nouveau, réutilise
`get_all_champion_lane_distributions()` et son repli sur le volume de matchups) fournit ces
données en un seul chargement par instance, jamais requêté par candidat.

**Scope volontairement limité** : ne touche que la branche `score_against_team()` avec au moins un
ennemi déjà pické. Le pick totalement à l'aveugle (`team=[]`, ex.
`HoverAutomation.get_best_champion_from_pool()`) ne reçoit aujourd'hui ni `player_lane` ni
`enemy_lanes` à cet appel — l'étendre au vrai blind pick est un gap séparé, plus petit, non traité
ici.

Tests : `tests/test_lane_restante.py` (formule pure, calcul à la main vérifié), 
`tests/test_scoring_lane_restante.py` (interrupteur, mise en cache par instance,
`effective_model_version`), extensions de `tests/test_champion_lanes_table.py`,
`tests/test_assistant_integration.py`, `tests/test_draft_monitor_final_scores_display.py`.

## 3ter. Ce qui a été implémenté (étage b, portée "1 ply glouton", 2026-09-06)

**Décision de portée** : @pj35 a demandé d'engager l'étage b protégé par le même garde-fou que
l'étage a plutôt que d'attendre. Trois approches ont été proposées (1 pli glouton / vrai minimax
multi-plis / outil à la demande isolé du Live Coach) ; **1 pli glouton** a été retenue — pas de
récursion, pas de modélisation de l'ordre des tours de pick/ban (qui diffère entre SoloQ et
format tournoi, tranché hors périmètre).

**Un vrai bug de conception trouvé et corrigé en écrivant les tests, avant tout câblage en
production** : la première implémentation simulait « l'ennemi ajoute son pire pick plausible à
l'équipe » en rejouant `score_against_team()` avec ce candidat ajouté à `team`. Empiriquement
**non monotone** : retirer le pire candidat du pool "aveugle" pour le rendre "connu" peut faire
*remonter* la moyenne de ce qu'il reste dans ce pool, au point de rendre le score final
**meilleur** qu'avant l'ajout — l'inverse de ce qu'un pire cas doit garantir. C'est exactement le
genre d'effet que la mise en garde du §3 anticipait, découvert ici par une voie différente
(propriété structurelle de la formule de dilution, pas un biais de calibration).

**Conception retenue à la place** : un terme additif, jamais une resimulation.
`src/analysis/one_ply_lookahead.py::worst_case_term()` moyenne les `LOOKAHEAD_TOP_K` (3) pires
`delta2` plausibles restants (parmi ceux qui passent `filter_valid_matchups`, même seuil que le
reste du scoring) et l'**ajoute** — jamais ne le substitue — à la contribution des slots ennemis
encore inconnus dans `score_against_team()`, avec un poids `LOOKAHEAD_WEIGHT` (1.0). Comme
min/moyenne d'un sous-ensemble est toujours ≤ la moyenne de l'ensemble entier, ce terme ne peut
**par construction** qu'égaler ou dégrader le score — jamais l'améliorer. Propriété vérifiée par
test (`test_gated_score_is_never_better_than_the_ungated_score`).

Coût : nul en requêtes DB supplémentaires (tout vient de `available_matchups`, déjà chargé pour
l'étage a) — contrairement à la conception initiale, qui aurait rejoué `score_against_team()`
(donc `get_matchup_delta2`) plusieurs fois par candidat. Câblé directement dans
`ChampionScorer.score_against_team()` (via `ScoringGateMixin._blind_slots_contribution()`,
`src/analysis/lane_restante.py`) — s'applique donc partout où `score_against_team()` est appelé
(Live Coach, Team Builder, Tournament Coach), pas seulement au Live Coach, précisément parce que
le coût est négligeable.

Tests : `tests/test_one_ply_lookahead.py` (formule pure du terme, plancher `MIN_PICKRATE`,
monotonie de bout en bout sur `score_against_team()`).

## 4. Pistes techniques à ne pas perdre (pour quand ce sera débloqué)

Notes de cadrage pour l'étage b, volontairement non détaillées à l'implémentation (les fichiers
concernés auront bougé d'ici là — inutile de spécifier des numéros de ligne qui seront faux).
L'étage a (lane restante) est fait — voir §3bis.

- **Étape 4 (recherche)** : minimax avec élagage alpha-bêta, profondeur = plis restants de la
  draft (borné, donc pas besoin d'itérative deepening façon Stockfish). Générateur de coups côté
  ennemi = top-N par score composite (§2). Fonction d'évaluation aux feuilles = le modèle log-odds
  calibré de l'étape 2/3, jamais une nouvelle heuristique ad hoc. Budget de calcul à définir
  empiriquement une fois l'étape 3 en place (le nombre de candidats plausibles par lane, mesuré
  sur la vraie distribution `champion_lanes`, dira si l'élagage suffit ou s'il faut un budget de
  profondeur adaptatif).
- **Ne pas** introduire de dépendance ML/scipy pour ça (cohérent avec SPEC-05 §8, « hors
  périmètre ») — le minimax alpha-bêta est un algorithme, pas une bibliothèque.

## 5. Hors périmètre (pour l'instant)

- ❌ Le **vrai minimax multi-plis** (§2, §4) — le "1 ply glouton" livré en §3ter n'en est PAS une
  version partielle à étendre directement : la modélisation de l'ordre des tours de pick/ban, la
  récursion et le budget de calcul restent entièrement à faire, et attendent toujours une
  calibration réelle (étape 2, §3) avant d'être engagés, pour les raisons du §3 (une recherche
  multi-plis compose l'erreur de son évaluation à chaque niveau — contrairement au terme additif
  et monotone de l'étage b actuel, qui ne compose rien).
- ❌ Étendre l'étage a au vrai blind pick (`team=[]`) sans d'abord câbler `player_lane`/
  `enemy_lanes` jusqu'à ce point d'appel (gap séparé, noté en §3bis).
- ❌ Réseau de neurones / évaluation apprise façon NNUE (Stockfish moderne) — bien au-delà du
  besoin d'un outil personnel, et sans le volume de données pour l'entraîner.
- ❌ Modéliser les bans adverses dans la recherche dans un premier temps — déjà complexe avec les
  seuls picks ; à réévaluer une fois l'étape 4 stable.
