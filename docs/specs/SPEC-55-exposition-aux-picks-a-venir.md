# SPEC-55 — Exposition aux picks à venir : l'Arbre classe par la règle D

**Statut** : ✅ Livrée le 2026-11-09, recette @pj35 à faire (draft classée réelle sous Arbre). Écarts : les champs du
snapshot sont faits en tâche 274 avec le Live Coach (le commit restait vert) ; `_tree` sonde la base avant
`exposure_tree` (les dépôts avalent les erreurs de lecture) ; libellé Arbre de l'écran Stratégies réécrit. Mesuré sur
la base du 8 nov. : arbre de l'écran Pool 0,58 s (39 adversaires), classement D 142 ms à froid.

**Origine** : @pj35, 2026-11-09 — l'arbre de SPEC-54 ne voit que la lane, alors qu'à l'ADC la synergie avec le
support pèse autant que le duel. Pas de règle par poste : « un système qui s'appuie sur des indicateurs factuels et
reproductibles, peu importe le rôle ». Et pas d'arbre réservé au B1 : « si je dois pick top en B4 ou B5, je risque
d'être blind sur mon matchup alors que c'est l'info la plus importante ».

**Effort** : ~2 jours, 5 tâches (§5).

---

## 1. Constat

### 1.1 L'arbre ignore la moitié des signaux hors top

Mesure du 2026-11-09, `data/db.db`, 31 ADC (paires ≥ 200 parties, ADC ≥ 20 000 parties) : écart-type des `delta2`
pondéré par les parties, variance binomiale retirée.

| Partenaire de l'ADC | Écart-type débruité |
|---|---|
| Support allié (`synergies`) | 1,13 pt |
| ADC adverse (`matchups`, duel) | 1,30 pt |
| Support adverse (`matchups`) | 1,42 pt |

Le poids dépend du champion, et les matrices le portent déjà : écart entre meilleur et pire partenaire (paires
≥ 1 000 parties), Ashe 10,6 pt selon le support allié contre 3,9 selon l'ADC adverse, Jhin 8,6 contre 3,9 ; Ziggs
5,1 contre 7,9, Hwei 4,0 contre 6,4. Le score calibré additionne ces `delta2` bruts (`GameEvaluator.contribution`,
`src/analysis/game_eval.py:269`) : il s'adapte au champion sans poids par champion. L'arbre
(`src/analysis/pool_tree.py:85`) ne lit que le vis-à-vis.

### 1.2 La règle D

Score d'un candidat `c` sur la lane `l`, en logit, la même pour tous les postes :

- **connu** = `GameEvaluator.contribution((c, l), alliés, ennemis)` − tirage complet de `c`
  (`winrate_points_to_logit(draw_points * K_INTRINSIC)`) ;
- **exposition** = Σ, sur chaque lane ennemie sans champion posé, de E[min sur `POOL_BLIND_DRAWS` tirages] de
  `matchup_logit((c, l), (e, lane))`, les `e` pondérés par leur popularité sur la lane (≥ `POOL_SWIPE_MIN_POPULARITY`),
  hors champions pris, bannis et `c` lui-même ;
- un allié pas encore choisi compte pour 0 : il ne choisit pas contre moi.

Draft vide, c'est la branche blind de l'arbre ; vis-à-vis posé, c'est sa branche counter, plus le reste de la draft.

### 1.3 Rejeu

Mesure du 2026-11-09, script jeté (`replay_d.py`, scratchpad de session) : 4 841 parties de `crawl.db` (files 420 et
440, ≥ 15 min, dix postes connus), 67 774 décisions. Ordre de pick B1 R1 R2 B2 B3 R3 R4 B4 B5 R5, champions tirés au
hasard dans leur camp (graine 54) ; chaque joueur décide avec les picks qui le précèdent. Candidats : pool désigné du
poste (`pools_by_role`), plus GRIND et QUINTET TOP au top, hors champions de la partie. Juge : victoire calibrée
(`GameEvaluator.win_probability`), reste de la partie figé. Trois hypothèses sur le vis-à-vis s'il n'est pas posé :
**figé** (son pick réel), **counter** (meilleur des 7 tirés selon la popularité, E[min]), **pire** (meilleur counter
≥ 1 %). Écart en points, IC 90 % par bootstrap sur les parties ; « PresqueComplet » = stratégie perso de @pj35
(poids 1, maîtrise 0, anticipation) avec correction de tirage, comme `_calibrated`.

