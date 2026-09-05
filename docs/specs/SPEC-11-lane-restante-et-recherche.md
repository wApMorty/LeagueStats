# SPEC-11 — Pondération par lane restante, puis recherche façon Stockfish

**Statut** : 🔵 **Recherche — non actionable en l'état.** Ceci n'est pas une spec prête à
implémenter comme SPEC-08 à SPEC-10 : c'est la mise en forme d'une discussion produit
(@pj35, 2026-09-06) pour qu'elle ne se perde pas. **Ne pas lancer d'agent d'implémentation
dessus avant que la condition de déblocage du §3 soit remplie.**

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

## 3. Condition de déblocage — pourquoi ce n'est pas actionable maintenant

**Une recherche amplifie les erreurs de son évaluation.** Chercher profond avec des
`K_MATCHUP`/`K_SYNERGY`/`SAME_LANE_WEIGHT` jamais calibrés (voir `docs/specs/SPEC-08-boucle-de-
mesure.md` — l'infra de mesure existe mais n'a produit sa première donnée que le 2026-09-06)
produirait des recommandations **très confiantes et potentiellement très fausses** — pire que le
modèle actuel, qui au moins reste modeste en ne cherchant pas.

**Séquence obligatoire, chaque étape validée sur le Brier score de la précédente**
(`scripts/calibrate_model.py`, `MIN_ROWS_FOR_CALIBRATION = 30`) :

1. ✅ **SPEC-08** (fermer la boucle de mesure) — mergée le 2026-09-06. Les résultats de partie
   entrent en base automatiquement.
2. ⏳ **Calibration réelle** — accumuler ~30 parties labellisées, exécuter
   `scripts/calibrate_model.py`, ajuster `K_MATCHUP`/`K_SYNERGY`/éventuellement
   `SAME_LANE_WEIGHT` si le score de Brier le justifie (bump `MODEL_VERSION` obligatoire).
3. ⏳ **Pondération par lane restante** (§1, ce document) — évolution incrémentale de l'éval
   existante, validée en comparant le Brier score avant/après sur le même jeu de parties.
4. ⏳ **Recherche minimax** (§2, ce document) — seulement une fois l'éval de l'étape 3 elle-même
   calibrée. Sans quoi on chercherait profond sur un board faux.

Ce document existe pour que l'idée ne se reperde pas d'ici l'étape 2, pas pour être exécuté
maintenant.

## 4. Pistes techniques à ne pas perdre (pour quand ce sera débloqué)

Notes de cadrage, volontairement non détaillées à l'implémentation (les fichiers concernés auront
bougé d'ici là — inutile de spécifier des numéros de ligne qui seront faux) :

- **Étape 3 (lane restante)** : le point d'entrée naturel est `_lane_weight()` /
  `score_against_team()` dans `src/analysis/scoring.py` — remplacer la pondération binaire
  same-lane/other-lane par une pondération proportionnelle à la probabilité que chaque lane
  ennemie encore ouverte soit occupée par un contre direct, dérivée de `champion_lanes.share` sur
  les candidats plausibles restants. Prudence sur la performance : ne pas réintroduire de requête
  SQL par candidat dans la boucle chaude du Live Coach (le pattern `get_all_matchups_bulk()` /
  `matchup_cache.py` existe déjà pour éviter ça).
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

- ❌ Toute implémentation avant que l'étape 2 (calibration réelle) ait produit un premier verdict.
- ❌ Réseau de neurones / évaluation apprise façon NNUE (Stockfish moderne) — bien au-delà du
  besoin d'un outil personnel, et sans le volume de données pour l'entraîner.
- ❌ Modéliser les bans adverses dans la recherche dans un premier temps — déjà complexe avec les
  seuls picks ; à réévaluer une fois l'étape 4 stable.
