# SPEC-48 — La réponse du vis-à-vis remplace le minimax

**Statut** : ✅ Livrée le 2026-11-01, recette @pj35 à faire (draft classée réelle sous WIN LANE, §6).

**Origine** : @pj35, 2026-11-01 — « Est-ce que tu crois qu'on pourrait déclarer une stratégie optimale qui
s'appuierait sur nos matrices de matchups et de synergies ? », puis, après la comparaison, feu vert pour retirer le
minimax.

**Effort** : ~1,5 jour, 5 tâches, 15 pts (§5).

---

## 1. Constat

### 1.1 Le moteur en vigueur

`DraftSearch.rank` (`src/draft/search.py:232`) est le seul classement du Live Coach. À `max_depth=1`, c'est le calcul
immédiat. Sans plafond, c'est un minimax alpha-bêta à approfondissement itératif, budget 2 s
(`src/draft/search.py:156`, `src/config_constants.py:398`). Il suppose que les neuf autres joueurs jouent le meilleur
coup du modèle, alliés compris.

Une stratégie choisit le mode par `Strategy.search` (`src/analysis/strategy.py:35`). Complet et la stratégie perso
**WIN LANE**, active chez @pj35, sont à recherche.

### 1.2 Mesure sur les poids calibrés

Mesure du 2026-11-01 : 219 parties de @pj35, 876 positions (211 et 844 pour Top playable), ordre de pick simulé (B2,
B3, B4, B5), comme SPEC-46 §1.3. Mêmes termes pour toutes les politiques, seule l'hypothèse sur l'adversaire change.
Valeur en points de victoire, maîtrise comptée : d'abord contre le reste réel de la draft, figé, puis avec le
vis-à-vis non vu remplacé par sa meilleure réponse parmi les top-8. IC 90 % par bootstrap de parties.

| Pool | Minimax − immédiat, reste réel | Minimax − immédiat, contre-pick |
|---|---:|---:|
| ULTRA GRIND (3) | −0,005 [−0,010 ; −0,001] | −0,006 [−0,011 ; −0,001] |
| Top playable (13) | −0,032 [−0,052 ; −0,014] | −0,017 [−0,034 ; −0,001] |
| 20 plus joués de la lane | −0,087 [−0,118 ; −0,059] | −0,056 [−0,083 ; −0,029] |

Le minimax ne bat l'immédiat sur aucun pool avec maîtrise, même si le vis-à-vis contre-pick à chaque fois. Remplacer
le « min » par une espérance sur la popularité n'apporte rien non plus : même valeur que l'immédiat, à ±0,01 pt, car
`delta2` a une moyenne quasi nulle sur la méta.

Le taux de contre-pick net en top vaut 3,5 % (46 champions à 20 000 lignes ou plus). C'est un plancher : `P(e|c)`
mélange les fois où le champion contre et celles où il se fait contrer.

Limites : tout est jugé dans le modèle calibré, pas sur des résultats de parties, et le vis-à-vis réel a répondu au
champion réellement joué.

### 1.3 Mesure sur WIN LANE

Poids force 1, duel 3, hors lane 0,25, synergie 0, maîtrise 0. Mêmes positions, tirage compris (`draw_correction`).
Le pool TRIO TOP est celui désigné en top depuis le 2026-11-01.

| Pool | n° 1 changés sans recherche | Idem, vis-à-vis non vu | Duel réel | Pire duel top-8 |
|---|---:|---:|---:|---:|
| TRIO TOP (3) | 24,4 % | 60 % | +0,009 [−0,017 ; +0,034] | +0,086 [+0,069 ; +0,104] |
| Top playable (13) | 34,9 % | 90 % | +0,016 [−0,010 ; +0,042] | +0,271 [+0,241 ; +0,302] |

Les deux dernières colonnes valent recherche − immédiat, en points de winrate. La recherche protège du pire duel, mais
ne change rien au duel réellement joué. Sur la victoire calibrée, le signe dépend du pool (+1,17 sur TRIO TOP, où elle
rabat sur Olaf et sa maîtrise, −0,35 sur Top playable) : pas de verdict.

