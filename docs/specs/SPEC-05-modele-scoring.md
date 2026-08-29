# SPEC-05 — Modèle de score : confiance statistique et log-odds

**Items** : B6, B7 · **Priorité** : 5 · **Effort estimé** : ~2 jours
**Constats d'audit** : M3, M4, M5 (`docs/AUDIT_2026_08.md` §4)
**Prérequis** : SPEC-03 recommandée (sinon double refonte du scoring)
**Statut** : ⚠️ **B7 est à valider avec @pj35 avant implémentation** — le cadre mathématique est posé ici, les coefficients de départ méritent une discussion.

---

## 1. Contexte

Trois défauts de modélisation, distincts et cumulatifs.

### 1.1 La confiance statistique est absente (B6)

Le filtre de qualité est binaire (`src/analysis/scoring.py:filter_valid_matchups`) :

```python
m.pickrate >= analysis_config.MIN_PICKRATE      # 0.5 %
and m.games >= analysis_config.MIN_MATCHUP_GAMES  # 200
```

Au-delà du seuil, **un matchup à 210 parties pèse exactement autant qu'un matchup à 26 354** (extrêmes réels de la base ; moyenne : 1 326). Sur un `delta2` typique de ±0,1 à ±3 points, le bruit d'échantillonnage à 200 parties est du même ordre que le signal.

> **Précision de @pj35, à respecter** : la pondération par `pickrate` n'est *pas* une mesure de qualité de donnée — elle sert à **prédire le pick adverse** (un adversaire fréquent compte davantage dans l'espérance). Ce choix est juste et doit être **conservé**. Le manque est ailleurs : deux notions différentes sont aujourd'hui portées par un seul poids.

| Notion | Question | Grandeur | État |
|---|---|---|---|
| Probabilité de rencontre | « quelle chance d'affronter ce champion ? » | `pickrate` | ✅ modélisée |
| Confiance dans l'estimation | « ce `delta2` est-il mesuré ou bruité ? » | `games` | ❌ seuil binaire puis ignorée |

### 1.2 La conversion vers un pourcentage est un trompe-l'œil (B7a)

`ChampionScorer.delta2_to_win_advantage()` (`src/analysis/scoring.py:104-137`) : 34 lignes de docstring pour

```python
advantage = delta2 * 1.0
```

— l'identité, avec un paramètre `champion_name` inutilisé « conservé pour compatibilité ». Le résultat est ensuite affiché comme un pourcentage de winrate (`+2,34 %`). La justification d'origine s'appuyait sur « l'analyse de 36 000+ matchups » : cette base n'existe plus (26 398 aujourd'hui, structure différente), et la conversion n'a jamais été revalidée.

### 1.3 La winrate d'équipe n'a pas de fondement (B7b)

`ChampionScorer.calculate_team_winrate()` : moyenne géométrique des winrates individuels, bornée à [25 %, 75 %], commentée « more mathematically sound than arithmetic averaging ». Multiplier des winrates ne modélise rien ici : ce ne sont ni des probabilités indépendantes, ni des événements conjoints — les cinq joueurs gagnent ou perdent **la même** partie. Les bornes [25, 75] sont là pour masquer les valeurs absurdes que le calcul produit.

---

## 2. Objectif

Un modèle unique, interprétable et **vérifiable** :

1. Chaque estimation est pondérée par la confiance qu'on peut lui accorder.
2. Les avantages se composent selon une règle qui a un sens.
3. Les scores affichés portent une unité réelle.
4. Les prédictions peuvent être **confrontées aux résultats réels** — donc calibrées.

---

## 3. Le cadre mathématique (B7)

### 3.1 L'idée : raisonner en log-odds

Les probabilités ne s'additionnent pas (60 % + 60 % n'a aucun sens) et se multiplient mal. Leur **logit** — le logarithme de la cote — s'additionne naturellement :

```
logit(p)   = ln( p / (1 − p) )       logit(0,50) = 0
sigmoid(x) = 1 / (1 + e^(−x))        l'inverse
```

