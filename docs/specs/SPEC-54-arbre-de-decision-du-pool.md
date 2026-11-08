# SPEC-54 — Arbre de décision du pool

**Statut** : 🟡 Rédigée le 2026-11-08, arbitrages validés par @pj35 le même jour (§2). À implémenter après
[SPEC-53](SPEC-53-rappel-de-place-en-draft.md), qui touche les mêmes fichiers de draft (§4.9).

**Origine** : @pj35, 2026-11-08 — « Maintenant qu'on a des stratégies de construction de pool efficaces, j'aimerais
qu'on soit beaucoup plus catégoriques sur la recommandation de champion. Chaque pool devrait avoir son arbre de
décision, plus déterministe qu'une moyenne pondérée comme actuellement. »

**Effort** : ~2,5 jours, 6 tâches, 20 pts (§5).

---

## 1. Constat

### 1.1 Le classement en draft est une somme pondérée

`DraftSearch.rank` (`src/draft/search.py:116`) note chaque champion du pool par le logit de toute la draft
connue : force, duels de lane, matchups hors lane, synergies, avec les poids de la stratégie active
(`WeightedEvaluator.contribution`, `src/analysis/strategy.py:207`), plus la maîtrise et, sous anticipation, la
réponse du vis-à-vis (SPEC-48). `DraftRecommender._calibrated` (`src/draft/recommendations.py:296`) ajoute la
correction de tirage et trie. Le n° 1 dépend donc de chaque pick déjà posé, sur toutes les lanes.

Stratégie active de @pj35 le 2026-11-08 (`user_prefs.json`) : **PresqueComplet** (force, duel, hors lane,
synergie à 1, maîtrise à 0, anticipation). Pools désignés : les cinq « GÉNÉRÉ 2026-11-07 » (au top : Ornn, Shen,
Teemo, Malphite, Garen).

### 1.2 Le générateur optimise déjà une politique à deux branches

Le score d'un pool (`pool_score`, `src/analysis/pool_swipe.py:114`, SPEC-50) vaut
`½ · Σ_e popularité(e) · max_{c∈P} value'(c, e) + ½ · max_{c∈P} blind(c)`. Il suppose que le joueur prend, vis-à-vis
vu, le meilleur counter du pool contre lui, et sinon le meilleur blind exposé. Le pool est optimal **pour cette
politique**, pas pour la somme pondérée du §1.1. `generate_pool` en sort déjà les deux tables : `blind` trié et
`counters` (meilleur counter par adversaire à ≥ 3 % de popularité, `pool_generator.py:77`).

Arbre de TOP GÉNÉRÉ sur la base du 7 nov. (`last_scrape_utc` 2026-11-07T22:14) :

- blind exposé : Ornn +0,34, Shen +0,28, Teemo −0,77, Garen −1,04, Malphite −1,21 ;
- part de popularité où chacun est le meilleur counter : Malphite 32 %, Teemo 27 %, Ornn 22 %, Garen 16 %,
  Shen 4 % ;
- exemples : Darius → Teemo +3,62, Yone → Malphite +1,96, Renekton → Teemo +3,40, Jayce → Malphite +3,35.

Construction : 1,1 s par lane (`PoolEvaluator` + `draw_shifts` + tables).

Adversaires de popularité ≥ 1 % / ≥ 3 % par poste, et part des parties couvertes : top 39 (85 %) / 9 (31 %),
jungle 37 (86 %) / 9 (35 %), mid 35 (87 %) / 10 (40 %), bot 24 (93 %) / 12 (69 %), support 31 (90 %) / 11 (50 %).

### 1.3 L'arbre contre le classement actuel, rejoué

Mesure du 2026-11-08, script jeté : 245 parties top de @pj35 (`game_records`, files 420 et 440, dix postes connus),
cinq stades simulés par partie (alliés et ennemis connus tirés dans la partie, graine fixe). Le moteur est
`DraftSearch.rank` + correction de tirage, comme `_calibrated` ; l'arbre prend le meilleur counter du pool si le
vis-à-vis est posé, sinon le meilleur blind exposé. Valeur : victoire calibrée (`GameEvaluator.win_probability`)
de l'arbre moins celle du moteur, contre le reste réel de la partie figé, en points.

