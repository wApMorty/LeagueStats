# SPEC-09 — Rendre l'ignorance visible

**Chantier** : B (priorité 2) · **Effort** : ~0,5-1 jour · **Prérequis** : aucun · **Bloque** : rien

**Principe directeur** : un outil d'aide à la décision qui ne sait pas doit le **dire**. Aujourd'hui, sur l'écran le plus utilisé du produit, il se tait.

Les items E1 à E5 sont indépendants et peuvent faire chacun un commit isolé.

---

## E1 — Un champion sans données disparaît sans un mot ⚠️

**Fichier** : `src/draft/recommendations.py`, `DraftRecommender.provide()`, l. 117

```python
matchups = self.m.assistant.get_matchups_for_draft(champion_name, lane=player_lane)
total_games = sum(m.games for m in matchups) if matchups else 0
if matchups and total_games >= draft_config.MIN_CHAMPION_GAMES:
    ...  # scoré et affiché
# ← pas de `else` : le champion sort de la liste sans laisser de trace
```

Un champion de la pool sans données pour la lane assignée est **écarté silencieusement**. Le joueur ne peut pas distinguer *« ce pick est mauvais ici »* de *« je n'ai rien en base »*. Le seul message existe quand **tous** les champions sont écartés (`if not scores`, l. ~200).

**L'incohérence est interne au produit** : l'écran de fin de draft, lui, fait la bonne chose (`src/draft/final_analysis.py:210`) :

```python
if matchup_score is None:
    print(f"  {champion_name:<15} | Données insuffisantes")
```

Deux écrans du même Live Coach, deux comportements opposés face à la même situation.

**Correction** : accumuler les écartés dans une liste `skipped: List[Tuple[str, int]]` (nom, games disponibles) et les afficher après le top N, en section distincte :

```
  [1st] Ahri (middle vs Zed) +3.42% (Matchup: +2.10%, Synergy: +1.32%) · 91 696 games
  [2nd] ...

  [DATA] Sans données exploitables en middle : Malphite (0 games), Pantheon (0 games)
```

Ne pas les mêler au classement : ils ne sont pas classables. Les rendre visibles suffit.

**Test** : `tests/test_draft_monitor_recommendations.py` — un pool de 3 champions dont 1 sans matchups pour la lane ⇒ le nom du champion écarté apparaît dans la sortie, et ne figure pas dans le classement.

---

## E2 — Seuil de scrape des lanes : 10 % → 5 %

**Fichier** : `src/config_constants.py:78`

```python
LANE_PICKRATE_THRESHOLD: float = 10.0
```

Une lane n'est scrapée pour un champion que si elle dépasse 10 % de ses parties. Conséquence mesurée sur la base du 2026-09-05 :

| Seuil | Combos (champion, lane) scrapés | Delta |
|---|---|---|
| 10 % (actuel) | 283 | — |
| 7,5 % | 305 | +22 (+8 %) |
| **5 % (cible)** | **343** | **+60 (+21 %)** |
| 3 % | 388 | +105 (+37 %) |

**60 combos (champion, lane) sont donc aujourd'hui invisibles au coach** alors qu'ils se jouent : Malphite middle (8,7 %), Pantheon middle (9,0 %), Lissandra top (9,6 %), Anivia support (9,5 %), Brand jungle (9,3 %), Zilean middle (9,2 %), Gangplank middle (8,6 %), Taliyah bottom (8,7 %)… Ce sont précisément les picks de niche où un coach a le plus de valeur ajoutée, et où il est actuellement muet (E1 : muet *sans le dire*).

**Coût** : le scrape complet passe de ~45 min à **~55 min** (+21 % de pages), 5 workers. **Arbitré et accepté par @pj35 le 2026-09-05.**

**Correction** : passer la constante à `5.0` et mettre à jour son commentaire — il cite aujourd'hui `ROADMAP_2026.md` H1 (« lanes à pickrate >10 % ») ; noter que la valeur est révisée par SPEC-09 avec le chiffrage ci-dessus.

**Vérification attendue dans la PR** : après un scrape complet, `SELECT COUNT(DISTINCT champion || '|' || lane) FROM matchups` doit valoir ~343 (contre 283). Mettre à jour les seuils volumétriques de `src/data_quality.py` si le contrôle de complétude les référence en absolu.

**Test** : `tests/test_lane_discovery.py` — `select_lanes_to_scrape()` avec une distribution à 6 % retourne la lane au nouveau seuil et pas à l'ancien.

---

## E3 — Le meilleur blind pick ignore encore la lane ⚠️

