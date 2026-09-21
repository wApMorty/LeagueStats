# SPEC-13 — Le shrink des tables de paires se mesure, il ne se devine pas

**Statut** : 🟢 **Implémenté** (2026-09-20), en attente de validation avant merge.

**Origine** : @pj35 — « J'aimerais m'inspirer des travaux en neural network de xPetu sur Coachless
pour le calcul de win chance dans notre algo. » La réponse à cette question est *non* (§1), mais
l'enquête menée pour y répondre a mis au jour un défaut réel du modèle (§2), et c'est lui que
cette spec corrige.

---

## 1. Pourquoi il n'y aura pas de réseau de neurones

Deux options ont été étudiées puis écartées, l'une sur un raisonnement, l'autre sur une mesure.

**Un NN draft → win chance entraîné sur des parties brutes** est hors d'atteinte : la table
`predictions` contient 53 parties labellisées. La littérature plafonne vers 55-58 % d'accuracy sur
la draft seule avec 10⁵-10⁶ parties. Collecter ce volume via l'API Riot match-v5 (100 req/2 min en
clé dev) demanderait des semaines *avant* la première ligne de modèle, et un NN sur la composition
entière détruirait la propriété de décomposition dont dépend `src/draft/search.py` : le minimax
réévaluerait une composition complète par nœud au lieu d'empiler des `contribution()`.

**Des embeddings de champions appris sur les tables agrégées qu'on possède déjà** (30 562 matchups,
24 760 synergies) était l'option séduisante : apprendre un vecteur par champion tel que
`f(v_i, v_j) ≈ delta2(i→j)`, pour imputer les paires à faible échantillon aujourd'hui écrasées par
`confidence()`. Elle a été **testée et réfutée**.

Modèle antisymétrique par construction, `d(i→j) ≈ (b_i − b_j) + (⟨u_i,v_j⟩ − ⟨u_j,v_i⟩)`, évalué en
held-out sur les paires à fort échantillon :

| lane   | baseline « prédire 0 » | k=0 (biais seuls) | k=4  | k=16  |
|--------|-----------------------:|------------------:|-----:|------:|
| top    | 1.98                   | 2.06              | 3.30 | 16.15 |
| middle | 1.97                   | 1.99              | 11.80| 26.60 |
| bottom | 1.76                   | 1.81              | 4.88 | 12.58 |

(RMSE en points de winrate, pondérée par `games`, régularisation relâchée.)

Le modèle apprend parfaitement le train (top : 3.69 → 1.39 à k=16) et le test **explose**. Il
mémorise intégralement du bruit d'échantillonnage. Sous régularisation forte, `U` et `V`
convergent vers 0 et le modèle **devient** la baseline « prédire zéro ». Autrement dit : les
paires held-out sont imprédictibles depuis les autres paires — l'hypothèse de rang faible est
fausse sur cette donnée, et c'était exactement ce que l'approche promettait d'exploiter.

## 2. Ce que l'enquête a trouvé à la place

Deux mesures, sur la table réelle :

```
sd(delta2) toutes paires confondues (top) : 6.10 pp
sd(delta2) sur les paires à n >= 500      : 1.98 pp
```

Les gros deltas de la table sont presque tous des artefacts de petit échantillon. Et
l'antisymétrie fournit une mesure du bruit **sans modèle** : pour une paire observée dans les deux
sens, `d(i→j) + d(j→i)` devrait valoir 0 ; l'écart observé est le bruit. Résultat : **30 à 70 % de
la variance de `delta2` est du bruit d'échantillonnage pur**, jusqu'à 71 % sur top.

Le modèle traitait donc ce bruit comme du signal, parce que `CONFIDENCE_K = 500` était une valeur
de convention. Sa justification d'origine en commentaire (« la médiane de la base est ~1 300
parties ») était fausse de surcroît : la médiane mesurée est de **225 parties**.

## 3. La correction : K se calcule