Pool TOP GÉNÉRÉ, même n° 1 (écart de valeur) :

| Stratégie du moteur | B1 blind | B2-B3 blind | B4-B5 blind | R3-R4 counter | R5 dernier |
|---|---|---|---|---|---|
| PresqueComplet (active) | 0 % (+0,98) | 40 % (−0,02) | 50 % (−0,36) | 65 % (−0,48) | 60 % (−0,72) |
| WIN LANE | 0 % (+0,98) | 5 % (+0,85) | 10 % (+0,77) | 94 % (−0,04) | 93 % (−0,08) |
| Simple sans maîtrise | 0 % (+0,98) | 38 % (+0,26) | 47 % (−0,35) | 72 % (−0,36) | 66 % (−0,45) |

QUINTET TOP donne le même profil (PresqueComplet : 0 / 44 / 49 / 67 / 62 %).

- En premier pick, le moteur prend Malphite (meilleure force, +1,74) et l'arbre Ornn : Malphite paie le pire
  tirage du pool (blind −1,21, tirage +0,21). L'arbre gagne +0,98 pt contre les drafts réelles.
- En fin de draft, l'arbre perd 0,3 à 0,7 pt contre PresqueComplet : il ignore les autres lanes et les synergies.
  Cette perte est jugée dans le modèle calibré, qui contient ces mêmes termes : elle est en partie circulaire.

## 2. Objectif et arbitrages

Chaque pool a un arbre de décision à deux branches, calculé sur les matrices : vis-à-vis vu, le meilleur counter
du pool contre lui ; sinon, le meilleur blind exposé ; repli au rang suivant si le choix est pris ou banni. Une
stratégie système « Arbre », par défaut, classe la draft selon cet arbre ; l'arbre se lit sur l'écran Pool, la Méta
du poste et la carte de draft.

| Sujet | Décision |
|---|---|
| Forme de l'arbre | **Validé (@pj35, 2026-11-08)** : deux branches, lane seule. Vis-à-vis vu → pool trié par `value'(c, e)` ; sinon → pool trié par `blind(c)`. Le premier disponible est le choix, les suivants les replis. Ni autres lanes, ni synergies, ni départage par le reste de la draft. |
| Intégration | **Validé (@pj35, 2026-11-08)** : stratégie système « Arbre » dans la rangée de boutons. Les % restent calibrés (règle SPEC-46), `predictions.strategy` vaut « Arbre ». |
| Maîtrise | **Validé (@pj35, 2026-11-08)** : hors de l'arbre, matrices seules, comme le générateur (SPEC-49, SPEC-50). |
| Édition | **Validé (@pj35, 2026-11-08)** : aucune, l'arbre est toujours calculé, rien n'est stocké. On change une feuille en changeant le pool ou les exclusions. |
| Affichage | **Validé (@pj35, 2026-11-08)** : écran Pool, Méta du poste (pool désigné et pool généré), carte de draft. |
| Bans | **Validé (@pj35, 2026-11-08)** : inchangés, `BanRecommender`. |
| Données | **Validé (@pj35, 2026-11-08)** : scrape actuel, comme les cartes d'échange. |
| Stratégie par défaut | **Validé (@pj35, 2026-11-08)** : `STRATEGY_DEFAULT = "Arbre"`, et la stratégie active de @pj35 bascule sur Arbre à la livraison (tâche 272). |
| Plafond de stratégies | **Validé (@pj35, 2026-11-08)** : la stratégie système « Méta » (force seule) est retirée, Arbre prend sa place ; `STRATEGY_MAX_COUNT` reste à 6. |
| Vis-à-vis sans données | Adversaire absent des valeurs de la lane (`PoolScorer.enemies`) : branche blind, comme s'il n'était pas vu. |
| Poste inconnu | Sans `player_lane` (file sans poste), pas d'arbre : Arbre classe comme une stratégie immédiate à force 1 et duel 1, et la console le dit. |
| Égalité | Nom sans casse, ordre alphabétique : l'arbre est déterministe. |
| Table affichée | Adversaires à ≥ 1 % de popularité (`POOL_SWIPE_MIN_POPULARITY`, filtre des candidats du générateur) : 85 à 93 % des parties (§1.2). La draft, elle, lit tous les adversaires. |

## 3. Approches considérées

1. **Retenue : arbre calculé, stratégie système.** Un module pur construit l'arbre sur un `PoolScorer` ; le
   Live Coach le garde en cache pour le pool et la lane de la draft. Réversible d'un clic, comparable aux autres
   stratégies par `predictions.strategy`, aucun changement du modèle calibré.
2. **Arbre à départage** : même arbre, mais le reste de la draft tranche quand deux champions sont à moins du
   bruit. Rattrape une partie de la perte de fin de draft (§1.3), mais l'arbre redevient une moyenne là où il
   compte. Écartée par @pj35.
3. **Arbre à la place des stratégies** : le plus de code retiré (`WeightedEvaluator`, écran Stratégies,
   anticipation), mais irréversible avant d'avoir des parties jouées sous Arbre. Écartée par @pj35.

## 4. Détail

### 4.1 `src/analysis/pool_tree.py` (nouveau)

Fonctions pures, sans I/O, sur un `PoolScorer` déjà construit.

```python
@dataclass(frozen=True)
class TreeChoice:
    champion: str
    value: float  # points de winrate : blind exposé, ou value' contre le vis-à-vis