**Fichier** : `src/draft/automation.py`, `get_best_champion_from_pool()`, l. 93

```python
matchups = self.m.assistant.get_matchups_for_draft(champion_name)   # ← pas de lane=
```

C'est le **5e résidu** de la famille de bugs corrigée en septembre 2026 (Live Coach, écran de fin, bans, Team Builder, Tournament Coach — voir `CHANGELOG.md [Unreleased]`), non détecté par l'audit du 2026-09-04.

Cette fonction alimente `do_initial_hover()` : le champion annoncé comme *« Meilleur blind pick — votre choix le plus sûr »* en tout début de draft, et auto-hover dans le client. Il est choisi sur l'agrégat **toutes lanes confondues** d'un champion multi-lane, alors que la lane est déjà connue à cet instant.

**Correction** : transmettre la lane. Deux sources disponibles sur le monitor, par ordre de préférence :
1. `self.m.pool_lane` — résolu par `PoolSelector` via `pool_manager.pool_role_to_lane()`, déjà en place depuis le fix des bans ;
2. `self.m.last_draft_state.ally_positions.get(local_player_cell_id)` — la position assignée par la file.

Prendre (1) si non nul, sinon (2), sinon `None` (comportement actuel, légitime en file sans rôle assigné). Appliquer aussi le seuil de E1 : un champion écarté ici doit être signalé, pas escamoté.

**Test de régression obligatoire** (bug utilisateur avéré) : `tests/regression/test_regression_blind_pick_lane_filter.py`, sur le modèle de `test_regression_live_coach_lane_filter.py`. Docstring : symptôme, cause racine, correctif, prévention.

---

## E4 — `db_meta.last_recompute_utc` ment hors mode `recompute_only`

**Fichier** : `src/pipeline.py:341`

`last_recompute_utc` n'est écrit que dans la branche `if recompute_only:`. Or un scrape complet **recalcule bien** `champion_scores` et `pool_ban_recommendations` (étapes 3 et 4, l. 312-324) sans jamais toucher la métadonnée.

Constat en base : `last_recompute_utc = 2026-08-28` alors que le scrape date du `2026-09-03` et que les bans ont été recalculés le `2026-09-04`.

Aucun code ne lit cette clé aujourd'hui (`data_freshness.py` lit `last_scrape_utc`), donc **aucun impact utilisateur actuel** — mais la valeur est fausse, et le sera visiblement dès qu'un écran l'affichera.

**Correction** : sortir l'écriture de `last_recompute_utc` de la branche `recompute_only` et la placer juste après le recalcul effectif (l. 324), dans les deux chemins.

**Test** : `tests/test_pipeline.py` — après un `run_pipeline()` complet mocké, `db_meta.last_recompute_utc` est postérieur au début du run.

---

## E5 — Volume de games dans les écrans hors Live Coach

Le Live Coach affiche le volume derrière chaque recommandation (`· 91 696 games`, `recommendations.py` l. ~175). Les autres écrans, non : `src/ui/tier_list_ui.py`, `src/ui/team_builder_ui.py` et `src/ui/tournament_display_ui.py` n'affichent aucun indicateur de fiabilité.

L'infrastructure existe (`confidence(games)` dans `src/analysis/scoring.py`, volumétrie disponible dans les résultats).

**Correction** : afficher le volume, ou à défaut un marqueur de confiance, sur les mêmes conventions que le Live Coach. Item volontairement souple : à traiter écran par écran, un commit chacun, sans refonte d'affichage.

**Test** : au moins un test par écran modifié vérifiant la présence du volume dans la sortie.

---

## Critères d'acceptation (globaux)

1. Aucun champion d'une pool ne peut sortir de l'écran de recommandations sans être ni classé, ni listé comme écarté.
2. Après un scrape complet au nouveau seuil, ~343 combos (champion, lane) en base.
3. Le blind pick initial et les recommandations de pick utilisent la **même** lane.
4. `pytest tests/ -v` vert, `black --check`, `pylint src/ --fail-under=8.0`.

## Hors périmètre

- ❌ Repli silencieux sur l'agrégat toutes-lanes quand la lane manque : ce serait remplacer une donnée absente par une donnée trompeuse, exactement le bug corrigé en septembre.
- ❌ Refonte de l'affichage console.
- ❌ Toucher aux seuils `MIN_CHAMPION_GAMES` / `MIN_GAMES_THRESHOLD` : ce sont des valeurs à **calibrer** (SPEC-08), pas à ajuster à l'intuition.
