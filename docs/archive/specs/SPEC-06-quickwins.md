# SPEC-06 — Quick wins : performance, confort, hygiène

**Items** : C2, C3, C4, D1, D2, D3, D4, E5, E7, E8 · **Effort** : < 1 h par item
**Constats d'audit** : P2, P3, P4, U1, U2, U3, F8, M7, M8, §7.4 (`docs/AUDIT_2026_08.md`)
**Prérequis** : aucun · **Bloque** : rien

Chaque item est **indépendant** et peut faire l'objet d'un commit isolé. Aucun n'exige de réflexion architecturale : ce sont des corrections dont le diagnostic est déjà fait.

---

## C2 — Sortir `get_all_champion_names()` de la boucle des trios

**Fichier** : `src/assistant.py`, `_evaluate_trio_holistic` (l. 1577)

```python
# Get all champions from database (dynamic, includes new champions)
all_champions = list(self.db.get_all_champion_names().values())
```

Cet appel est **dans la boucle** de `find_optimal_trios_holistic` : pour un pool de 15 champions, 455 trios × une requête SQL + construction d'un dict de 173 entrées. Le pré-chargement `get_all_matchups_bulk()` juste au-dessus (l. 1509) montre que le pattern est déjà connu.

**Correction** : charger la liste une fois dans `find_optimal_trios_holistic` et la passer en paramètre à `_evaluate_trio_holistic`, comme `matchup_cache`.

**Test** : `tests/test_assistant_cache.py` — vérifier par mock que `get_all_champion_names` est appelé une seule fois pour N trios.

---

## C3 — Supprimer le double calcul d'affichage du top 3

**Fichier** : `src/draft_monitor.py`, `_provide_recommendations` (l. 818)

La boucle de scoring calcule `matchup_score` et `synergy_score` pour tous les champions du pool, trie, puis **recalcule les deux** pour chacun des 3 affichés (l. ~910-925).

**Correction** : stocker le triplet `(champion_id, final_score, matchup_score, synergy_score)` dans `scores` et réutiliser les valeurs à l'affichage.

**Enjeu réel** : au-delà du coût, deux calculs séparés peuvent diverger — le classement afficherait alors des valeurs qui ne le justifient pas.

**Test** : `tests/test_draft_monitor_*.py` — vérifier par mock que les fonctions de score sont appelées une fois par champion, pas deux.

---

## C4 — Retirer `COLLATE NOCASE` des jointures

**Fichier** : `src/db.py`, `get_matchup_delta2` (l. 799)

```sql
WHERE c1.name = ? COLLATE NOCASE AND c2.name = ? COLLATE NOCASE
```

`COLLATE NOCASE` sur la colonne comparée empêche l'utilisation de l'index sur `champions.name`. Mesure : **6,3 ms par appel** (200 appels en 1,27 s) sur une base de 26 k lignes — environ 50× le coût attendu d'une lecture indexée. Le draft coach fait 5 appels par champion de pool et par changement d'état du draft.

**Correction** : normaliser les noms côté Python avant la requête (le projet a déjà `build_champion_cache()` qui indexe en minuscules, et `src/utils/champion_utils.py` pour la normalisation), ou créer un index `COLLATE NOCASE` explicite :

```sql
CREATE INDEX idx_champions_name_nocase ON champions(name COLLATE NOCASE);
```

La seconde option est moins invasive et conserve le comportement insensible à la casse — la retenir sauf raison contraire.

**Vérification** : `EXPLAIN QUERY PLAN` avant/après doit montrer un `SEARCH ... USING INDEX` au lieu d'un `SCAN`. Mesurer les 200 appels avant/après et reporter le chiffre.

**Test** : `tests/test_db_lane.py` ou équivalent — les recherches restent insensibles à la casse (`"jinx"`, `"Jinx"`, `"JINX"` donnent le même résultat).

---

## D1 — Corriger le chemin de `champion_pools.json` ⚠️

**Fichier** : `src/pool_manager.py`, `get_user_pools_path` (l. 9-22)

```python
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
```

Trois `dirname` depuis `src/pool_manager.py` remontent **un cran trop haut**. Vérifié :