@dataclass(frozen=True)
class TreeLeaf:
    branch: str  # "blind" | "counter"
    opponent: Optional[str]  # vis-à-vis de la branche counter, None en blind
    choices: Tuple[TreeChoice, ...]  # disponibles, du choix au dernier repli
    skipped: Tuple[str, ...]  # champions de l'arbre classés avant le choix et indisponibles

@dataclass(frozen=True)
class PoolTree:
    lane: Optional[str]
    blind: Tuple[TreeChoice, ...]  # tout le pool, blind décroissant
    counters: Tuple[Tuple[str, float, Tuple[TreeChoice, ...]], ...]
    # (adversaire, popularité, pool trié par value' décroissante), adversaires par popularité décroissante

    def leaf(self, opponent: Optional[str], unavailable: Collection[str]) -> TreeLeaf: ...

def build_tree(scorer: PoolScorer, pool: Sequence[str]) -> PoolTree: ...
```

- `build_tree` : `blind` trié par `(-scorer.blind(c), c.casefold())` ; pour chaque `scorer.enemies[i]`, le pool trié
  par `(-scorer.values(c)[i], c.casefold())`. Pool vide : tables vides. Doublons du pool (sans casse) retirés.
- `leaf` : `opponent` comparé sans casse aux adversaires ; trouvé → branche `counter` et sa table, sinon (`None` ou
  absent) → branche `blind`. `unavailable` comparé sans casse. `choices` = la table privée des indisponibles ;
  `skipped` = les indisponibles classés avant `choices[0]`. Tout indisponible : `choices` et `skipped` vides.
- `PoolTree.counters` porte tous les adversaires ; le filtre d'affichage (§2) est appliqué par la vue.

### 4.2 Stratégie « Arbre » : `src/analysis/strategy.py`, `src/config_constants.py`

- `Strategy` gagne `tree: bool = False`. `strategy_from_dict` et `strategy_to_dict` l'ignorent : une stratégie
  perso n'est jamais un arbre.
- `SYSTEM_STRATEGIES` : Simple, Counter, Complet, **Arbre** ; « Méta » retirée.
  `Strategy("Arbre", force=1.0, duel=1.0, other=0.0, synergy=0.0, mastery=0.0, search=False, tree=True,
  system=True)`. Les poids ne servent qu'au repli « poste inconnu » (§2) et à la victoire calibrée.
- `draft_config.STRATEGY_DEFAULT = "Arbre"` (origine : arbitrage §2). `STRATEGY_MAX_COUNT` inchangé.
- Une stratégie active « Méta » dans `user_prefs.json` retombe sur le défaut par `find_strategy`, sans code de plus.

### 4.3 Live Coach : arbre de la draft

`src/draft_monitor.py` :

```python
def pool_tree(self, lane: Optional[str]) -> Optional[PoolTree]:
    """Arbre du pool courant sur `lane`, construit une fois par (pool, lane) et par draft. None sans lane
    ou en cas d'erreur (best-effort : jamais d'exception)."""