Modèle de mesure d'un delta : `d_obs = d_vrai + bruit`, avec `d_vrai ~ N(0, var_signal)` et
`bruit ~ N(0, C/n)`. `C = 10000·p(1−p)` est la variance binomiale d'un winrate en points de
winrate², soit ~2500 autour de p=0.5 — une constante **physique**. Mesurée indépendamment sur les
cinq lanes par régression de `mean(d²)` sur `1/n`, elle retombe entre **2284 et 2617** : le modèle
de bruit est juste, ce n'est pas un ajustement de courbe heureux.

Le poids bayésien optimal d'une mesure est alors :

```
var_signal / (var_signal + C/n)  =  n / (n + C/var_signal)
```

C'est **exactement** la forme de `confidence(n)`, avec `K = C / var_signal`. La formule n'avait
pas besoin de changer — seule sa constante était arbitraire.

**Seul `var_signal` dépend de la méta**, d'où un K recalculé à chaque scrape (`src/pipeline.py`)
et stocké dans `db_meta`, plutôt qu'une constante qui vieillit en silence. C'était la condition
posée par @pj35 pour valider cette approche : « il faudrait idéalement le calculer plutôt que le
mesurer ponctuellement. »

### Pourquoi un MLE et pas la méthode des moments

`var_signal = moyenne(d² − C/n)` est non biaisé et tient en une ligne, mais soustrait deux grands
nombres pour en obtenir un petit : à n=100 le terme de bruit vaut ~25 pp² quand le signal en vaut
~1. Mesuré, cet estimateur donne **0.91 à 3.17** selon la lane. Le MLE à 1 paramètre — qui pondère
chaque ligne par sa précision — donne **1.14 à 1.37**, avec des intervalles bootstrap à 90 % qui
se recouvrent tous.

**Conséquence de conception** : la variation apparente entre lanes était du bruit d'estimateur,
pas de la méta. D'où un K par **type** (matchup / synergie) et non par lane, comme envisagé au
départ — les lanes sont d'accord à ±15 %, les types diffèrent d'un facteur 3.

### Valeurs mesurées

| table     | var_signal (pp²) | K mesuré | K précédent |
|-----------|-----------------:|---------:|------------:|
| matchups  | 1.14 – 1.37      | **1897** | 500         |
| synergies | 0.12 – 0.60      | **6460** | 500         |

Les synergies portent 3 à 10 fois moins de signal que les matchups — sur top et jungle, `var_signal`
n'est pas distinguable de zéro. Le `K_SYNERGY = 0.5` existant allait dans le bon sens mais très
loin du compte.

## 4. Effet observable

Poids accordé à une paire selon son échantillon :

| n     | avant (K=500) | matchup (K=1897) | synergie (K=6460) |
|-------|--------------:|-----------------:|------------------:|
| 80    | 0.138         | 0.040            | 0.012             |
| 225   | 0.310         | 0.106            | 0.034             |
| 2000  | 0.800         | 0.513            | 0.236             |
| 8000  | 0.941         | 0.808            | 0.553             |

