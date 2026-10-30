# SPEC-46 — Stratégies de draft

**Statut** : ✅ Livrée le 2026-10-30, recette @pj35 à faire (`alembic upgrade head`, bascule en draft classée réelle).

**Origine** : @pj35, 2026-10-30 — « J'ai l'impression qu'on a trop compliqué le moteur d'évaluation des
drafts. Je pense qu'on devrait mettre une option visuelle pour switch entre plusieurs stratégies (et une
page spécifique pour définir les stratégies). »

**Effort** : ~3 jours, 7 tâches, 22 pts (§5).

---

## 1. Constat

### 1.1 Le moteur en vigueur

Le classement de pick empile cinq mécanismes :

| Mécanisme | Source | Réglage |
|---|---|---|
| Force intrinsèque du champion sur sa lane | `GameEvaluator.intrinsic_logit` (`src/analysis/game_eval.py:241`) | `K_INTRINSIC` 0,83 |
| Duels de lane | `GameEvaluator.matchup_logit` (`game_eval.py:141`) | `K_MATCHUP` 0,68, `SAME_LANE_WEIGHT` 2 |
| Matchups hors lane | même méthode | `K_MATCHUP`, `OTHER_LANE_WEIGHT` 1 |
| Synergies | `GameEvaluator.synergy_logit` (`game_eval.py:194`) | `K_SYNERGY` 1,49 |
| Maîtrise personnelle, sur mon pick | `MasteryTerm.logit` (`src/analysis/mastery.py:171`) | `MASTERY_LOGIT_PER_POINT` 0,0717, `MASTERY_K` 42,4 |

Le tout passe par une recherche minimax de 2 s (`DraftSearch.rank`, `src/draft/search.py:230`).

### 1.2 Ce que chaque terme prédit

Mesure du 2026-10-30 : 13 117 parties classées de `crawl.db` (patch en cours), validation croisée à 5 plis,
régression logistique sur les termes de `scripts/backtest_draft_model.py`.

| Termes | AUC hors pli | Brier hors pli |
|---|---|---|
| Synergies seules | 0,5036 | 0,24990 |
| Duel de lane seul | 0,5249 | 0,24938 |
| Matchups (lane + hors lane) | 0,5309 | 0,24916 |
| Force seule | 0,5328 | 0,24900 |
| Force + duel de lane | 0,5435 | 0,24840 |
| Force + duel + synergies | 0,5440 | 0,24835 |
| Force + matchups | 0,5461 | 0,24817 |
| Complet (3 termes) | 0,5463 | 0,24813 |

La synergie apporte 0,0002 d'AUC sur cet échantillon. Elle reste significative sur 96 987 parties (SPEC-43,
`K_SYNERGY` [1,10 ; 1,87]) et ne quitte donc pas le modèle calibré : seule la stratégie par défaut la coupe.

### 1.3 Ce que chaque terme change au classement

Mesure du 2026-10-30 : 180 positions rejouées depuis les parties classées de @pj35 (`game_records`, 204 parties
à dix postes connus, dont 196 top ; 45 positions par stade), pools de `pools_by_role`, budget de 2 s. L'ordre de
pick est simulé (B2, B3, B4, dernier pick), `predictions` ne le gardant pas.

- **Olaf sort n° 1 dans 95 % des cas** (171/180 ; les autres sont des positions au support ou Kennen, 1 fois).
- Amplitude moyenne d'un terme sur le pool, en logit : maîtrise 0,33, force 0,10, matchups 0,04 à 0,09,
  duel de lane 0,05 à 0,06 quand le vis-à-vis est connu, synergie 0,01 à 0,03. Olaf cumule la meilleure maîtrise (+5,4 pts de victoire,
  57 parties) et la meilleure force du pool GRIND.
- **La recherche ne change presque rien tant que la maîtrise est active** : même n° 1 que le calcul immédiat
  sur 179 positions sur 180. Sans maîtrise elle compte : Kennen passe en tête sur 22 des 45 positions B2, contre
  6 pour le calcul immédiat.
- Sans synergie ni recherche, le n° 1 est celui du moteur actuel sur **178 positions sur 180** (98,9 %), en
  0,02 ms au lieu de 2 s.