```

Construction : `PoolScorer(PoolEvaluator(self.assistant.db, lane), draw_shifts(self.assistant.db.connection)
.get(lane, {}))`, puis `build_tree` sur `self.current_pool`. Cache `{(tuple(current_pool), lane): PoolTree}` vidé
par `DraftLifecycle._rearm_for_new_draft` (`src/draft/lifecycle.py:157`) à côté de `_reload_strategy` : une mise à
jour des données entre deux drafts est prise en compte. Erreur : `[ALERTE] Arbre du pool indisponible (...)` une
fois, `None`.

`src/draft/recommendations.py`, `_provide`, sous `strategy.tree` :

- Le calcul de `results` ne change pas (`rank` immédiat, puis `_calibrated` : victoire calibrée et `score`).
- Si `player_lane` et `self.m.pool_tree(player_lane)` existent : `leaf = tree.leaf(direct_counter_name,
  unavailable)`, `unavailable` = champions posés, bannis et `skipped` de `_split_pool` (sans données). Les
  `results` sont réordonnés selon `leaf.choices` ; un résultat absent de l'arbre passe après, dans l'ordre de
  `score`. `analysis.tree = leaf`.
- Sinon : ordre de `_calibrated` et `[INFO] Arbre : poste inconnu, classement force + duel`.
- Console, sous le titre `[PICKS]` : `[ARBRE] Blind : Ornn (+0,34 pt)` ou `[ARBRE] Counter de Darius : Teemo
  (+3,62 pts)`, suivi de ` · indisponibles avant lui : Ornn` si `leaf.skipped`.
- Le survol automatique prend le n° 1, donc le choix de l'arbre. Rien d'autre ne change (`predictions`, jauge).

`Analysis` (`src/draft/snapshot.py:154`) gagne `tree: Optional[TreeLeaf] = None`.

`src/draft/automation.py`, `get_best_champion_from_pool` (survol de début de draft) : sous `strategy.tree`, si
`player_lane` et l'arbre existent, le premier de `tree.leaf(None, sans_données).choices` ; sinon le calcul
actuel. Les champions sans données restent signalés comme aujourd'hui (SPEC-09).

### 4.4 Snapshot et carte de draft

- `DraftSnapshot` gagne `tree: Optional[Dict[str, Any]] = None` : `{"branch", "opponent", "skipped"}`.
- `SnapshotRecommendation` gagne `tree_value: Optional[float] = None`, la `value` de son `TreeChoice`.
- `src/client/draft_view.py`, `recommendations` : sous un snapshot qui porte `tree`, la ligne de la carte remplace
  la décomposition (`_decomposition`) :
  - carte 1 : `Blind · +0,34 pt` ou `Counter de Darius · +3,62 pts`, puis ` · Ornn indisponible` (noms de
    `skipped` joints par des virgules) ;
  - cartes suivantes : `Repli · +2,10 pts`.
  - Le gros chiffre (victoire immédiate calibrée) et l'écart ne changent pas.

### 4.5 Vue de l'arbre : `src/client/pool_tree.py` (nouveau)

```python
def tree_view(db_path: Union[str, Path], lane: str, champions: Sequence[str], portraits: Champions) -> Optional[dict]:
    """L'arbre prêt pour `partials/pool_tree.html` ; None sans lane, sans champion ou sur une base illisible."""