Le retrait pur changerait donc le classement actif de @pj35. Ce que WIN LANE tire de la recherche tient à la réponse
du vis-à-vis, pas à l'arbre :

| Pool | Même n° 1 que le minimax, réponse à un pli | Dont vis-à-vis non vu | Immédiat, vis-à-vis non vu |
|---|---:|---:|---:|
| TRIO TOP | 799/880 (90,8 %) | 275/333 (82,6 %) | 135/333 (40,5 %) |
| Top playable | 760/848 (89,6 %) | 258/322 (80,1 %) | 36/322 (11,2 %) |

Coût de la réponse à un pli : 0,03 à 0,07 ms en médiane par position, 5 ms au pire, contre 2 s de budget.

### 1.4 Ce que la recherche impose au reste du code

- `SearchResult.depth` et `principal_variation`, repris par `src/draft/snapshot.py:80`, `:281` et `:283`.
- « Fin de draft attendue » et « suite » : `src/client/draft_view.py:426-445`, `src/client/draft_grimoire.py:72-84`.
- « profondeur atteinte » : `src/client/draft_view.py:577`, `src/draft/recommendations.py:144`.
- `PickTurn.lane` ne sert qu'à `_moves` (`src/draft/search.py:144`), renseigné par `src/draft/state_parser.py:164`.
- `scripts/bench_search.py` et `scripts/bench_swap_advice.py` mesurent la recherche. Le second importe le premier. Le
  conseil d'échange en production passe par `role_swaps` et `GameEvaluator`, pas par la recherche.

## 2. Objectif et arbitrages

Remplacer l'arbre par une anticipation à un pli, la réponse du vis-à-vis non vu, sans toucher au modèle calibré.

| Sujet | Décision |
|---|---|
| Moteur | **Validé (@pj35, 2026-11-01)** : la réponse du vis-à-vis remplace le minimax. |
| Cartes | **Validé (@pj35, 2026-11-01)** : « Réponse attendue : X » remplace « Fin de draft attendue » et « suite ». |
| Candidats de la réponse | Les `SEARCH_TOP_N` plus joués de la lane, comme la recherche, disponibles, hors bans (mesure du §1.3). |
| Condition d'anticipation | Stratégie à `search`, poste connu, vis-à-vis non vu, au moins un tour ennemi après le mien. Sinon, calcul immédiat. |
| Alliés et autres postes ennemis | Hors du calcul : leurs slots comptent pour 0, comme à profondeur 1. |
| Probabilités | `GameEvaluator` ne change pas. `predictions` non plus. La jauge projetée lit la victoire calibrée de mon pick et de la réponse. |
| Clé `search` | Conservée dans `Strategy` et `user_prefs.json` : pas de migration des stratégies perso, WIN LANE garde son mode. |
| Complet | **Validé (@pj35, 2026-11-01)** : la stratégie système garde `search=True`, donc l'anticipation. |
| Libellés | **Validé (@pj35, 2026-11-01)** : case « Anticiper le vis-à-vis », mode « Anticipation » à la place de « Recherche ». |

Le terme relève d'ADR-004 : raison au §1.1, pas de dégradation puisque les probabilités restent calibrées, effet
chiffré au §1.3.

## 3. Approches considérées

**A. Réponse du vis-à-vis (retenue).** Une boucle sur le pool et une sur les top-8 remplacent l'arbre. Garde 80 % des
n° 1 de la recherche quand le vis-à-vis n'est pas vu. Limite : le classement de WIN LANE change sur 9 à 10 % des
positions, et la suite complète disparaît.

**B. Tout retirer.** Le moins de code. Écartée : WIN LANE perdrait sa protection sur le pire duel, et un quart à un tiers
de ses n° 1 changeraient, alors que c'est la stratégie active.

**C. Garder le minimax pour les stratégies perso.** Aucun changement pour WIN LANE. Écartée : l'arbre, son budget de 2 s
et ses affichages restent pour un gain nul sur le duel réel (§1.3).

**D. Espérance sur la popularité.** Écartée : elle ne se distingue pas du calcul immédiat (§1.2).

## 4. Détail

### 4.1 `src/draft/search.py`