- Un classement au duel seul, vis-à-vis inconnu, tombe à égalité et rend le premier du pool : Ambessa 29/29 en
  B2. Toute stratégie a besoin d'un départage (§4.3).

### 1.4 Plusieurs chiffres, plusieurs modèles

- Le gros chiffre d'une carte est la victoire immédiate avec maîtrise, la sous-ligne la fin de draft de la
  recherche, la jauge la position ou la projection (`src/client/draft_view.py:400-446`).
- Le survol de début de draft classe au winrate de lane plus la maîtrise (`src/draft/automation.py:143-153`).
- Les bans passent par `BanRecommender`, un autre modèle (`src/draft/ban_advice.py:93`).

Le cumul se comprend mal à l'écran, et rien ne permet de voir ce qu'un terme change au classement.

## 2. Objectif et arbitrages

Rendre le classement de pick lisible et pilotable : une stratégie nommée règle le poids de chaque terme et le
mode de calcul, se bascule d'un clic en draft et se définit sur une page dédiée, sans toucher au modèle calibré.

| Sujet | Décision |
|---|---|
| Forme d'une stratégie | **Validé (@pj35, 2026-10-30)** : un poids de 0 à 3 par terme (force, duel de lane, matchups hors lane, synergie, maîtrise) et un choix immédiat ou recherche. 1 = valeur calibrée, 0 = terme coupé. |
| Portée | **Validé (@pj35, 2026-10-30)** : la stratégie règle l'ordre et le survol automatique. Les % de victoire, la jauge, l'analyse finale et `predictions` restent ceux du modèle calibré. Une carte classée 2ᵉ peut donc afficher un % supérieur à la 1ʳᵉ. |
| Stratégie par défaut | **Validé (@pj35, 2026-10-30)** : « Simple » (force, matchups, maîtrise à 1, synergie à 0, immédiat). Elle garde Olaf n° 1 à 95 % : ce n'est pas un défaut du moteur, c'est le constat du §1.3, et la bascule sert à sortir de ce classement. |
| Bascule | **Validé (@pj35, 2026-10-30)** : boutons segmentés dans la rangée des recommandations, qui reclassent aussitôt. Une stratégie active globale, mémorisée dans `user_prefs.json`, choisie aussi depuis la page. Pas de stratégie par poste : @pj35 joue top à 96 %. |
| Journal | **Validé (@pj35, 2026-10-30)** : colonne `strategy` dans `predictions`, pour comparer les stratégies à l'usage. |
| Stratégies de base | **Validé (@pj35, 2026-10-30)** : quatre stratégies système figées, dupliquées pour être modifiées, comme les pools système. |
| Nombre de stratégies | **Validé (@pj35, 2026-10-30)** : 6 au plus, système comprises, noms de 14 caractères au plus, pour que les boutons tiennent dans la rangée. |
| Départage | **Validé (@pj35, 2026-10-30)** : à score égal, la victoire calibrée départage (§1.3). |
| Survol de début de draft | **Validé (@pj35, 2026-10-30)** : il suit la stratégie, avec ses poids de force et de maîtrise. Il répond à la même question que le classement. |
| Bascule à mon tour | **Validé (@pj35, 2026-10-30)** : avec `auto_hover`, le nouveau n° 1 est survolé à mon tour, comme à un changement de draft ; jamais de verrouillage. |
| Bans, conseils d'échange, grimoire | **Validé (@pj35, 2026-10-30)** : inchangés, calibrés. Le tri « recommandations » du grimoire suit l'ordre du classement, sans code de plus. |

## 3. Approches considérées

**A. Poids appliqués à part, classement seul (retenue).** Un `WeightedEvaluator` applique les poids aux termes
de `GameEvaluator`, qui ne change pas. Les probabilités restent calculées par `GameEvaluator`. Aucun changement
du modèle, donc ni `MODEL_VERSION` à incrémenter, ni backtest, ni calibration à refaire. Limite : l'ordre et le %
peuvent diverger, d'où la décomposition sur les cartes (§4.5).