Juge counter, toutes décisions :

| Pool | D − Arbre | dont aveugle hors B1 | D − PresqueComplet | n° 1 changés vs Arbre |
|---|---:|---:|---:|---:|
| Top, pool désigné | +0,34 [+0,32 ; +0,36] | +0,18 | +0,68 | 32 % |
| Top, GRIND | +0,40 [+0,38 ; +0,42] | +0,51 | −0,09 [−0,11 ; −0,08] | 30 % |
| Top, QUINTET TOP | +0,24 [+0,22 ; +0,25] | +0,17 | +0,65 | 32 % |
| Jungle | +0,53 [+0,51 ; +0,55] | +0,61 | +0,23 | 47 % |
| Mid | +0,59 [+0,57 ; +0,62] | +0,80 | +0,02 [+0,00 ; +0,03] | 62 % |
| Bot | +0,35 [+0,33 ; +0,37] | +0,16 | +0,41 | 30 % |
| Support | +0,56 [+0,54 ; +0,58] | +0,41 | +0,27 | 33 % |

- D − Arbre est positif sur les cinq postes et sous les trois juges. En aveugle hors B1 au top, D protège au moins
  autant que l'Arbre (juge counter +0,18, pire +0,23).
- PresqueComplet perd 1 à 2,4 pt en B1 : il ne pare la réponse que parmi les `SEARCH_TOP_N` champions les plus joués.
- Exposition à la lane seule au lieu de toutes les lanes : ±0,1 pt, sauf top pool désigné en B1 (−0,68 pour la lane
  seule).
- En B1 au mid, D et l'Arbre diffèrent 89 % du temps alors que l'exposition hors lane n'y change rien : l'arbre
  compare des points nets bruts, D le logit calibré (`K_MATCHUP`, `SAME_LANE_WEIGHT`, `K_INTRINSIC`). Cause probable,
  non isolée.

Limites : le juge contient les synergies, donc le gain à vis-à-vis posé est en partie acquis par construction ; seul
le vis-à-vis réagit ; pas de bans ni de maîtrise ; parties de tiers. Application d'ADR-004 : (1) mécanisme : un pick
non vu paie le counter qu'il offre ; (2) le classement ne touche pas les probabilités ; (3) effet chiffré ci-dessus.

## 2. Objectif et arbitrages

La stratégie système « Arbre » classe la draft par la règle D, sur tous les postes ; l'arbre affiché devient la
lecture de D sur une draft vide (blind) et sur le seul vis-à-vis (counters).

| Sujet | Décision |
|---|---|
| Intégration | **Validé (@pj35, 2026-11-09)** : D remplace le classement de l'Arbre, aucun bouton en plus (le plafond de 6 stratégies est atteint). Le nom « Arbre » reste : `active_strategy` des préférences ne change pas. |
| Exposition | **Validé (@pj35, 2026-11-09)** : toutes les lanes ennemies sans champion posé, comme au rejeu. |
| Maîtrise | **Validé (@pj35, 2026-11-09)** : hors de D, matrices seules, comme l'arbre et le rejeu. |
| Affichage | **Validé (@pj35, 2026-11-09)** : chaque carte donne « connu » et « exposition » en points ; la console écrit `[D]`. |
| Arbre affiché | Découle de l'intégration : écran Pool, Méta du poste et pool généré montrent D sur draft vide (colonne blind) et D face au seul vis-à-vis (une ligne par adversaire ≥ 1 %). Il ne lit plus `PoolScorer`. |
| Probabilités | Inchangées : les % restent ceux du modèle calibré (règle SPEC-46), D ne touche que l'ordre. |
| Tirage | Retiré en entier, vis-à-vis vu ou non : l'exposition chiffre déjà le risque de counter que `draw_correction` approchait par `max(tirage, 0)`. C'est la version mesurée. |
| Poste inconnu | Comme SPEC-54 : sans `player_lane`, classement immédiat force 1 et duel 1, la console le dit. |
| Égalité | Nom sans casse, ordre alphabétique. |
| Échec | Best-effort : une exception dans D rend le classement reçu de `_calibrated`, avec `[ALERTE]`, jamais d'interruption du monitoring. |
| Générateur | Hors périmètre : la sélection du générateur (SPEC-50) reste sur `pool_score`. |

## 3. Approches considérées