Fichier et noms conservés, pour ne pas toucher à `self.m.search`, `state.py`, `state_parser.py` ni `snapshot.py`.

Supprimés : `_SearchTimeout`, `_minimax`, `_moves`, `_rank_at_depth`, `nodes`, `PickTurn.lane`,
`SearchResult.depth`, `SearchResult.principal_variation`, les paramètres `budget_seconds` et `max_depth`. Le docstring
de module décrit le calcul à un pli.

```python
@dataclass
class SearchResult:
    champion: str
    lane: Optional[str]
    win_probability: float
    reply: Optional[Placed] = None  # SPEC-48 : réponse attendue du vis-à-vis, None sans anticipation
    personal_points: float = 0.0
    score: Optional[float] = None


class DraftSearch:
    def rank(
        self,
        allies: Sequence[Placed],
        enemies: Sequence[Placed],
        pool: Sequence[str],
        remaining_turns: Sequence[PickTurn],
        banned: Sequence[str] = (),
        player_lane: Optional[str] = None,
        personal: Callable[[str], float] = _no_term,
        anticipate: bool = False,
    ) -> List[SearchResult]:
        """Classe `pool` pour mon pick, avec la réponse du vis-à-vis si `anticipate`."""
```

Pour chaque champion disponible du pool, `(nom, lane)` ajoute au logit de base `contribution` et `personal(nom)`.
`lane` vaut `player_lane`, sinon la première lane libre alliée (`_free_lanes`), comme aujourd'hui.

Si l'anticipation s'applique (§2), avec `taken` les champions posés, les bans et le candidat :

```python
replies = self.candidates.best(lane, taken)
reply = min(replies, key=lambda name: -evaluator.contribution((name, lane), enemies, allies + [me]))
```

`value` reçoit `-contribution` de `reply`, et `SearchResult.reply` vaut `(reply, lane)`. Sans candidat, pas de
réponse. Un vis-à-vis est vu si un ennemi posé porte `lane` ; un ennemi de lane `None` ne compte pas comme vu. Le tri
reste par `win_probability` décroissante. `rank` rend `[]` sans `remaining_turns`, comme aujourd'hui.

### 4.2 `src/draft/recommendations.py`

- `_provide` : `anticipate=strategy.search` remplace `max_depth=None if strategy.search else 1`.
- `_calibrated` : l'ajout de `result.reply` à `enemy_side`, s'il existe, remplace la boucle sur `principal_variation`,
  et le paramètre `turns` disparaît.
- `_format_variation` devient `_format_reply` : ` → réponse attendue : Darius (top)`.
- `_print_results` : la ligne `[SEARCH] Profondeur atteinte` disparaît.

### 4.3 `src/draft/snapshot.py`, écran de draft

- `SnapshotRecommendation` : `reply: Optional[Dict[str, Optional[str]]] = None` (`{"champion", "lane"}`) remplace
  `variation`, et `depth` disparaît. `DraftSnapshot.depth` disparaît.
- `src/client/draft_view.py`, `recommendations` : avec `rec["reply"]`, la ligne vaut
  `Réponse attendue : Darius (Top), 51,20 %`, la valeur venant de `rec["win_probability"]`. Sans réponse, elle reste
  vide. `searched` disparaît, ainsi que la mention de profondeur (`:577`) et la clé `"depth"` (`:604`).
- `src/client/draft_grimoire.py` : `· réponse attendue : Darius (Top)` remplace `fin de draft attendue` et
  `suite attendue`.

### 4.4 Écran Stratégies

`src/client/strategies.py:37` : `"Anticipation" if strategy.search else "Immédiat"`.
`src/client/templates/partials/strategies_body.html:31` et `:40` : libellés du §2. Le nom de champ `search` ne change
pas.

### 4.5 Réglages et scripts

- `src/config_constants.py` : `SEARCH_BUDGET_SECONDS` et `SEARCH_MAX_DEPTH` disparaissent. `SEARCH_TOP_N` reste, avec
  un commentaire à jour : la mesure de profondeur n'a plus lieu d'être, 8 est la valeur du §1.3.