**B. Poids dans `GameEvaluator`.** Moins de code, et l'ordre colle toujours au %. Mais chaque stratégie devient
un modèle non calibré : il faudrait marquer ou écarter les prédictions par stratégie, et les % ne seraient plus
des probabilités. Écartée pour la portée validée au §2.

**C. Modes fixes, sans page.** Le moins de code, mais la page de définition demandée disparaît et le dosage de
la maîtrise avec. Écartée.

## 4. Détail

### 4.1 `src/analysis/strategy.py` (nouveau)

```python
@dataclass(frozen=True)
class Strategy:
    name: str
    force: float = 1.0
    duel: float = 1.0
    other: float = 1.0  # matchups hors lane
    synergy: float = 1.0
    mastery: float = 1.0
    search: bool = False  # False = calcul immédiat
    system: bool = False

    @property
    def is_calibrated(self) -> bool:
        """Tous les poids à 1 : le logit de la stratégie est celui de `GameEvaluator`."""

def parse_strategies(raw: Any) -> List[Strategy]:
    """Stratégies perso lues de `user_prefs.json` ; une entrée invalide est écartée sans lever."""

def all_strategies(custom: Sequence[Strategy]) -> List[Strategy]:
    """Les stratégies système, puis les perso."""

def find_strategy(name: Optional[str], custom: Sequence[Strategy]) -> Strategy:
    """La stratégie `name`, sinon `draft_config.STRATEGY_DEFAULT`."""

def strategy_of(monitor) -> Strategy:
    """`monitor.strategy` s'il en est une, sinon la stratégie par défaut (monitors simulés, comme `term_of`)."""

class WeightedEvaluator:
    """L'interface de `GameEvaluator` dont la recherche a besoin, avec les poids d'une stratégie."""

    def __init__(self, base: GameEvaluator, strategy: Strategy) -> None: ...
    def parts(self, champion: Placed, own_team, opposing_team) -> Dict[str, float]:
        """Log-odds pondérés par terme : `force`, `duel`, `other`, `synergy`. Ni I/O ni exception nouvelle."""
    def contribution(self, champion, own_team, opposing_team) -> float: ...
    def team_logit(self, allies, enemies) -> float: ...
    @staticmethod
    def probability(logit: float) -> float: ...
```

`parts` sépare duel et hors lane en comparant les lanes (`champion[1] and champion[1] == enemy[1]`), comme
`_lane_weight`. `matchup_logit` porte déjà `SAME_LANE_WEIGHT` et `K_MATCHUP` : le poids s'applique par-dessus.
`src/analysis/game_eval.py` n'est **pas** modifié : la règle du backtest (`docs/specs/README.md`) ne s'applique pas.

Constantes de `draft_config` (`src/config_constants.py`) :

```python
STRATEGY_DEFAULT: str = "Simple"
STRATEGY_WEIGHT_MAX: float = 3.0
STRATEGY_WEIGHT_STEP: float = 0.25
STRATEGY_MAX_COUNT: int = 6  # système comprises : boutons segmentés de la rangée de draft
STRATEGY_NAME_MAX: int = 14
```

Stratégies système, dans cet ordre, définies dans `strategy.py` :

| Nom | Force | Duel | Hors lane | Synergie | Maîtrise | Calcul | Mesure du §1.3 |
|---|---|---|---|---|---|---|---|
| Simple | 1 | 1 | 1 | 0 | 1 | immédiat | n° 1 du moteur actuel à 98,9 %, Olaf 171/180 |
| Counter | 0,5 | 2 | 1 | 0 | 0,25 | immédiat | 8 champions distincts, Olaf 138/180, n° 1 du moteur actuel à 78,3 % |
| Méta | 1 | 0 | 0 | 0 | 0 | immédiat | Olaf 171/180 : il a aussi la meilleure force du pool GRIND |
| Complet | 1 | 1 | 1 | 1 | 1 | recherche | le moteur d'avant SPEC-46, à l'identique |

### 4.2 Préférences (`src/user_prefs.py`)

Mêmes règles que `motion` : clés hors de `UserPrefs`, reportées par `save_user_prefs`, écrites par lecture brute.