```

- Calcul en cache `functools.lru_cache` sur `(lane, tuple(champions), data_version(db_path))` (`data_version` de
  `src/client/pool_swipe.py:49`) : base ouverte en `connect_read_only`, `PoolScorer`, `build_tree`.
- Vue : `blind` (portrait, nom, valeur signée en points) et `rows` : adversaires de popularité ≥
  `POOL_SWIPE_MIN_POPULARITY`, triés par popularité, chacun avec sa popularité en %, le choix et sa valeur, et le
  premier repli et sa valeur.
- `partials/pool_tree.html` : « Vis-à-vis inconnu » suivi de l'ordre de blind, puis le tableau « Vis-à-vis → choix
  · repli ». Sans JS. Note sous le titre : « Matrices du scrape actuel, sans maîtrise. »

### 4.6 Écran Pool

- `GET /pool/arbre?nom=` (`src/client/app.py`, en `in_thread`) rend `partials/pool_tree.html` pour le pool `nom`.
  Lane : `pool_role_to_lane(pool.role)` (`src/pool_manager.py:27`), sinon le premier poste où il est désigné, sinon
  `dominant_lane` (`src/analysis/pool_value.py:86`). Pool inconnu : 404 ; lane introuvable : paragraphe « Aucun
  poste pour ce pool ».
- `partials/pool_body.html` : sous les champions du pool ouvert, un panneau `hx-get="/pool/arbre?nom=…"
  hx-trigger="load"` avec un indicateur : l'écran Pool reste instantané, l'arbre (~1 s) arrive ensuite.

### 4.7 Méta du poste

`src/client/pool_swipe.py` :

- `_stack` construit déjà un `PoolScorer` pour les cartes : il rend aussi `build_tree(scorer, champions)` du pool
  désigné, et `aside_view` l'ajoute sous la clé `tree` (vue de §4.5 sur cet arbre, sans second calcul).
- `_compute` construit l'arbre du pool généré sur `scorers[0]` et le garde dans son cache ; `_generated_view`
  expose `tree` à la place de `counters`.
- `GeneratedPool.counters` et `POOL_GEN_COUNTERS_MIN_POPULARITY` disparaissent : l'arbre les remplace.
  `_counter_rows` reste pour `counter_share`.
- `partials/meta_aside.html` : le bloc « counters » du pool généré et un bloc sous le pool du poste incluent
  `partials/pool_tree.html`.

### 4.8 Écran Stratégies

`src/client/strategies.py` : `_mode` rend « Arbre » si `strategy.tree`. `partials/strategies_body.html` : pour
Arbre, pas de poids ni de bouton Dupliquer, mais le texte « Vis-à-vis vu : le meilleur counter du pool contre lui.
Sinon : le meilleur blind exposé. Matrices seules, sans maîtrise. Les % de victoire ne changent pas. »

### 4.9 Ordre avec SPEC-53

SPEC-53 (tâches 262 à 266) modifie `src/draft/recommendations.py`, `src/draft/snapshot.py` et
`src/client/draft_view.py`. Les tâches 269 et 270 partent d'un `master` où SPEC-53 est livrée.

### 4.10 Tests

- `tests/test_pool_tree.py` : scorer factice (comme `tests/test_pool_swipe.py`) — ordre de blind, table par
  adversaire, égalité alphabétique, `leaf` vu / non vu / absent des données, replis et `skipped`, tout
  indisponible, comparaison sans casse, doublons du pool.
- `tests/test_strategy.py` : Arbre système, Méta absente, `STRATEGY_DEFAULT` = Arbre, `strategy_from_dict` ne
  produit jamais `tree=True`, « Méta » active retombe sur Arbre ; tests existants qui citent Méta mis à jour
  (`tests/test_client_draft.py:1827`, `tests/test_client_strategies.py:55`, `tests/test_draft_monitor_hover.py:281`,
  `tests/test_draft_monitor_recommendations.py:522` et `:561`).
- `tests/test_draft_monitor_recommendations.py` : sous Arbre, n° 1 = choix de l'arbre (vis-à-vis vu et non vu,
  construits pour différer du classement pondéré), repli si le choix est banni, `win_probability` calibrée, ligne
  `[ARBRE]`, poste inconnu, `pool_tree` qui lève → classement sans exception ; cache vidé à une nouvelle draft.
- `tests/test_draft_monitor_hover.py` : survol de début de draft sous Arbre = premier blind de l'arbre.
- `tests/test_draft_snapshot.py`, `tests/test_client_draft.py` : `tree` et `tree_value`, lignes des cartes 1 et
  suivantes, indisponibles.
- `tests/test_client_pool_tree.py` (nouveau) : `tree_view` (seuil de popularité, repli), cache, route
  `/pool/arbre` (lane du rôle, du poste désigné, dominante ; pool inconnu 404).
- `tests/test_client_pool_swipe.py` : `tree` dans `aside_view` et dans la vue du pool généré, plus de `counters`.
- `tests/test_pool_generator.py` : retrait des assertions sur `counters`.
- `tests/test_client_strategies.py` : Arbre en lecture seule, sans Dupliquer.

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 267 | `src/analysis/pool_tree.py` (`build_tree`, `leaf`), tests | 3 | — |
| 268 | Stratégie système Arbre, Méta retirée, `STRATEGY_DEFAULT`, tests existants mis à jour | 2 | — |
| 269 | Live Coach : `pool_tree` en cache, ordre de l'arbre dans `_provide`, console, survol de début de draft, tests | 5 | 267, 268, SPEC-53 |
| 270 | Snapshot et cartes de draft (`tree`, `tree_value`, lignes), tests | 3 | 269 |
| 271 | Client : `pool_tree.py`, partiel, route `/pool/arbre`, Méta du poste (`counters` retiré), écran Stratégies, tests | 5 | 267, 268 |
| 272 | Clôture : exe vérifié, `PROJECT_STRUCTURE.md`, `CHANGELOG.md`, statut, README des specs, `TODO.md`, stratégie active de @pj35 sur Arbre | 2 | 270, 271 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests des tâches 267 à 271.
2. `git diff 8ae7833 -- src/analysis/game_eval.py src/analysis/pool_value.py` est vide et `MODEL_VERSION` ne change
   pas.
3. Sur la base du 7 nov., `build_tree` de TOP GÉNÉRÉ au top donne l'ordre de blind Ornn, Shen, Teemo, Garen,
   Malphite et Teemo contre Darius (§1.2), valeurs à 0,01 près.
4. Sous Arbre, vis-à-vis vu, le n° 1 est le premier disponible de sa table ; vis-à-vis non vu, le premier disponible
   de l'ordre de blind ; son ban fait passer le suivant (tests 269).
5. Sous toute stratégie, Arbre compris, `win_probability` d'une carte et `predicted_probability` viennent du modèle
   calibré.
6. `grep -rn "\"Méta\"" src/analysis/strategy.py` ne rend rien et `find_strategy(None, ())` rend Arbre.
7. `grep -rn "POOL_GEN_COUNTERS_MIN_POPULARITY\|generated\.counters" src` ne rend rien.
8. Une exception dans `pool_tree` ou `build_tree` n'interrompt pas la draft : le classement s'affiche (test 269).
9. Après une nouvelle draft, l'arbre est reconstruit (cache vidé, test 269).
10. `python scripts/check_exe_assets.py` vert sur un exe reconstruit, `pool_tree.html` présent.
11. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec et `docs/specs/README.md` à jour ; `user_prefs.json` de
    @pj35 porte `"active_strategy": "Arbre"`.

**Vérification de bout en bout** : dans le client lancé, écran Pool, TOP GÉNÉRÉ : l'arbre s'affiche sous les
champions (blind Ornn en tête, Teemo contre Darius). Méta du poste, Top : même arbre sous le pool du poste ;
« Générer » montre l'arbre du pool généré. En draft classée réelle (@pj35), sous Arbre : avant le vis-à-vis, la
carte 1 dit « Blind » ; une fois le vis-à-vis posé, « Counter de X » et le n° 1 suit la table. Recette par @pj35
(pas de sonde de fenêtre réelle sans son accord).

## 7. Hors périmètre

- ❌ Départage par le reste de la draft, branches par stade : écartés par @pj35 (§3). À rouvrir avec des parties
  jouées sous Arbre, en comparant `predictions.strategy`.
- ❌ Maîtrise dans l'arbre, forçage manuel d'une feuille : arbitrages §2.
- ❌ Bans dictés par l'arbre : `BanRecommender` inchangé.
- ❌ Moyenne des scrapes pour l'arbre : la draft joue la base actuelle.
- ❌ Retirer `WeightedEvaluator`, l'anticipation ou l'écran Stratégies : Arbre s'ajoute, il ne remplace rien.
- ❌ Modifier le modèle calibré, un K ou `predictions` : rien ici ne touche `game_eval.py`.