```
PATH: D:\Users\Paul\Documents\Code Workspace\champion_pools.json   ← hors du dépôt
```

Les 5 pools personnels (GRIND, Support, Mid, Top playable, NINO) vivent hors du projet, hors sauvegarde. `src/config.py:31` utilise, lui, **deux** `dirname` — l'incohérence est interne au code.

**Correction** :

1. Passer à deux `dirname` (ou mieux : réutiliser la logique de `src/config.py`).
2. **Migration silencieuse** : au chargement, si le fichier n'existe pas au nouvel emplacement mais existe à l'ancien, le déplacer et le signaler (`[INFO] Pools migrés depuis <ancien chemin>`). Sans ça, l'utilisateur perd ses pools.
3. Vérifier que `champion_pools.json` est bien couvert par `.gitignore` (le `*.json` global s'en charge — voir E5 avant de le restreindre).

**Ne pas toucher** au chemin en mode `sys.frozen` (à côté de l'exécutable), qui est correct.

**Test** : `tests/test_pool_manager.py` — chemin attendu en mode dev ; migration depuis l'ancien emplacement ; absence de migration quand le nouveau fichier existe déjà.

---

## D2 — Mémoriser les préférences du draft coach

**Fichiers** : `lol_coach.py` (l. ~130-160), `src/ui/draft_coach_ui.py`

Six questions avant chaque session : auto-hover, auto-accept queue, auto-ban hover, onetricks, poids synergie, puis choix du pool. Les réponses sont presque toujours les mêmes.

**Correction** : un fichier de préférences `user_prefs.json` (même emplacement que `champion_pools.json`, après correction D1), avec les derniers choix. Au lancement :

```
Préférences précédentes : hover=oui, accept=non, ban-hover=oui, onetricks=oui, synergie=0.5, pool=GRIND
[Entrée] pour reprendre · [m] pour modifier
```

Une touche au lieu de six réponses. Écriture best-effort (un fichier illisible ou absent retombe sur les questions, sans erreur bloquante).

**Test** : nouveau `tests/test_user_prefs.py` — sauvegarde/relecture, fichier absent, fichier corrompu, valeurs hors bornes ignorées.

---

## D3 — Unifier la langue de l'interface (français)

Le menu principal (`src/ui/menu_system.py`), les messages `[ERROR]`/`[INFO]` et les conseils de draft sont en anglais ; la bannière de fraîcheur, le prompt de poids de synergie et les notifications Discord sont en français. Pour un utilisateur unique francophone, trancher : **français**.

**Périmètre** : uniquement les chaînes **affichées à l'utilisateur**. Ne toucher ni aux noms de variables, ni aux docstrings, ni aux messages de log techniques, ni aux noms de champions.

**Ordre suggéré** : `menu_system.py` (menu principal) → `draft_coach_ui.py` → messages du draft monitor → `lol_coach_legacy.py` (le plus volumineux, à faire en dernier).

**Attention** : certains tests vérifient des chaînes affichées (`grep -rn "Choose an option\|Press Enter" tests/`). Les mettre à jour dans le même commit.

---

## D4 — Purger les emojis des sorties console

`src/data_freshness.py` explique en commentaire que les emojis font planter les consoles cp1252 (sortie redirigée, `pythonw`) et utilise donc `[OK]`/`[ALERTE]`. Mais `draft_coach_ui.py` (`🎯 🔥 🚫 🌐`), `assistant.py` (`✅ ⚠️`) et `draft_monitor.py` en émettent.

**Correction** : remplacer par les marqueurs ASCII de la convention maison (`[OK]`, `[ALERTE]`, `[INFO]`, `[ERREUR]`).

```bash
grep -rnP "[\x{1F300}-\x{1FAFF}\x{2600}-\x{27BF}]" src/ lol_coach.py
```

**Exception** : les notifications Discord (`src/notifications.py`) passent par HTTP en UTF-8 — les emojis y sont sans risque, les conserver.

---

## E5 — Hygiène du dépôt

**Fichiers parasites trackés dans git** (créés par des redirections shell ratées, signalés dès juin 2026) :

```bash
git rm "2.0.0" "90%" "Dict[str"
```

**Résidus sur disque** (non trackés, à supprimer manuellement) :

| Chemin | Origine |
|---|---|
| `server/` | Couche FastAPI supprimée du dépôt en juillet (`17c621b`), dossier resté sur disque |
| `node_modules/`, `package.json`, `package-lock.json` | Outillage Ruflo/claude-flow, désinstallé le 25/07 |
| `config/.env.neon` | Base Neon décommissionnée |
| `outputs/t13_neon_readonly_user.yaml` | Idem |
| `logs/auto_update.log` | 12,7 Mo, dernière écriture 19/03/2026 |
| `e2e/` | Vide |

**`.gitignore`** : la règle `*.json` est globale et ignore silencieusement tout nouveau fichier JSON légitime. La restreindre aux fichiers de données réels (`champion_pools.json`, `user_prefs.json`, `benchmark.json`) — **en vérifiant d'abord** qu'aucun JSON actuellement ignoré ne devrait être versionné (`git status --ignored | grep json`).

---

## E7 — Sortir les seuils métier vers `config_constants`

Malgré la règle « aucune valeur hardcodée » de `CLAUDE.md` :

| Valeur | Emplacement | Constante cible |
|---|---|---|
| `m.games >= 200`, `m.pickrate >= 0.5` | `src/db.py` : `get_matchup_delta2` (l. 799), `get_all_matchups_bulk` (l. 847), `get_all_synergies_bulk` (l. 1085), `get_reverse_matchups_for_draft` (l. 620) | `analysis_config.MIN_MATCHUP_GAMES`, `MIN_PICKRATE` |
| `m.pickrate > 0.5` | `get_champion_matchups_by_name` (l. 292), `get_champion_matchups_for_draft` (l. 556) | `analysis_config.MIN_PICKRATE` |
| `sum(m.games) >= 500` | `src/draft_monitor.py` (l. ~884) — seuil d'éligibilité aux recommandations | nouvelle `draft_config.MIN_CHAMPION_GAMES` |
| `min(3, len(scores))` | `src/draft_monitor.py` (l. ~903) — nombre de recommandations | `ui_config.MAX_RECOMMENDATIONS` (existe déjà, vaut 5 — arbitrer) |

**Attention** : ces valeurs sont interpolées dans des requêtes SQL. Utiliser des **paramètres liés**, jamais du formatage de chaîne :

```python
cursor.execute(sql, (champion, enemy, analysis_config.MIN_PICKRATE, analysis_config.MIN_MATCHUP_GAMES))
```

**Vérifier** que la valeur en config correspond exactement à celle en dur avant remplacement — un écart changerait les résultats sans le dire.

---

## E8 — Corriger la casse dans `calculate_synergy_bonus`

**Fichier** : `src/analysis/scoring.py`, `calculate_synergy_bonus`

```python
relevant_synergies = [s for s in synergies if s.ally_name in ally_names]
```

Comparaison **exacte**, alors que tout le reste du code normalise en minuscules (`m.enemy_name.lower()` dans `score_against_team`). Toute variation de casse dans la liste d'alliés fait silencieusement tomber le bonus de synergie à 0 — sans erreur, sans avertissement.

**Correction** :

```python
allies_lower = {name.lower() for name in ally_names}
relevant_synergies = [s for s in synergies if s.ally_name.lower() in allies_lower]
```

**Test de régression obligatoire** : `tests/regression/test_regression_synergy_case_sensitivity.py` — `["yasuo"]`, `["Yasuo"]` et `["YASUO"]` donnent le même bonus, non nul.

---

## Critères d'acceptation communs

- [ ] Un commit atomique par item, avec le Gitmoji correspondant.
- [ ] `pytest tests/ -v` : 0 échec après chaque item.
- [ ] `black --check` et `pylint --fail-under=8.0` passent.
- [ ] Aucun item n'introduit de valeur hardcodée ni ne fait grossir un fichier déjà > 500 lignes.
- [ ] C4 : mesure avant/après reportée dans le CHANGELOG.
- [ ] D1 : les pools existants sont récupérés, pas perdus.