1. **Retenue : D, la même règle partout.** Les poids par champion viennent des matrices elles-mêmes ; l'exposition
   remplace la branche blind et protège à tout stade. Meilleure que l'Arbre sur les cinq postes au rejeu.
2. **Arbre jusqu'au premier champion connu, puis score complet (règle A).** Écartée par @pj35 : le top choisi en B4-B5
   resterait aveugle au counter, et le rejeu de SPEC-54 ne voyait pas ce risque (vis-à-vis figé).
3. **Arbre au signal dominant par champion (règle B)** : une seule dimension par champion, plus de code, non mesurée.

## 4. Détail

### 4.1 `src/analysis/exposure.py` (nouveau)

```python
Popularity = Dict[str, List[Tuple[str, float]]]  # lane -> [(champion, part des parties)], parts >= 1 %

def lane_popularity(db) -> Popularity:
    """Champions joués à POOL_SWIPE_MIN_POPULARITY au moins sur chaque lane de scraping_config.LANES,
    parts lues dans db.get_lane_winrates(lane) (games / total de la lane)."""

@dataclass(frozen=True)
class DScore:
    champion: str
    known: float     # logit : contribution calibrée − tirage complet
    exposure: float  # logit : Σ E[min] des lanes ennemies sans champion posé (≤ 0 en général)

    @property
    def total(self) -> float: ...

def d_scores(evaluator: GameEvaluator, lane: str, candidates: Sequence[str], allies: Sequence[Placed],
             enemies: Sequence[Placed], unavailable: Collection[str], popularity: Popularity) -> List[DScore]:
    """Score D de chaque candidat, trié par total décroissant puis nom sans casse (SPEC-55 §1.2)."""

def exposure_tree(evaluator: GameEvaluator, lane: str, pool: Sequence[str], popularity: Popularity) -> PoolTree:
    """L'arbre lu dans D : `blind` = d_scores draft vide ; une table par adversaire de popularity[lane],
    d_scores avec ce seul ennemi. Valeurs en points de victoire (`to_win_points`), même `PoolTree`."""
```

- E[min] : `_expected_min` de `src/analysis/pool_swipe.py:36` (déplacé ou importé, pas recopié), sur
  `(matchup_logit, part)`, `POOL_BLIND_DRAWS` tirages.
- `unavailable` : noms pris et bannis, sans casse ; `c` est exclu de ses propres tirages.
- Aucune constante nouvelle : `POOL_BLIND_DRAWS` (7) et `POOL_SWIPE_MIN_POPULARITY` (1 %) sont celles de l'arbre.

### 4.2 Live Coach

- `src/draft/recommendations.py`, `_provide`, sous `strategy.tree` avec `player_lane` : après `_calibrated`, les
  `results` sont réordonnés selon `d_scores(self.m.evaluator, player_lane, …, unavailable=pris + bannis,
  popularity=self.m.lane_popularity())`. `analysis.exposure = {champion: (known_pts, exposure_pts)}`. Console, n° 1 :
  `  [D] Ornn : connu +1,20 pt · exposition −0,85 pt`. `_tree_order` et `_print_tree` disparaissent.