```python
def load_strategies() -> Tuple[Optional[str], List[Strategy]]:
    """Nom de la stratégie active (None : aucune choisie) et stratégies perso."""

def save_active_strategy(name: str) -> bool: ...
def save_strategies(strategies: Sequence[Strategy]) -> bool: ...
```

Clés `active_strategy` et `strategies` de `user_prefs.json`. `save_user_prefs` les préserve comme `motion`
(`user_prefs.py:121-125`). Une stratégie perso ne stocke que ses poids et `search`.

### 4.3 Moteur

`src/draft/search.py` — `DraftSearch.rank` gagne `max_depth: Optional[int] = None`, qui plafonne `max_depth`
(`search.py:271`). L'immédiat est `max_depth=1` : aucun chemin de code de plus. `SearchResult` gagne
`score: Optional[float] = None`.

`src/draft_monitor.py` — `set_strategy(strategy)` pose `self.strategy`, `self.weighted`
(`WeightedEvaluator`, ou `self.evaluator` si `strategy.is_calibrated`) et `self.search.evaluator = self.weighted`.
Appelée à la construction avec la stratégie de `load_strategies`.

`src/draft/lifecycle.py` — `_reload_strategy()` à côté de `_reload_mastery()` (`lifecycle.py:165`), best-effort :
la stratégie active et ses poids sont relus à chaque nouvelle draft.

`src/draft/commands.py` — commande `strategy <nom>` dans `apply_pending`, sur le modèle de
`handle_pool_command` : relit les préférences, appelle `set_strategy`, renvoie `True` pour forcer le recalcul.
Stratégie inconnue : `[ALERTE]`, stratégie courante conservée. Aucune exception ne remonte à la boucle.

`src/draft/recommendations.py`, `_provide` :

```python
strategy = strategy_of(self.m)
results = self.m.search.rank(
    ...,
    personal=lambda name: strategy.mastery * term_of(self.m).logit(name),
    max_depth=None if strategy.search else 1,
)
self._calibrate(results, allies, enemies, turns)
```

`_calibrate` copie `win_probability` dans `score`, puis y écrit la victoire calibrée de mon pick et de sa suite :
`pv[i]` joue le tour `turns[i + 1]`, le camp vient de `turn.is_ally`, et `with_term` ajoute ma maîtrise à poids 1.
Les résultats sont retriés par `(-score, -win_probability)` : c'est le départage du §1.3. Si
`strategy.is_calibrated`, `win_probability` n'est pas recalculée et l'ordre reste celui de la recherche.

`Analysis` gagne `parts: Dict[str, Dict[str, float]]` (champion → terme → points de victoire, `to_win_points` de
`WeightedEvaluator.parts` à la racine, termes de poids nul omis), et `_key` inclut le nom de la stratégie.

`_print_results` n'imprime `[SEARCH] Profondeur atteinte` que si `strategy.search`. Le titre `[PICKS]` porte le
nom de la stratégie. Le reste de la sortie console ne change pas.

`src/draft/automation.py`, `get_best_champion_from_pool` : seule la ligne de score change. Le score devient
`strategy.force * evaluator.intrinsic_logit((nom, lane)) + strategy.mastery * term.logit(nom)`, à égalité le
winrate rétréci. La règle SPEC-09 des champions sans données reste.

### 4.4 Journal (`predictions.strategy`)

Migration Alembic (`down_revision = "e5b7d2a14c93"`) : `ALTER TABLE predictions ADD COLUMN strategy TEXT`, `NULL`
pour les lignes existantes. `insert_prediction` (`src/repositories/predictions.py:17`, délégué `src/db.py:400`)
gagne `strategy: Optional[str] = None`, en SQL paramétré. `FinalDraftAnalyzer` (`src/draft/final_analysis.py:328`)
passe `strategy_of(self.m).name`. `predicted_probability` et `model_version` ne changent pas.

### 4.5 Snapshot et écran de draft

`src/draft/snapshot.py` : `SnapshotRecommendation.parts: Dict[str, float]`, `DraftSnapshot.strategy: Optional[str]`
et `strategies: List[str]`.

`src/client/draft_view.py` :