On part d'un match équilibré (`logit = 0`), chaque élément du draft ajoute ou retranche sa contribution, et la sigmoïde reconvertit :

```
avantage = Σ (contributions alliées) − Σ (contributions adverses)
P(victoire) = sigmoid(avantage)
```

Deux propriétés gratuites, exactement ce qui manque aujourd'hui :

- **le résultat reste toujours dans ]0 ; 1[** → plus de clamp arbitraire à [25, 75] ;
- **les avantages saturent** → accumuler du bon fait progresser de moins en moins vite, ce qui est le comportement réel d'un draft (le premier contre-pick vaut plus que le cinquième).

### 3.2 La conversion « point de winrate → log-odds »

Autour de 50 %, la relation est quasi linéaire :

```
d(logit)/dp = 1 / (p·(1−p)) = 4        à p = 0,5
⇒ +1 point de winrate (0,01) ≈ +0,04 en log-odds
```

Cette constante (`LOGIT_PER_WINRATE_POINT = 0.04`) remplace le `delta2 * 1.0` de `delta2_to_win_advantage` : elle donne un sens à l'unité au lieu d'afficher un score brut avec un signe `%`.

### 3.3 La formule complète

```
score = Σ_alliés   [ LOGIT_PER_WR_PT × (winrate_base_i − 50) ]     # force intrinsèque
      + Σ_matchups [ LOGIT_PER_WR_PT × k_m × delta2_ij ]           # nos matchups
      + Σ_synergies[ LOGIT_PER_WR_PT × k_s × delta2_ik ]           # nos synergies
      − (les mêmes termes, côté adverse)

P(victoire) = sigmoid(score)
```

**Pourquoi il n'y a pas de double comptage** : la winrate de base d'un champion contient déjà l'effet *moyen* de ses adversaires ; `delta1`/`delta2` de LoLalytics sont précisément des **écarts à cette moyenne**. Les additionner est le seul découpage légitime — c'est aussi ce qui justifie de ne pas re-normaliser les deltas.

**`k_m` et `k_s`** (0,3 à 1,0) corrigent le double comptage résiduel entre matchups qui se recouvrent partiellement. Ils remplacent `synergy_config.SYNERGY_BONUS_MULTIPLIER` (0.3) avec la même fonction, mais sur une échelle interprétable. Valeurs de départ proposées : `k_m = 1.0`, `k_s = 0.5`. **À discuter avec @pj35 — c'est le point ouvert de cette spec.**

### 3.4 Ce qui rend ce modèle différent : il est calibrable

C'est l'argument principal en faveur de ce chantier. Le draft coach connaît, via le LCU, **l'issue réelle de chaque partie**. En journalisant `(probabilité prédite, résultat)`, on peut :

- vérifier la **calibration** : parmi les drafts annoncés à 60 %, en gagne-t-on ~60 % ?
- ajuster `k_m` et `k_s` par régression logistique sur les parties accumulées.

Une centaine de parties suffit à corriger grossièrement, quelques centaines à affiner. **Aucun paramètre n'a besoin d'être deviné définitivement** — c'est le seul endroit du projet où l'on peut mesurer si le coach a *raison*.

---

## 4. Travail à faire

### B6 — Composer fréquence et confiance

Dans `src/analysis/scoring.py`, remplacer la pondération `pickrate` seule par le produit :

```python
poids = pickrate × confidence(games)

confidence(games) = games / (games + CONFIDENCE_K)
```

Nouvelle constante dans `analysis_config` :

```python
# Lissage de confiance : un matchup à CONFIDENCE_K parties reçoit la moitié
# du poids d'un matchup infiniment observé. Les petits échantillons sont
# ramenés vers le neutre plutôt que comptés au même titre que les gros.
# Valeur initiale 500 : la médiane de la base est ~1 300 parties.
CONFIDENCE_K: int = 500
```

À appliquer dans `avg_delta1`, `avg_delta2`, `avg_winrate`, `calculate_synergy_bonus`, et dans le calcul de `coverage`/`peak_impact` de `Assistant.calculate_global_scores` (`src/assistant.py:440-460`).

**Conserver `MIN_MATCHUP_GAMES = 200` comme filtre d'entrée** : le lissage complète le seuil, il ne le remplace pas (en dessous de 200 parties, LoLalytics est trop bruité pour être exploitable même atténué).

Effet attendu : les classements bougent peu en moyenne, mais les matchups rares cessent de produire des recommandations extrêmes. **Vérifier avant/après sur un pool réel** et documenter dans le CHANGELOG les 3 à 5 changements de classement les plus marquants.

### B7 — Le modèle log-odds

Étapes, dans cet ordre :

1. **Primitives** — dans `src/analysis/scoring.py` ou un nouveau `src/analysis/probability.py` (préférable, ~40 lignes) :

```python
def logit(p: float) -> float:        # avec garde: p clampé à [1e-6, 1-1e-6]
def sigmoid(x: float) -> float:
def winrate_points_to_logit(points: float) -> float:  # points × 0.04
```

2. **Remplacer `delta2_to_win_advantage`** par `winrate_points_to_logit(delta2 * k_m)`. Supprimer le paramètre `champion_name` inutilisé. Les appelants qui affichent un pourcentage doivent désormais afficher soit une probabilité (`sigmoid`), soit un écart en points de winrate — jamais un log-odds brut, qui n'est pas lisible.

3. **Réécrire `calculate_team_winrate`** selon la formule §3.3. Supprimer le clamp [25, 75] et la moyenne géométrique. La signature actuelle prend `List[float]` de winrates : l'étendre pour recevoir aussi les contributions matchups/synergies, ou introduire une nouvelle fonction `estimate_win_probability(...)` et ne garder l'ancienne que le temps de migrer les appelants (`src/assistant.py:352`, affichages divers).

4. **Journaliser les prédictions** — à la fin d'un draft (`DraftMonitor._analyze_complete_draft`, l. 509), écrire dans une table `predictions` :

```sql
CREATE TABLE predictions (
    id INTEGER PRIMARY KEY,
    created_utc TEXT NOT NULL,
    ally_champions TEXT NOT NULL,    -- CSV d'IDs Riot
    enemy_champions TEXT NOT NULL,
    ally_lanes TEXT,                 -- rôles inférés (SPEC-04), CSV
    predicted_probability REAL NOT NULL,
    model_version TEXT NOT NULL,     -- pour ne pas mélanger deux calibrations
    outcome INTEGER                  -- NULL puis 1 (victoire) / 0 (défaite)
);
```

Le résultat se renseigne a posteriori via la fin de partie du LCU (`gameflow` en `EndOfGame`) — ou, si c'est trop fragile, par une commande manuelle. **La journalisation ne doit jamais bloquer ni ralentir le draft** : écriture best-effort en `try/except`, comme les notifications.

5. **Script de calibration** — `scripts/calibrate_model.py` : lit `predictions`, affiche la courbe de calibration par tranches de 10 %, le score de Brier, et propose des `k_m`/`k_s` ajustés. À n'écrire qu'une fois assez de données accumulées ; le **prévoir** dès maintenant conditionne le schéma de la table.

---

## 5. Critères d'acceptation

**B6**
- [ ] Un matchup à 200 parties et un à 20 000 parties, même `delta2` et même `pickrate`, produisent des contributions différentes (ratio ≈ 0,29 vs 0,98).
- [ ] `CONFIDENCE_K` est dans `config_constants.py`, documentée, et ne figure nulle part en dur.
- [ ] La pondération par `pickrate` est **conservée** partout où elle existait — le produit remplace le facteur, il ne le supprime pas.
- [ ] Comparatif avant/après sur un pool réel documenté dans le CHANGELOG.

**B7**
- [ ] `logit(sigmoid(x)) == x` à 1e-9 près pour x ∈ [−10, 10].
- [ ] `sigmoid` ne renvoie jamais 0 ni 1 exactement ; `logit(0)` et `logit(1)` ne lèvent pas.
- [ ] `estimate_win_probability` renvoie toujours une valeur dans ]0 ; 1[ **sans clamp**, y compris sur un draft extrême (5 contre-picks parfaits).
- [ ] Deux avantages de +3 points cumulés donnent **moins** de +6 points de probabilité (saturation vérifiée par un test).
- [ ] `delta2_to_win_advantage` n'est plus l'identité ; plus aucun paramètre inutilisé.
- [ ] Aucun log-odds brut n'est affiché à l'utilisateur.
- [ ] Une partie complète insère une ligne dans `predictions` ; un échec de journalisation ne perturbe pas le draft.
- [ ] `pytest tests/ -v` : 0 échec.

---

## 6. Tests exigés

| Fichier | Contenu |
|---|---|
| `tests/test_probability.py` (nouveau) | `logit`/`sigmoid` : inverses, bornes, valeurs extrêmes, monotonie ; conversion points → log-odds |
| `tests/test_scoring_confidence.py` (nouveau) | B6 : effet du lissage, `CONFIDENCE_K` respectée, `pickrate` toujours actif, seuil 200 conservé |
| `tests/test_win_probability.py` (nouveau) | Draft équilibré → 0,5 ; avantage → > 0,5 ; symétrie (inverser les équipes donne 1−p) ; saturation ; jamais 0 ni 1 |
| `tests/test_predictions_log.py` (nouveau) | Écriture de la ligne, `outcome` NULL puis mis à jour, échec d'écriture silencieux |
| `tests/test_scoring.py` (existant) | Mise à jour des valeurs attendues — **avec commentaire justifiant chaque changement**, jamais d'ajustement silencieux |
| `tests/regression/test_regression_no_clamp.py` (nouveau) | Un draft très déséquilibré ne produit pas exactement 75 % (l'ancien clamp ne doit pas réapparaître) |

---

## 7. Pièges connus

- **Ne pas mélanger les échelles.** Trois unités coexistent : points de winrate (`delta2`), log-odds (interne), probabilité (affichage). Nommer les variables en conséquence (`_pts`, `_logit`, `_prob`) — c'est la principale source de bug de ce type de refonte.
- **`SYNERGY_BONUS_MULTIPLIER = 0.3`** devient `k_s`. Ne pas laisser les deux coexister.
- **`_final_score` du draft monitor** (l. 636) mélange matchup et synergie avec un poids utilisateur (`synergy_weight`, saisi au lancement). Ce mélange reste **au-dessus** du modèle : `k_m`/`k_s` sont des constantes du modèle, `synergy_weight` est une préférence. Ne pas fusionner les deux — et vérifier que les trois cas épinglés dans la docstring de `_final_score` (0.0, 0.5, 1.0) restent exacts.
- **`calculate_team_winrate` a des appelants d'affichage** dans `assistant.py` et `lol_coach_legacy.py` : les recenser (`grep -rn "calculate_team_winrate\|team_winrate" src/`) avant de changer la signature.
- **Ne pas calibrer sur des données inventées.** Tant que la table `predictions` est vide, `k_m` et `k_s` restent des valeurs par défaut assumées. Ne pas « ajuster au feeling » pour que les scores « aient l'air mieux ».
- **`model_version`** doit changer à chaque modification des coefficients, sinon la calibration mélangera des prédictions issues de modèles différents.

---

## 8. Hors périmètre

- Modèle par joueur (skill, maîtrise du champion) : données non disponibles.
- Prise en compte du patch, du rang, de la durée de partie.
- Machine learning : la régression logistique de calibration se fait sur 2 paramètres, à la main ou avec `statistics` — aucune dépendance nouvelle.
- Refonte de l'affichage au-delà du remplacement des unités (SPEC-04 B5 s'en charge).