À l'échantillon médian, un matchup pèse désormais **3 fois moins**. Les probabilités affichées se
rapprochent de 50 % (une draft 3v3 d'exemple : 51.9 % → 50.9 %), et surtout **le classement des
recommandations change** : un pick porté par un delta spectaculaire à faible échantillon recule au
profit des matchups réellement mesurés. C'est l'effet recherché, pas un effet de bord.

## 5. Ce qui a été implémenté

- `src/analysis/shrink.py` (nouveau, 185 lignes) — MLE, estimation, lecture/écriture `db_meta`.
  Bissection en Python pur, aucune dépendance nouvelle (même parti pris que
  `calibration.suggest_scale`).
- `src/analysis/probability.py` — `confidence(games, k=None)`. Le défaut `None` retombe sur
  `CONFIDENCE_K` : les 14 appelants d'avant SPEC-13 sont inchangés, bit pour bit.
- `src/analysis/game_eval.py` — lit les deux K une fois à la construction (la recherche fait des
  dizaines de milliers d'appels et ne peut pas relire `db_meta` à chacun).
- `src/pipeline.py` — `refresh_shrink_k(db)` après chaque recompute.
- `src/config_constants.py` — bornes de sécurité, `MODEL_VERSION` → `spec13-v1`.
- `tests/test_shrink.py` (18 tests) + 2 tests de câblage dans `tests/test_game_eval.py`.

Le test central est `test_mle_recovers_known_variance` : on fabrique des deltas dont on **connaît**
la variance de signal et on vérifie que l'estimateur la retrouve (±20 % sur 6000 échantillons). Sur
des données réelles la vraie valeur est justement l'inconnue — c'est la seule façon de valider un
estimateur.

## 5bis. Corrections après la première mise en service (2026-09-21)

Deux défauts révélés par la première partie jouée sous `spec13-v1`.

**Le repli était silencieux.** `read_shrink_k()` retombe sur `CONFIDENCE_K` quand `db_meta` ne
contient pas encore de K — c'est le bon comportement sur une base non migrée, mais rien ne le
disait. @pj35 a joué une partie en croyant le nouveau shrink actif alors que le pipeline n'avait
pas été relancé : la prédiction #60 (68,8 %) a été produite par l'ancien modèle. Dans un projet
qui a une spec entière intitulée « ignorance visible » (SPEC-09), c'était la faute exacte que
cette spec existe pour empêcher. `shrink_is_measured(db)` expose désormais l'information, et
`DraftMonitor` affiche une ligne au démarrage de session quand les poids ne sont pas mesurés.

**Le compteur de prédictions ignorait `model_version`.** `count_labelled_predictions()` annonçait
« 54 labellisées / 30 requises » juste après le bump, en additionnant quatre générations de modèle
(b7-v1 : 31, b7-v1+lane-restante : 16, spec12-v1 : 5, spec13-v1 : 2). Deux conséquences :

1. le message contredisait `scripts/calibrate_model.py`, qui filtre et aurait refusé de calibrer ;
2. surtout, `lane_restante.is_enabled()` s'appuie sur ce même compteur pour activer la pondération
   SPEC-11. Le garde-fou s'ouvrait donc sur des parties jouées sous un **autre** modèle — une éval
   déclarée éprouvée par l'expérience acquise avec une autre, exactement ce que le garde-fou
   existe pour empêcher.

Le paramètre `model_version` est désormais **obligatoire** (passer `None` explicitement pour le
total) : c'est l'absence de défaut qui empêche la récidive. `is_enabled()` filtre sur
`analysis_config.MODEL_VERSION` brut et jamais sur `effective_model_version()`, qui l'appelle et
bouclerait ; depuis SPEC-12 le Live Coach journalise la constante sans suffixe, donc l'égalité
stricte est exacte et stable.

**Conséquence assumée** (choix de @pj35 entre trois options) : la pondération par lane restante se
désactive jusqu'à 30 parties labellisées sous `spec13-v1`. C'est la sémantique voulue du garde-fou
— le modèle d'évaluation vient de changer, il n'est pas éprouvé.

Régression couverte par `tests/regression/test_regression_prediction_count_model_version.py`
(4 des 5 tests échouent sur le code d'avant le fix).

## 6. Hors périmètre

- **`scoring.py` / `champion_scores.py` / `lane_restante.py` gardent `CONFIDENCE_K = 500.`** Ils
  utilisent `confidence()` comme poids de *moyenne pondérée*, où seul le poids relatif entre lignes
  compte : l'effet d'un changement de K y est du second ordre, contrairement à `game_eval.py` où
  `confidence()` multiplie le delta et shrinke donc réellement vers zéro. Les basculer toucherait
  la tier list, autre périmètre, autre rayon d'impact.
- **Les 53 prédictions en `spec12-v1` ne sont pas rejouables.** Le bump de `MODEL_VERSION` les
  isole ; le compteur de `MIN_ROWS_FOR_CALIBRATION` repart de zéro. Inévitable, et c'est
  précisément ce que la constante `MODEL_VERSION` sert à garantir.
- **Rien ne valide encore que le win chance est *mieux* calibré.** 53 parties ne permettent pas de
  le mesurer. La correction repose sur un modèle de bruit validé (C ≈ 2500 sur 5 lanes
  indépendantes), pas sur une amélioration observée du Brier score. À revérifier via
  `scripts/calibrate_model.py` quand la boucle SPEC-08 aura reconstitué un échantillon.