- `src/draft/state_parser.py:164` : `lane=` disparaît, et le commentaire au-dessus de la boucle ne parle plus de minimax.
- `src/analysis/strategy.py:35` : commentaire `# False = calcul immédiat, True = réponse du vis-à-vis`.
- `scripts/bench_search.py` et `scripts/bench_swap_advice.py` sont supprimés.

### 4.6 Tests

- `tests/test_draft_search.py` : réécrit autour de `rank`. Sans `anticipate`, la valeur égale `contribution` plus le
  terme personnel. Avec, le pire des top-8 est retenu et sa valeur soustraite. Pas de réponse si le vis-à-vis est vu,
  sans tour ennemi restant, sans lane, ou sans candidat. Bans et champions pris sont exclus de la réponse, le candidat
  aussi. `personal` ne porte que sur mon pick.
- `tests/test_strategy.py` et `tests/test_draft_monitor_recommendations.py` : le test d'identité de Complet (SPEC-46
  §4.7) est remplacé par un test d'anticipation sur `WeightedEvaluator`. La victoire de `_calibrated` compte la réponse
  et reste calibrée sous tous les poids. Le départage à score égal reste.
- `tests/test_draft_snapshot.py`, `tests/test_client_draft.py`, tests du grimoire : `reply` à la place de `variation`
  et `depth`, ligne « Réponse attendue », rien sans réponse.
- `tests/test_client_strategies.py` : libellés du §2.

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 236 | `DraftSearch.rank` à un pli, suppression de l'arbre, `tests/test_draft_search.py` | 5 | — |
| 237 | `recommendations.py` : `anticipate`, `_calibrated`, console, tests | 3 | 236 |
| 238 | Snapshot, cartes, grimoire, tests | 3 | 237 |
| 239 | Écran Stratégies, constantes, `PickTurn.lane`, scripts supprimés | 2 | 236 |
| 240 | Clôture : exe vérifié, `PROJECT_STRUCTURE.md`, README, `TODO.md` (reports SPEC-17 retirés), `CHANGELOG.md`, statuts | 2 | 238, 239 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests du §4.6.
2. `git diff 61caea1 -- src/analysis/game_eval.py` est vide et `MODEL_VERSION` ne change pas.
3. `grep -rnE "_minimax|principal_variation|SEARCH_BUDGET_SECONDS|SEARCH_MAX_DEPTH|max_depth|bench_search" src scripts tests`
   ne rend rien.
4. Sous Simple, aucune réponse n'est calculée : `reply` vaut `None` sur tous les résultats.
5. Sous WIN LANE, vis-à-vis non vu et tour ennemi restant, `reply` porte sur ma lane et le candidat classé diffère de
   l'immédiat dans un test construit pour ça.
6. `win_probability` d'une carte vient du modèle calibré sous toute stratégie (test sur Counter et WIN LANE).
7. Une stratégie perso avec `"search": true` se charge sans changement dans `user_prefs.json` et anticipe.
8. Les cartes n'affichent ni « Fin de draft attendue » ni « profondeur atteinte » : `grep -rn "Fin de draft attendue\|profondeur atteinte" src` ne rend rien.
9. `python scripts/check_exe_assets.py` vert sur un exe reconstruit.
10. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec et `docs/specs/README.md` à jour.

**Vérification de bout en bout** : en draft classée réelle (@pj35), sous WIN LANE, avant que le vis-à-vis soit posé, les
cartes affichent « Réponse attendue : X » et se classent sans délai. Une fois le vis-à-vis posé, la ligne disparaît. Sous
Simple, elle n'apparaît jamais.

## 7. Hors périmètre

- ❌ Modifier le modèle calibré, un K ou `predictions` : rien ici ne touche `game_eval.py`.
- ❌ Stratégie de pool (`E_e[max_{c∈P} M(c,e)]`) : autre sujet, à ouvrir sur demande.
- ❌ Bans et conseils d'échange : ils ne passent pas par la recherche.
- ❌ Renommer `src/draft/search.py`, `DraftSearch` ou la clé `search` : du bruit dans le diff pour un gain de lecture
  faible.
- ❌ Réponses de plusieurs ennemis ou alliés : c'est le minimax qu'on retire.
