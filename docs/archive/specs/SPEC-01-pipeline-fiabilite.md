# SPEC-01 — Pipeline : remettre le dernier maillon en place

**Items** : A1, A2, A3, A4, A5, A6 · **Priorité** : 1 · **Effort estimé** : ~1 jour
**Constats d'audit** : F1, F2, F3, F6, F9 (`docs/AUDIT_2026_08.md` §3)
**Prérequis** : aucun · **Bloque** : rien (mais rend tout le reste diagnosticable)

---

## 1. Contexte

Le scrape fonctionne : la base contient 26 398 matchups et 21 288 synergies multi-lane, scrapés le 25/08/2026. Ce sont les **étapes qui suivent le scrape** qui décrochent, et rien ne le signale.

Il existe **deux orchestrateurs** qui ne font pas le même travail :

| Étape | Menu 3 (`src/ui/lol_coach_legacy.py`) — **utilisé** | `scripts/update_all.py` — plus lancé depuis le 16/07 |
|---|---|---|
| Découverte de lane dynamique | ✅ `_scrape_by_discovered_lane` (l. 98) | ✅ via `src/multilane.py` |
| Scrape multi-lane taggé | ✅ | ✅ |
| Contrôle de complétude | ❌ | ✅ `assert_completeness` |
| Recalcul `champion_scores` | ✅ (précédé d'un `DROP`) | ✅ |
| Recalcul `pool_ban_recommendations` | ❌ | ✅ |
| Écriture `db_meta` (fraîcheur) | ❌ | ✅ |
| Log fichier | ❌ (console seule) | ✅ `logs/update_all.log` |
| Notifications | ❌ | ✅ toast + Discord |

**Conséquence constatée le 29/08** : `champion_scores` contient **0 ligne**. Le menu 3 appelle `db.init_champion_scores_table()` (= `DROP TABLE`, `src/db.py:203-217`) *avant* le scrape, puis `assistant.calculate_global_scores()` à la fin. Le 25/08, ce recalcul a levé un `AttributeError` sur chaque champion (corrigé le jour même par `08d2c9c`), la table est restée vide, et **rien n'a alerté pendant 4 jours**. Les tier lists renvoient `[ERROR] No champion scores found in database`.

---

## 2. Objectif

À la fin de cette spec :

1. Les tier lists refonctionnent.
2. Il n'existe **qu'un seul** chemin de mise à jour des données, avec tous ses garde-fous.
3. L'âge des données affiché au démarrage reflète le dernier **scrape**, jamais autre chose.
4. Un échec partiel de scrape ne détruit plus 45 minutes de travail.
5. La CI est verte sur `master`.

---

## 3. Travail à faire

### A1 — Recalculer `champion_scores` maintenant

Ajouter à `scripts/update_all.py` un mode qui saute le scrape et ne fait que les étapes dérivées :

```bash
python scripts/update_all.py --recompute-only
```

- Nouvel argument dans `_parse_args()` : `--recompute-only` (`action="store_true"`).
- Quand il est actif : sauter les étapes 1 (scrape) et 2 (complétude), exécuter les étapes 3 (`calculate_global_scores`), 4 (`precalculate_all_custom_pool_bans`) et 5 (`db_meta`).
- Pour `db_meta` dans ce mode : ne **pas** écrire `last_update_utc` (les données n'ont pas été rafraîchies), mais écrire `last_recompute_utc`.
- Exécuter la commande une fois pour restaurer l'état de la base (172 champions attendus).

### A2 — Faire converger les deux orchestrateurs

`src/ui/lol_coach_legacy.py` réimplémente le pipeline à quatre endroits : `parse_pool_statistics` (l. ~190-295), `parse_all_champions` (l. ~298-395), et les deux variantes « all data » (l. ~589-720, ~729-850). Toutes suivent le même schéma : `init_*_table()` → `_scrape_by_discovered_lane(...)` → `calculate_global_scores()`.

**À faire** : remplacer le corps de ces fonctions par un appel à la logique de `scripts/update_all.py`.

- Extraire le pipeline de `scripts/update_all.py:main()` dans une fonction réutilisable — par exemple `run_pipeline(champions=None, include_synergies=True, workers=None, patch=None) -> PipelineResult`. Le placer dans un module `src/pipeline.py` (nouveau) plutôt que dans `scripts/`, pour être importable proprement depuis l'UI. `scripts/update_all.py` devient un mince point d'entrée CLI autour de cette fonction.
- Le paramètre `champions=None` signifie « tout le roster » ; une liste restreinte couvre le cas « pool seulement » du menu.
- Les fonctions du menu appellent `run_pipeline(...)` et se contentent d'afficher le résultat.
- **Ne pas faire grossir `lol_coach_legacy.py`** : ce chantier doit le faire *maigrir* (plusieurs centaines de lignes en moins).

### A3 — Rendre la fraîcheur mesurable

Deux corrections indissociables :

**(a) Écrire `db_meta` au bon endroit.** Aujourd'hui l'écriture est dans `scripts/update_all.py:main()` (étape 5), donc le menu ne l'écrit jamais. Après A2, elle se retrouve naturellement dans `run_pipeline`. Écrire :

| Clé | Quand | Valeur |
|---|---|---|
| `last_scrape_utc` | après un scrape terminé, **même si la complétude échoue** | ISO 8601 UTC |
| `last_full_success_utc` | seulement si tout le pipeline a abouti | ISO 8601 UTC |
| `last_scrape_status` | après chaque run | `"ok"` / `"partial"` / `"failed"` |
| `matchups_count`, `synergies_count`, `last_update_patch` | comme aujourd'hui | — |

Conserver `last_update_utc` en écriture pour compatibilité avec les bases existantes, mais lire `last_scrape_utc` en priorité.

**(b) Supprimer le repli sur le `mtime`.** `src/data_freshness.py:70-72` :

```python
else:
    info.last_update = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    info.source = "file_mtime"
```

Ce repli mesure la dernière **ouverture** du fichier (l'application écrit dans `data/db.db` à chaque session : pools, bans…), pas la dernière mise à jour des données. Il affichait « à jour » sur des données de six semaines entre le 16/07 et le 25/08. **Le retirer** : sans métadonnée, `last_update` reste `None`, ce que `format_freshness_banner` traite déjà comme un cas d'alerte — adapter son message :

```
[ALERTE] FRAÎCHEUR INCONNUE — la base ne porte pas de date de mise à jour.
         Lancez : python scripts/update_all.py
```

Ajouter au bandeau, quand `last_scrape_status != "ok"`, une seconde ligne signalant que le dernier run est incomplet.

### A4 — Contrôle de complétude gradué

`src/data_quality.py` lève `DataCompletenessError` dès **un seul** champion sous le seuil. Le 16/07, 566/566 pages avaient été scrapées avec succès, 13 champions sont sortis sans synergies, et tout le pipeline a été annulé — scores et bans compris.

Introduire deux niveaux dans `CompletenessReport` :

- `blocking_failures` — la base est inexploitable :
  - `matchups_total < MIN_TOTAL_MATCHUPS` ou `synergies_total < MIN_TOTAL_SYNERGIES` ;
  - plus de `MAX_INCOMPLETE_CHAMPIONS_RATIO` (nouvelle constante, **0.05**) de champions vides ou sous le seuil ;
  - table `champions` vide.
- `warnings` — quelques trous : liste des champions concernés.

`assert_completeness()` ne lève que sur `blocking_failures`. Sur `warnings` : journaliser en `WARNING`, **continuer** le pipeline (scores + bans recalculés), notifier avec le statut `"partial"`, et écrire `last_scrape_status = "partial"`.

Ajouter en fin de run, quand des `warnings` existent, une relance ciblée de la réparation pour les champions concernés (`scripts/repair_data.py` expose `MATCHUPS` / `SYNERGIES` via `RepairTarget` — réutiliser ces cibles plutôt que de relancer un scrape complet). Si la réparation échoue, rester en `"partial"` : ne jamais boucler.

**Cas particulier à traiter** : `Aphelios` a **0 matchup** en base. C'est le seul champion qui déclencherait un blocage aujourd'hui. Vérifier la normalisation de son nom d'URL (`src/constants.py:normalize_champion_name_for_url`) contre l'URL réelle `https://lolalytics.com/lol/aphelios/build/` et corriger.

### A5 — Sauvegarde avant `DROP`

`src/multilane.py:75-81` fait `db.init_matchups_table()` + `db.init_synergies_table()` — soit `DROP TABLE` — avant ~45 min de scraping. Le menu 3 fait la même chose. Toute interruption dans cette fenêtre détruit la base : c'est le mécanisme exact du sinistre du 01/06/2026 (40 753 → 16 179 matchups).

**Version retenue (suffisante, peu coûteuse)** : sauvegarde-restauration du fichier.

1. Avant tout `DROP`, copier `config.DATABASE_PATH` vers `data/db.backup-<timestamp>.db` (utiliser l'API `sqlite3.Connection.backup()`, pas `shutil.copy` — elle est sûre même si une connexion est ouverte).
2. Si le pipeline se termine en `"ok"` ou `"partial"` : conserver la sauvegarde, en purgeant les plus anciennes au-delà de `BACKUP_RETENTION` (nouvelle constante, **3**).
3. Si le pipeline échoue (exception, `blocking_failures`, interruption clavier) : **restaurer** la sauvegarde et le dire clairement dans le log et la notification.
4. Ajouter le motif `data/db.backup-*.db` au `.gitignore` (attention : `*.db` y est déjà — vérifier avant d'ajouter une ligne redondante).

Envelopper le run dans un `try/except/finally` qui couvre aussi `KeyboardInterrupt`.

### A6 — Réparer la CI

Deux causes indépendantes, vérifiées :

**(a) Black.** `requirements-dev.txt` pin `black==26.3.1` (Dependabot PR #44, mergé le 25/08) mais le code n'a jamais été reformaté ; la CI échoue sur `black --check`. En local c'est black 24.10.0 qui est installé, il répond « All done » — d'où l'invisibilité du problème.

```bash
pip install black==26.3.1
python -m black src/ tests/ scripts/
```

Commit dédié `🎨 Style:` séparé de tout changement fonctionnel.

**(b) Test obsolète.** `tests/test_pool_manager.py::TestPoolManagerBanRecalculation::test_save_custom_pools_recalc_bans_in_dev_mode` fait `mock_db_class.assert_called_once_with("data/db.db")`, mais `PoolManager.__init__` ouvre désormais la base une fois de plus via `_load_role_pools_from_db()` (pools système dynamiques, PR #41). Corriger l'assertion pour vérifier l'appel attendu parmi les appels réels (`assert call("data/db.db") in mock_db_class.call_args_list`) plutôt que l'unicité.

*Note : l'isolation de ce test (il touche la vraie base) est traitée par E6 dans SPEC-07 — hors périmètre ici.*

---

## 4. Critères d'acceptation

- [ ] `python scripts/update_all.py --recompute-only` remplit `champion_scores` (172 champions attendus) sans re-scraper.
- [ ] Le menu 3 et `scripts/update_all.py` exécutent le **même** code : contrôle de complétude, `db_meta`, recalcul des bans, log fichier et notifications sont effectifs dans les deux cas.
- [ ] Sur une base sans `db_meta`, le bandeau de démarrage affiche `[ALERTE] FRAÎCHEUR INCONNUE` — jamais une durée estimée.
- [ ] Après un run réussi, le bandeau affiche l'âge réel calculé depuis `last_scrape_utc`.
- [ ] Un run où 3 champions sur 173 sont incomplets se termine avec le statut `"partial"` : scores et bans **sont** recalculés, la notification signale les champions manquants.
- [ ] Un run où la volumétrie globale s'effondre (< 20 000 matchups) est bloqué et **la base précédente est restaurée**.
- [ ] `Aphelios` a des matchups après le prochain scrape.
- [ ] `pytest tests/ -v` : 0 échec. `black --check` et `pylint --fail-under=8.0` passent. CI verte sur `master`.
- [ ] `src/ui/lol_coach_legacy.py` a **diminué** en nombre de lignes.

---

## 5. Tests exigés

| Fichier | Contenu |
|---|---|
| `tests/test_pipeline.py` (nouveau) | `run_pipeline` : mode `recompute_only`, propagation du statut `ok`/`partial`/`failed`, écriture des clés `db_meta` attendues (base temporaire, scrape mocké) |
| `tests/test_data_quality.py` (nouveau ou étendu) | Séparation `blocking_failures` / `warnings` : 3 champions vides sur 173 → warning ; 20 champions vides → blocage ; volumétrie effondrée → blocage |
| `tests/test_data_freshness.py` (existant) | Ajouter : base sans `db_meta` → `last_update is None` et `is_stale is True` ; **retirer/adapter** les tests qui vérifiaient le repli `file_mtime` |
| `tests/regression/test_regression_scores_recompute.py` (nouveau) | Régression de l'incident du 25/08 : après un `init_champion_scores_table()` suivi d'un `calculate_global_scores()` qui échoue, le pipeline doit renvoyer un statut d'échec — pas un succès silencieux |
| `tests/test_pipeline_backup.py` (nouveau) | Échec en cours de run → la base restaurée est identique à l'originale (comparer un `COUNT(*)` avant/après) |
| `tests/test_pool_manager.py` (existant) | Correction de l'assertion (A6b) |

---

## 6. Pièges connus

- **`Database` et threads** : `src/parallel_parser.py` sérialise les écritures avec `self.db_lock`. Ne pas partager une connexion SQLite entre threads sans ce verrou.
- **Ordre des étapes** : `calculate_global_scores()` doit tourner **après** le scrape et **après** le contrôle de complétude, mais son échec ne doit plus faire perdre les données scrapées (c'est tout l'objet de A4/A5).
- **`Assistant()` sans argument** ouvre `config.DATABASE_PATH` — dans les tests, toujours injecter un mock ou une base temporaire.
- **`db.set_meta` / `db.get_meta`** existent déjà (`src/db.py:1127-1163`) : les réutiliser, ne pas réécrire d'accès à `db_meta`.
- **`--skip-completeness`** existe déjà comme option de diagnostic : la conserver, elle sert quand LoLalytics est en vrac.
- **Notifications** : `src/notifications.py` est best-effort et ne lève jamais. Ne pas faire dépendre le statut du pipeline de leur succès.

---

## 7. Hors périmètre

- L'automatisation nocturne (Task Scheduler) reste **suspendue par choix** — ne pas la réactiver. Noter simplement dans `docs/AUTO_UPDATE_SETUP.md` que la tâche pointe encore sur `scripts/auto_update_db.py`.
- La suppression de `scripts/auto_update_db.py` (doublon de `update_all.py`) : possible ici si le contexte s'y prête, sinon SPEC-07.
- Toute modification du scoring ou de la lecture des lanes : SPEC-03 et SPEC-05.