- `src/draft_monitor.py` : `pool_tree` et `_pool_trees` remplacés par `lane_popularity()`, lu une fois par draft
  (cache vidé comme `_pool_trees` aujourd'hui), `None` sur échec avec un seul `[ALERTE]`.
- `src/draft/automation.py`, `get_best_champion_from_pool` : sous `strategy.tree`, le n° 1 de `d_scores` draft vide
  (bans connus exclus) ; sinon le calcul actuel.
- `Analysis` (`src/draft/snapshot.py`) : `tree: Optional[TreeLeaf]` devient `exposure: Optional[Dict[str, Tuple[float, float]]]`.

### 4.3 Carte de draft

- `SnapshotRecommendation` : `tree_value` devient `known_points: Optional[float]` et `exposure_points: Optional[float]`.
- `DraftSnapshot.tree` devient `exposure: bool` (vrai si le classement vient de D).
- `src/client/draft_view.py` : `_tree_line` devient `_exposure_line` : « Connu +1,20 · Exposition −0,85 », formaté par
  `signed` ; sans D, `_decomposition` comme aujourd'hui.

### 4.4 Arbre affiché

- `src/client/pool_tree.py`, `_tree` : `exposure_tree(GameEvaluator(db), lane, champions, lane_popularity(db))`.
- `src/client/pool_swipe.py` : `_stack` construit l'arbre du pool désigné par `exposure_tree` ; `_compute` remplit
  `GeneratedPool.tree` par `dataclasses.replace` avec `exposure_tree` sur le scrape le plus récent.
- `src/analysis/pool_generator.py` : `generate_pool` ne construit plus l'arbre, `GeneratedPool.tree` vaut `None` par
  défaut. `build_tree` reste si un appelant en a encore besoin, sinon il disparaît avec ses tests.
- `partials/pool_tree.html` et l'écran Stratégies (`src/client/strategies.py`, `partials/strategies_body.html`) :
  libellé « Arbre » expliqué comme « connu + exposition aux picks à venir ».

### 4.5 Tests

- `tests/test_exposure.py` (évaluateur factice, comme `tests/test_pool_swipe.py`) : exposition = E[min] attendu sur un
  cas à la main ; lane ennemie posée → hors de l'exposition ; pris, bannis et le candidat exclus des tirages ; allié
  non posé = 0 ; tirage retiré en entier, vu ou non ; égalité par nom ; `exposure_tree` : blind = d_scores draft vide,
  ligne de `e` = d_scores face à `e` seul.
- `tests/test_draft_monitor_recommendations.py` : sous Arbre, n° 1 = argmax D (vis-à-vis vu et non vu) ; `[D]` en
  console ; `lane_popularity` qui lève → classement reçu sans exception ; poste inconnu inchangé.
- Survol initial, snapshot, carte et vues de l'arbre : tests existants de SPEC-54 adaptés aux nouveaux champs.

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 273 | `src/analysis/exposure.py` (`lane_popularity`, `d_scores`, `exposure_tree`) + `tests/test_exposure.py` | 3 | — |
| 274 | Live Coach : Arbre classe par D dans `_provide` et le survol initial, `lane_popularity` en cache par draft, `[D]` en console, retrait de `_tree_order` / `pool_tree` + tests | 5 | 273 |
| 275 | Snapshot et carte de draft : `known_points`, `exposure_points`, `_exposure_line` + tests | 2 | 274 |
| 276 | Arbre affiché : écran Pool, Méta du poste, pool généré et libellés par `exposure_tree` + tests | 3 | 273 |
| 277 | Docs : CHANGELOG, statut de SPEC-55 et de SPEC-54 (classement remplacé), README des specs, structure | 1 | 274-276 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests de §4.5.
2. `tests/test_exposure.py` vérifie l'exposition sur un cas calculé à la main et l'exclusion des lanes posées.
3. Sous Arbre avec poste connu, le n° 1 de la draft est le premier de `d_scores` ; ses `win_probability` sont
   identiques à celles d'avant SPEC-55 pour la même draft (test).
4. `grep -rn "_tree_order\|pool_tree(" src/draft src/draft_monitor.py` ne renvoie rien.
5. Une exception dans `lane_popularity` ou `d_scores` laisse le classement de `_calibrated` et un `[ALERTE]` (test).
6. L'écran Pool et la Méta du poste lisent `exposure_tree` : `grep -n "exposure_tree" src/client/pool_tree.py src/client/pool_swipe.py`.
7. Aucune constante nouvelle en dur : `grep -n "POOL_BLIND_DRAWS\|POOL_SWIPE_MIN_POPULARITY" src/analysis/exposure.py`.
8. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec, de SPEC-54 et `docs/specs/README.md` à jour.

**Vérification de bout en bout** : une draft classée réelle sous Arbre (recette @pj35) : la carte du n° 1 affiche
« Connu … · Exposition … », la console `[D]`, et un top choisi en B4-B5 sans vis-à-vis voit son exposition non nulle.

## 7. Hors périmètre

- ❌ Poids par champion ou par poste : les matrices les portent déjà (§1.1), un coefficient en plus compterait deux
  fois l'écart, sans données pour le prouver.
- ❌ Maîtrise dans D : décision de §2 ; le n° 1 peut s'écarter du champion de confort, c'est voulu.
- ❌ Réponse des autres ennemis que le vis-à-vis, bans à venir : non mesurés.
- ❌ Sélection du générateur de pools (`pool_score`) : elle garde son blind et son counter_value (SPEC-49, SPEC-50).
- ❌ Probabilités affichées et modèle calibré : inchangés.