- La ligne d'une carte commence par la décomposition, `Force +0,4 · duel +4,2 · hors lane +0,8`, qui explique
  l'ordre quand il diverge du %. Elle est suivie de `_personal`, dont les points sont ceux du poids de la stratégie ;
  si ce poids est nul, `_personal` n'affiche rien pour un champion joué.
- « Fin de draft attendue » et « suite » ne s'affichent que pour une stratégie à recherche
  (`rec["variation"]` non vide ou `depth > 1`).
- La vue reçoit `strategies` : `[{"name", "active"}]`.

`src/client/templates/partials/draft_row_pick.html` : dans `.d-row-actions`, un groupe `.seg` de boutons
`data-strategy="<nom>"`, `aria-pressed` sur l'actif ; `v.strategies` entre dans `data-sig` de `row-head`.
`src/client/static/draft.js` : clic délégué comme `[data-swap]` (`draft.js:443`), `post("/strategies/active",
{name})`. `src/client/static/style.css` : état actif de `.seg` hors du réglage Motion.

### 4.6 Écran Stratégies

`src/client/strategies.py` (nouveau), sur le modèle de `src/client/pools.py` :

```python
def strategies_view(selected: Optional[str], notice: Optional[str] = None) -> dict: ...
def edit(action: str, name: str, form: Dict[str, str]) -> Tuple[str, Optional[str]]:
    """`actif`, `dupliquer`, `modifier`, `supprimer`. Lève `Refusal` en cas de refus."""
```

`src/client/app.py` :

- `NavItem("strategies", "Stratégies", "ᚾ", 125, "/strategies")` après Pool (`app.py:108`).
- `GET /strategies`, `POST /strategies/active?name=`, `POST /strategies/{action}?name=`, corps htmx lu par
  `parse_qs` comme `pool_action` (`app.py:493`).
- Après `actif`, ou `modifier` et `supprimer` de la stratégie active : `commands(f"strategy {nom}")`.

Gabarits `strategies.html` et `partials/strategies_body.html` : liste à droite, détail à gauche, comme l'écran
Pool. Détail d'une stratégie perso : un `<input type="range">` par terme, de 0 à `STRATEGY_WEIGHT_MAX` par pas de
`STRATEGY_WEIGHT_STEP`, avec sa valeur, une case « Recherche minimax », Enregistrer, Supprimer, Dupliquer. Stratégie système : valeurs en lecture
seule et Dupliquer. Texte d'aide : « 1 = valeur calibrée, 0 = terme coupé. Les % de victoire ne changent pas. »

Validation serveur, seule frontière de confiance de la fonctionnalité (`Refusal`, affiché dans le corps en 200) :
nom vide, trop long ou déjà pris sans tenir compte de la casse ; plus de `STRATEGY_MAX_COUNT` stratégies ; poids
non fini, hors de `[0, STRATEGY_WEIGHT_MAX]` ou tous nuls ; modification ou suppression d'une stratégie système.
Supprimer la stratégie active rebascule sur `STRATEGY_DEFAULT`.

### 4.7 Tests

- `tests/test_strategy.py` : `parts` somme à `contribution` ; antisymétrie de `team_logit` ; poids à 0 ;
  `parse_strategies` écarte une entrée invalide ; `find_strategy` retombe sur le défaut.
- Identité de « Complet » : mêmes champions, `win_probability`, variantes et profondeur qu'un `DraftSearch` direct
  sur `GameEvaluator`, sur une position à deux tours restants, où le budget ne coupe pas la recherche.
- `tests/test_draft_monitor_recommendations.py` : `max_depth=1` en immédiat ; `win_probability` calibrée quels que
  soient les poids ; départage à score égal ; commande `strategy` qui force le recalcul sans exception.
- `tests/test_user_prefs.py` : `save_user_prefs` préserve les deux clés.
- Migration et `insert_prediction` : ligne écrite avec sa stratégie, `predicted_probability` identique sous
  Simple et Counter pour une même composition.
- `tests/test_client_strategies.py` : routes, jeton, tous les refus du §4.6, `commands` appelé, sélecteur dans le
  fragment de draft (`data-sig` qui change avec la stratégie).

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 223 | `src/analysis/strategy.py`, constantes, stratégies système, tests | 3 | — |
| 224 | Préférences : `load_strategies`, sauvegardes, clés préservées, tests | 2 | 223 |
| 225 | Moteur : `max_depth`, `set_strategy`, rechargement, commande `strategy`, `_calibrate`, départage, `parts`, survol de début de draft, test d'identité de Complet | 5 | 223, 224 |
| 226 | Migration `predictions.strategy`, `insert_prediction`, `FinalDraftAnalyzer`, tests | 2 | 223 |
| 227 | Snapshot, cartes, sélecteur de la rangée, `POST /strategies/active`, `draft.js`, CSS | 3 | 225 |
| 228 | Écran Stratégies : `strategies.py`, routes, gabarits, navigation, validation, tests | 5 | 224, 227 |
| 229 | Clôture : exe vérifié, `PROJECT_STRUCTURE.md`, README, `CHANGELOG.md`, statuts | 2 | 226, 228 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests du §4.7.
2. `git diff master -- src/analysis/game_eval.py` est vide et `MODEL_VERSION` vaut toujours `spec43-v1`.
3. Sous Simple, `rank` s'exécute à profondeur 1 sans recherche : `depth == 1` et aucun nœud au-delà de la racine.
4. Sous Complet, le classement est identique à celui d'un `DraftSearch` direct sur `GameEvaluator` (test d'identité).
5. Sous toute stratégie, `win_probability` d'une carte, `projected_probability` et `predicted_probability`
   sont ceux du modèle calibré (test sur Counter).
6. À score égal, le meilleur champion à la victoire calibrée passe devant : une stratégie au seul duel, vis-à-vis
   inconnu, ne rend plus le premier du pool.
7. `auto_hover` et bascule à mon tour : le nouveau n° 1 est survolé, jamais verrouillé. Hors de mon tour, rien
   n'est survolé. Vérifié par un test à faux LCU.
8. La commande `strategy <nom>` sur un nom inconnu laisse la stratégie courante et n'interrompt pas la boucle.
9. `SELECT strategy FROM predictions ORDER BY id DESC LIMIT 1` rend le nom de la stratégie active après une
   analyse finale ; `python -m alembic upgrade head` puis `downgrade -1` passent sur une copie de la base.
10. Chaque refus du §4.6 s'affiche dans le corps de l'écran, sans écriture dans `user_prefs.json`, et les
    stratégies système ne sont ni modifiables ni supprimables.
11. Poids maximal, pas, nombre de stratégies et longueur des noms viennent de `draft_config`, y compris dans le
    gabarit de l'écran Stratégies.
12. `python scripts/check_exe_assets.py` vert sur un exe reconstruit.
13. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec et `docs/specs/README.md` à jour.

**Vérification de bout en bout** : en draft classée réelle (@pj35), basculer de Simple à Counter puis à Complet
pendant la phase de picks. Le classement et la ligne de décomposition changent aussitôt, les % de la jauge ne
bougent pas sous Simple et Counter, la suite attendue n'apparaît que sous Complet, et la stratégie active revient
au lancement suivant. Après la partie : `SELECT strategy, predicted_probability FROM predictions ORDER BY id DESC
LIMIT 1`.

## 7. Hors périmètre

- ❌ Modifier le modèle calibré, retirer la synergie ou recalibrer un K : rien ici ne touche `game_eval.py`.
- ❌ Plafonner ou réétudier la maîtrise : SPEC-41 reste en vigueur, la stratégie permet seulement de la doser.
- ❌ Bans et conseils d'échange par stratégie : ils relèvent d'autres calculs, calibrés ou précalculés.
- ❌ Écran de comparaison des stratégies : la colonne `strategy` permet de le faire en SQL ; à rouvrir avec assez
  de parties par stratégie.
- ❌ Stratégie par poste : @pj35 joue top à 96 %.
- ❌ Aperçu du classement sur la page Stratégies : la bascule en draft le montre.
- ❌ Supprimer les chemins hérités hors Live Coach (`DraftScorer`, `lane_restante`, `one_ply_lookahead`) : autre
  sujet, leurs appelants sont le Team Builder et les tier lists.
