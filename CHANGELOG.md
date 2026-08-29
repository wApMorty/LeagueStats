# Changelog

All notable changes to LeagueStats Coach will be documented in this file.

## [Unreleased] - 2026-08-29

### ✨ Ajouts

- **SPEC-01 A5 — sauvegarde avant `DROP`.** `run_pipeline()` snapshote désormais
  `data/db.db` (nouveau module `src/db_backup.py`, via `sqlite3.Connection.backup()` —
  sûr même avec une connexion déjà ouverte) juste avant que `scrape_all_multilane()`
  ne fasse son `DROP TABLE` sur `matchups`/`synergies`, soit ~45 minutes avant la fin
  du scrape. C'est le mécanisme exact du sinistre du 01/06/2026 (40 753 → 16 179
  matchups) : toute interruption dans cette fenêtre détruisait la base sans recours.
  - Run `"ok"` ou `"partial"` : la sauvegarde est conservée, les plus anciennes au-delà
    de `data_quality_config.BACKUP_RETENTION` (3) sont purgées.
  - Run en échec — exception, `DataCompletenessError` (`blocking_failures`), ou
    `KeyboardInterrupt` (Ctrl+C) — : la base est restaurée depuis la sauvegarde et le
    log/la notification le disent explicitement. `run_pipeline()` capture désormais
    aussi `KeyboardInterrupt` pour garantir le même contrat qu'avant A5 : jamais
    d'exception qui remonte jusqu'à l'appelant (menu ou CLI), toujours un
    `PipelineResult(status="failed")`.
  - `data/db.backup-*.db` est déjà couvert par la règle `*.db` du `.gitignore`
    existante — aucune ligne redondante ajoutée.
- **SPEC-01 A4 — contrôle de complétude gradué.** `check_completeness()` distingue
  désormais `blocking_failures` (base inexploitable : volumétrie globale effondrée,
  table `champions` vide, ou plus de `MAX_INCOMPLETE_CHAMPIONS_RATIO` = 5 % de champions
  vides/sous le seuil) de simples `warnings` (quelques champions incomplets sous ce ratio).
  `assert_completeness()` ne lève plus que sur `blocking_failures` — c'est exactement le
  scénario du 16/07 (566/566 pages OK, 13 champions sans synergies) qui annulait jusqu'ici
  tout le pipeline, scores et bans compris.
  - Sur `warnings` : le pipeline continue (scores + bans recalculés), tente une réparation
    ciblée des champions concernés via `scripts/repair_data.py` (`MATCHUPS`/`SYNERGIES`,
    même découverte de lane que le run nominal), puis écrit `last_scrape_status = "partial"`
    et notifie avec le récapitulatif des champions et de la réparation.
  - `Aphelios` (0 matchup, seul champion qui aurait bloqué un run avant A4) : vérifié —
    `normalize_champion_name_for_url("Aphelios")` renvoie déjà `"aphelios"`, qui correspond
    à l'URL réelle LoLalytics ; la normalisation n'est **pas** en cause. La cause du 0 matchup
    reste à diagnostiquer sur un run réel (hors portée d'une vérification statique).
- **SPEC-01 A3 — fraîcheur mesurable.** `run_pipeline()` écrit désormais `last_scrape_utc`
  dès la fin du scrape, **même si le contrôle de complétude échoue ensuite** — jusqu'ici un
  run bloqué ne laissait aucune trace en base. `last_scrape_status` (`"ok"` / `"failed"` /
  `"partial"`, ce dernier statut posé par A4) est écrit après chaque run avec scrape, et
  `last_full_success_utc` seulement quand tout le pipeline a abouti. `last_update_utc`
  reste écrit pour compatibilité avec les bases existantes.
  - `src/data_freshness.py` lit désormais `last_scrape_utc` en priorité (repli sur
    `last_update_utc` pour les bases antérieures à A3).
  - **Repli sur le `mtime` du fichier supprimé** : il mesurait la dernière *ouverture* de
    `data/db.db` (réécrit à chaque session pour les pools/bans), pas la dernière mise à jour
    des données — c'est ce qui a masqué six semaines de données obsolètes entre le 16/07 et
    le 25/08 (`docs/AUDIT_2026_08.md` F2). Sans métadonnée, le bandeau affiche désormais
    `[ALERTE] FRAÎCHEUR INCONNUE` au lieu d'un âge estimé.
  - Le bandeau affiche une seconde ligne d'alerte quand `last_scrape_status != "ok"`.

### ⚡ Performance

- **SPEC-02 (C1) — matchups + synergies en une seule visite de page.** `src/parser.py`
  chargeait deux fois la même URL LoLalytics par couple (champion, lane) : une fois pour
  les matchups (`get_champion_data_on_patch`), une fois pour les synergies
  (`get_champion_synergies_on_patch`), alors que les deux jeux de données sont sur la même
  page (seul l'onglet « Common Teammates » change). Nouvelle méthode
  `Parser.get_champion_page_data()` : charge la page une fois, lit le carrousel matchups,
  clique sur l'onglet synergies, relit le carrousel — via un tronc commun
  `_extract_carousel_rows()` qui conserve tous les garde-fous existants (boucle infinie,
  éléments périmés, sentinelle de pickrate) factorisés depuis les deux anciennes méthodes.
  - `ParallelParser.parse_page_by_role()` remplace l'appel séquentiel
    `parse_champions_by_role` + `parse_synergies_by_role` dans `src/multilane.py` : une
    seule passe parallèle par lane, un seul chargement de page par champion.
  - **Tolérance aux pannes préservée** : un échec de l'onglet synergies (bouton introuvable
    ou section qui ne rend jamais) n'efface pas les matchups déjà extraits — le champion est
    marqué dans `synergies_missing` (remonté dans le rapport de notification et repris par la
    réparation ciblée de SPEC-01 A4), pas perdu.
  - `get_champion_data_on_patch()` / `get_champion_synergies_on_patch()` restent en place,
    devenues de fines enveloppes autour de `get_champion_page_data()` — toujours utilisées
    par `scripts/repair_data.py`.
  - Gain de volumétrie attendu : ~40 % de requêtes en moins vers LoLalytics (283 pages au
    lieu de 566 pour un run complet 173 champions) ; durée réelle à mesurer sur un run
    complet et à reporter ici (référence : 45 min le 16/07, `DEFAULT_MAX_WORKERS = 5`).
- **SPEC-06 (C2) — `get_all_champion_names()` sorti de la boucle des trios.**
  `Assistant._evaluate_trio_holistic()` rechargeait la liste des 173 champions
  (une requête SQL + construction d'un dict) à **chaque trio évalué** — 455 requêtes
  identiques pour un pool de 15 champions. `find_optimal_trios_holistic()` la précharge
  désormais une seule fois, comme `matchup_cache` juste au-dessus, et la passe en
  paramètre à `_evaluate_trio_holistic()`.

### ♻️ Refactoring

- **SPEC-01 A2 — convergence des deux orchestrateurs de pipeline.** `scripts/update_all.py`
  et le menu 3 (`src/ui/lol_coach_legacy.py`) réimplémentaient chacun le schéma
  scrape → complétude → scores → bans → fraîcheur, et avaient dérivé : le menu ne
  lançait jamais le contrôle de complétude, n'écrivait jamais `db_meta`, et ne
  loggait/notifiait jamais. Le pipeline est extrait dans un nouveau module
  `src/pipeline.py::run_pipeline()`, désormais l'unique chemin de mise à jour des
  données utilisé par les deux entrées.
  - `scripts/update_all.py` devient un mince point d'entrée CLI (~150 lignes en moins).
  - `src/ui/lol_coach_legacy.py` : les 6 fonctions de parsing du menu (`parse_champion_pool`,
    `parse_all_champions`, `parse_synergies_pool`, `parse_synergies_all`,
    `parse_all_data_pool`, `parse_all_data_all`) délèguent maintenant à `run_pipeline()`
    (**-534 lignes** au total, dont l'ancien helper `_scrape_by_discovered_lane` devenu mort).
  - `src/multilane.py::scrape_all_multilane()` accepte désormais `champions=` (scope
    restreint à un pool, sans rafraîchissement complet depuis l'API Riot) et
    `include_matchups=` (indépendant de `include_synergies=`).
  - Effet de bord attendu : toute exécution déclenchée depuis le menu bénéficie
    désormais du contrôle de complétude, de l'écriture `db_meta`, du log fichier
    (`logs/update_all.log`) et des notifications (toast + Discord) — comme le run CLI.
    Le contrôle de complétude (portant sur tout le roster) reste sauté pour les scopes
    "pool" du menu, puisqu'il échouerait systématiquement sur les champions hors pool.

### ✨ Ajouts

- **`scripts/update_all.py --recompute-only`** — recalcule `champion_scores` et
  `pool_ban_recommendations` sans re-scraper. Restaure la table `champion_scores`
  (vide depuis le 25/08, cf. `docs/AUDIT_2026_08.md` F1) qui faisait échouer les
  tier lists. Écrit `last_recompute_utc` dans `db_meta` (distinct de
  `last_update_utc`, puisque les données sources n'ont pas été rafraîchies).

## [Unreleased] - 2026-07-25

### 🗑️ Suppressions (audit de sur-ingénierie)

Passe de dé-complexification sur tout le dépôt : **-12 800 lignes, -10 dépendances**.
Aucun changement de comportement fonctionnel.

- **`server/` supprimé** (6 371 l.) — couche FastAPI + PostgreSQL/Neon décommissionnée
  depuis 7afb137 (« SQLite only »), plus aucun import depuis l'app. `analysis/scoring.py`,
  `analysis/team_analysis.py` et `models.py` y étaient byte-identiques à leurs jumeaux `src/`.
  - CI : jobs black/pylint/mypy/bandit/pytest dupliqués retirés
  - **-9 dépendances** : fastapi, uvicorn, gunicorn, sqlalchemy, asyncpg, pydantic,
    pydantic-settings, httpx, pytest-asyncio
- **Abstraction `DataSource` supprimée** (979 l.) — une seule implémentation,
  `SQLiteDataSource`, qui déléguait chaque méthode à `Database` sans logique.
  `Assistant(data_source=...)` devient `Assistant(db: Database | None)`.
- **`scripts/repair_matchups.py` + `repair_synergies.py` fusionnés** (1 182 → 620 l.) —
  ils étaient identiques à 93,4 %. Remplacés par `scripts/repair_data.py --target
  {matchups,synergies}`. ⚠️ **Changement d'invocation** — voir ci-dessous.
- **`src/error_ids.py` supprimé** (206 l. + 191 l. de tests) — Enum + dataclass + `.log()`
  pour préfixer un code au message, sans Sentry dans les dépendances et 5 codes sur 14
  jamais utilisés. Les codes `[ERR_*]` restent identiques dans les logs.
- **`numpy` retiré** (**-1 dépendance**, allège le bundle PyInstaller) — servait à
  `np.unique()` sur une liste littérale (→ `sorted({...})`) et à un `np.var()` qui avait
  déjà un repli manuel (→ `statistics.pvariance`).
- **`config.TierListConfig` supprimé** — dupliquait champ pour champ `AnalysisConfig`
  (mêmes noms, mêmes valeurs) ; les 8 `@property` de rétro-compatibilité aussi, dont 5
  sans aucun appelant. Les seuils vivent désormais uniquement dans `config_constants.py`.
- **Code mort supprimé** : 343 l. dans `src/ui/lol_coach_legacy.py` (doublon inatteignable
  de tout l'entry point, dont un `main()` de 156 l.), 9 délégateurs sans appelant dans
  `src/assistant.py`, 12 alias « legacy » dans `src/constants.py`, `Parser.contains()`
  (→ `row not in result`), `to_dict()` sur les dataclasses (→ `dataclasses.asdict`).
- **Scripts ad hoc supprimés** : `fill_db.py` (remplacé par `scripts/update_all.py`),
  `cleanup_db.py`, `test_parser_single.py`, `scripts/benchmark_cache.py`,
  `scripts/diagnose_synergies_html.py`, `scripts/test_synergies_xpath.py`.
- **Docs obsolètes supprimées** (1 935 l.) : NEON_READONLY_USER_GUIDE, OFFLINE_FIRST_PLAN,
  API_PERFORMANCE_ISSUES, DRAFT_SITES_INTEGRATION_RESEARCH, AUDIT_REPORT (remplacé par
  AUDIT_2026_06), github_actions_scraping, create_readonly_user_neon.sql.
- `create_package.py` : parcours `zipfile` manuel → `shutil.make_archive()`.
- `src/utils/display.py` : table de 26 substitutions emoji → ASCII remplacée par
  `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`.

### ⚠️ Breaking changes

- `python scripts/repair_matchups.py` → **`python scripts/repair_data.py --target matchups`**
- `python scripts/repair_synergies.py` → **`python scripts/repair_data.py --target synergies`**
  Les défauts `--headless` par cible sont conservés (matchups en GUI, synergies en headless)
  et `--firefox-profile` est désormais disponible pour les deux.
- `python fill_db.py` → **`python scripts/update_all.py`**
- `Assistant(data_source=...)` → **`Assistant(db=...)`**, qui attend un `Database`
  (et non plus un `DataSource`).

### 🐛 Connu

- `src/db.py::get_synergy_delta2()` utilise `fetchone()` et retourne une lane arbitraire,
  là où `get_matchup_delta2()` fait une moyenne pondérée par les games. Divergence
  préexistante héritée de l'implémentation `server/`, documentée par un test
  `xfail(strict=True)` dans `tests/test_regression_get_synergy_delta2.py`. **Non corrigée**
  ici : cette passe ne change aucun comportement d'analyse.

## [1.2.0] - 2026-02-11

### ✨ Features

- **NEW**: PostgreSQL Direct Mode for remote data access (PR #TBD)
  - **Problem**: API FastAPI timeout (60s+) on Render free tier, cannot play away from home without USB drive
  - **Solution**: Direct PostgreSQL Neon connection (no API intermediary)
    - Client .exe connects directly to PostgreSQL Neon cloud database
    - 3 data access modes: `sqlite_only` (default), `postgresql_only` (remote), `hybrid` (fallback)
    - ROT13 + Base64 obfuscation for connection string security
    - READ-ONLY PostgreSQL user (GRANT SELECT only, zero risk)
    - Latency: 100-300ms (vs 60s+ timeout API FastAPI)
  - **Architecture**: Eliminates API FastAPI + Render hosting (cost $0/month vs $21/month)
  - **Use cases**:
    - At home: `sqlite_only` (<10ms queries, maximum performance)
    - Gaming café / travel: `postgresql_only` (remote access to your data)
    - Unstable network: `hybrid` (try PostgreSQL, fallback SQLite)
  - **Files created**:
    - `src/credentials.py` - ROT13 + Base64 obfuscation module
    - `src/postgresql_data_source.py` - PostgreSQL adapter (DataSource interface)
    - `tests/test_credentials.py` - 9 unit tests (100% pass)
    - `tests/test_postgresql_data_source.py` - 12 unit tests (100% pass)
    - `tests/test_hybrid_data_source_e2e.py` - 9 E2E tests (skip if DATABASE_URL not set)
  - **Files modified**:
    - `src/hybrid_data_source.py` - Replaced APIDataSource with PostgreSQLDataSource
    - `requirements.txt` - Added sqlalchemy[asyncio], asyncpg, greenlet
    - `LeagueStatsCoach.spec` - Included asyncpg native binaries for PyInstaller
  - **Security**: READ-ONLY user, public data (LoL stats), obfuscated credentials (ROT13+Base64)
  - **Documentation**: README.md updated with 3 data modes + use cases

### 🗑️ Removed

- API FastAPI integration (APIDataSource replaced by PostgreSQLDataSource)
  - No longer uses Render hosting or API REST endpoints
  - Direct PostgreSQL connection reduces latency by 50-90%

## [Unreleased]

### 🐛 Fix — Pools Système dynamiques & homogénéisation lane (issue #41, 2026-07-23)

- **♻️ Refactor**: les pools Système (`All Top/Jungle/Mid/ADC/Support Champions`)
  ne sont plus des listes en dur dans `src/constants.py` — `PoolManager` les calcule
  désormais depuis la colonne `lane` déjà taguée en BD par le pipeline multi-lane
  (`src/lane_discovery.py`), rôle par rôle. Chaque rôle sans données BD retombe
  individuellement sur la liste `constants.py` correspondante (fresh install, tests,
  avant le premier scrape multi-lane)
- **♻️ Refactor**: `scripts/repair_matchups.py` et `scripts/repair_synergies.py`
  réutilisent désormais `discover_lanes_for_champions()` +
  `group_champions_by_lane()` (les mêmes fonctions que `scripts/update_all.py`) au
  lieu de scraper une lane par défaut non taguée pour les champions manquants —
  élimine la divergence de comportement entre les scripts de réparation et le
  pipeline nightly
- **🐛 Fix**: un champion joué sur plusieurs lanes (ex. Pyke top/support) n'efface
  plus les lignes de la première lane lors de la réparation — le nettoyage
  (`clear_matchups_for_champion`/`clear_synergies_for_champion`) n'a désormais lieu
  qu'une fois par champion, pas une fois par lane
- **✅ Test**: `tests/test_pool_manager_system_pools.py` (pools calculés depuis la BD
  + fallback par rôle) et `tests/test_repair_scripts_lane_handling.py` (découverte de
  lane, groupement, non-écrasement multi-lane)
- **🐛 Fix**: le menu principal (`src/ui/lol_coach_legacy.py`, option 3 « Parse Match
  Statistics ») taguait **toutes** les données scrapées pour un pool avec `lane="top"`
  en dur, quel que soit le rôle réel du pool sélectionné (ex. sélectionner « All Jungle
  Champions » taguait les matchups/synergies comme `top`) — et les options « All
  Champions » scrapaient une lane par défaut non taguée. Les 6 fonctions concernées
  (`parse_champion_pool`, `parse_all_champions`, `parse_synergies_pool`,
  `parse_synergies_all`, `parse_all_data_pool`, `parse_all_data_all`) passent
  désormais par le nouvel helper `_scrape_by_discovered_lane()`, qui réutilise
  `discover_lanes_for_champions()` + `group_champions_by_lane()` — même méthode que
  `scripts/update_all.py` et les scripts repair. Parité comportementale conservée
  (rafraîchissement Riot API, pré-calcul des bans) pour les variantes « All Champions »
- **✅ Test**: `tests/test_menu_lane_handling.py` — preuve de régression sur un pool
  Jungle/Support/ADC (le bug se reproduisait avant le fix : lane taguée `top`)

### 🟠 Horizon 2 — Dette technique 2.0 (2026-06-14)

Implémentation de `docs/ROADMAP_2026.md` §3 H2. **Chantier #1 — décommission de la
couche données distante** (Décisions B « outil personnel » + C « SQLite uniquement »,
tranchées le 2026-06-11).

- **🗑️ Removed**: couche données distante supprimée intégralement côté client —
  `src/api_data_source.py` (zombie post-1.2.0), `src/postgresql_data_source.py`,
  `src/hybrid_data_source.py`, `src/credentials.py` (la chaîne de connexion committée
  disparaît — règle le point sécurité de l'audit §6), `scripts/sync_local_to_neon.py`
  et le script admin Neon `scripts/test_readonly_permissions.py`
- **🗑️ Removed**: `APIConfig` / `api_config` (mode auto `sys.frozen` →
  `postgresql_only`/`sqlite_only`/`hybrid`) retiré de `src/config_constants.py` ;
  plus de bascule de mode selon le contexte d'exécution
- **♻️ Refactor**: `Assistant` ne dépend plus que de `SQLiteDataSource` (défaut quand
  aucune source n'est injectée) ; `SQLiteDataSource()` accepte désormais un chemin
  optionnel (défaut `config.DATABASE_PATH`)
- **🗑️ Removed**: appels de sync Neon dans `src/ui/lol_coach_legacy.py` (fonction
  `sync_to_neon()` + 6 sites d'appel) et bloc « sync Neon » + « refresh API Render »
  (`ADMIN_API_KEY`) de `scripts/auto_update_db.py`
- **🔧 Chore**: dépendances client allégées — `sqlalchemy[asyncio]`, `asyncpg`,
  `greenlet`, `httpx` retirées de `requirements.txt` (SQLAlchemy reste disponible via
  Alembic en dev) ; `LeagueStatsCoach.spec` ne collecte plus les binaires asyncpg/greenlet
- **✅ Test**: tests de l'ancienne couche supprimés (api/postgresql/hybrid/credentials/
  sync_local_to_neon/admin-refresh) ; `test_assistant_integration.py` et
  `test_regression_pool_warm_cache.py` recâblés sur `SQLiteDataSource` / le contrat
  générique `DataSource`. Suite : 512 tests verts
- **Note**: la suppression de `server/` et la fermeture de la base Neon (chantier #2)
  feront l'objet d'une PR distincte ; `tests/test_admin_endpoint.py` (couplé à `server/`)
  reste en place jusque-là

### 🔴 Horizon 1 — Pipeline de données fiable (2026-06-12)

Implémentation de `docs/ROADMAP_2026.md` §3 H1 : données complètes, fraîches,
multi-lane, sans intervention manuelle.

- **🗃️ Database**: migration Alembic `b7e41c9a3f02` — colonne `lane` (TEXT, nullable) sur
  `matchups`/`synergies` + index composites `(champion|enemy|ally, lane, pickrate)` +
  table `db_meta` (clé/valeur). Les lignes multi-lane sont enfin distinguables
  (fondation Tâche #15) ; migration testée upgrade+downgrade sur copie de la BD réelle
- **✨ Feature**: découverte dynamique des lanes (`src/lane_discovery.py`) — la répartition
  des lanes est extraite du HTML brut LoLalytics (SSR Qwik) en simple HTTP `requests`,
  sans Selenium ; seules les lanes à pickrate >10% sont scrapées
  (`LANE_PICKRATE_THRESHOLD`). Décision validée le 2026-06-12
- **✨ Feature**: orchestration multi-lane (`src/multilane.py`) — scrape matchups+synergies
  par groupe (lane, champions) avec tag `lane` en BD ; fallback lane par défaut (lane=NULL)
  si la découverte échoue pour un champion
- **✨ Feature**: `scripts/update_all.py` — successeur industrialisé de `fill_db.py` /
  `auto_update_db.py` : scrape multi-lane → gate de complétude → recalcul
  `champion_scores` → recalcul `pool_ban_recommendations` → métadonnées fraîcheur →
  notifications (toast Windows + webhook Discord). Patch depuis `config.CURRENT_PATCH`
  (fin du `PATCH = "14"` hardcodé), SQLite uniquement (plus de sync Neon — Décision C)
- **✅ Test**: gate de complétude volumétrique (`src/data_quality.py`) — échec bruyant
  (exit 1 + notification, fraîcheur non avancée) si la volumétrie est sous les seuils
  `DataQualityConfig` ; la perte silencieuse 40k→16k du 01/06 ne peut plus se reproduire
- **✨ Feature**: bandeau de fraîcheur au lancement de l'app (`src/data_freshness.py`) —
  âge des données + volumétrie à chaque affichage du menu, `[ALERTE]` si >7 jours
  (le garde-fou qui manquait quand l'auto-update est mort silencieusement le 19/03)
- **🔧 Chore**: `scripts/setup_auto_update.ps1` re-ciblé sur `update_all.py`
  (Task Scheduler quotidien)
- **📝 Docs**: `docs/runbook_scraping.md` — diagnostic DOM, sélecteurs à vérifier,
  recalibration des seuils, marche à suivre si Cloudflare réapparaît

### 🚨 Horizon 0 — Stabilisation (2026-06-12)

Voir `docs/AUDIT_2026_06.md` et `docs/ROADMAP_2026.md` (décisions stratégiques A/B/C tranchées le 2026-06-11).

- **🐛 Fix**: `CloudflareException` était avalée par le `except Exception` générique dans
  `parallel_parser.py` (matchups et synergies) — elle est maintenant dans le tuple
  `retry_if_exception_type` et re-levée (le test de régression passe à nouveau)
- **🐛 Fix**: `Assistant.draft()` défini deux fois (pylint E0102 faisait échouer la CI) —
  suppression du stub mort masqué, comportement runtime inchangé
- **🐛 Fix**: test `sync_local_to_neon` hermétique — `SYNC_SKIP_DOTENV=1` empêche le script
  de recharger `DATABASE_URL` depuis `server/.env` (et de lancer une vraie sync Neon en plein test)
- **🔧 Chore**: suppression de `.github/workflows/scraping.yml` (cancelled à 2h chaque nuit,
  ~60h de minutes Actions/mois gaspillées, destinataire Neon abandonné — Décision C)
- **🔧 Chore**: jobs `build` et `performance` de la CI ciblent `refs/heads/master`
  (le build n'avait **jamais** tourné : il visait `main`/`inspiring-rhodes`)
- **🔧 Chore**: `fill_db.log` écrit dans `logs/` au lieu de la racine
- **🎨 Style**: Black appliqué aux 3 fichiers laissés non formatés par le rewrite du 01/06
  (`src/parser.py` faisait échouer le job quality)
- **🗃️ Data**: `champion_scores` (172/172) et `pool_ban_recommendations` (3 pools custom)
  recalculés sur les données du 2026-06-01
- **🔀 Git**: branche `feature/playwright-migration` archivée (tag `archive/playwright-migration`)
  puis supprimée — chantier annulé, Cloudflare a retiré son challenge (Décision A)

### 🐛 Fixes

- **CRITICAL**: Fixed auto-update scraping failure in Task Scheduler (PR #TBD)
  - **Root cause**: `pythonw.exe` (Task Scheduler) cannot launch GUI Firefox windows
  - **Impact**: Auto-update was deleting database (DROP TABLE matchups) without scraping new data
  - **Logs showed**: `0/172 champions succeeded, 172 failed` daily since 2025-12-23
  - **Solution**: Implemented headless mode for Firefox WebDriver
    - Added `headless` parameter to `Parser` class (default: False)
    - Added `headless` parameter to `ParallelParser` class (default: False)
    - Set `headless=True` in `scripts/auto_update_db.py` for Task Scheduler execution
    - Firefox now runs with `--headless` flag in background mode (no GUI)
    - All DOM operations (clicks, scrolls, scraping) work identically in headless
  - **Backward compatible**: Manual scraping still uses GUI mode (headless=False)
  - **Enhanced logging**:
    - Added failure rate calculation and warnings
    - Full traceback for first scraping failure (debugging aid)
    - Exception type included in error messages

### ✨ Features

- **NEW**: Automated log rotation system (PR #TBD)
  - **Problem**: `auto_update.log` grows to 1+ GB, no automatic cleanup
  - **Solution**: PowerShell scripts for automated log management
    - `scripts/rotate_logs.ps1` - Rotate logs when exceeding size threshold (default: 50 MB)
    - `scripts/setup_log_rotation.ps1` - Task Scheduler setup wizard
    - Archives old logs with timestamp: `auto_update_YYYYMMDD_HHMMSS.log`
    - Optional compression to `.zip` format (~80% space savings)
    - Keeps configurable number of backups (default: 5)
    - Automatic cleanup of old backups
    - Detailed logging to `logs/log_rotation.log`
  - **Default schedule**: Weekly on Sunday at 2:00 AM (before auto-update at 3:00 AM)
  - **Documentation**: `docs/LOG_ROTATION.md` with setup guide and FAQ

### 🔧 Changed

- `src/parser.py`: Added `headless` parameter + viewport size control (41 lines modified)
  - Force 1920x1080 resolution in headless mode (matches GUI fullscreen)
  - Skip coordinate-based cookie fallback in headless (DOM-only strategies)
- `src/parallel_parser.py`: Propagate `headless` to Parser instances (8 lines modified)
- `scripts/auto_update_db.py`: Multiple improvements (50+ lines modified)
  - Enable headless mode for Task Scheduler compatibility
  - Enhanced error reporting with failure rate calculation
  - Configured Python logging to capture all logs in file (pythonw.exe compatible)
  - Reduced log verbosity: Selenium/urllib3 set to WARNING (was DEBUG)
  - 95% reduction in log file size while keeping useful diagnostics

### 📊 Impact

- **Auto-update reliability**: ✅ **VALIDATED - 172/172 champions succeeded in 16.6 minutes**
  - Before: 0/172 succeeded (100% failure rate since 2025-12-23)
  - After: 172/172 succeeded (100% success rate)
  - Root cause fixed: Headless viewport + cookie banner compatibility
- **Task Scheduler compatibility**: Now works correctly with pythonw.exe (no GUI required)
- **Data integrity**: Database no longer left empty after failed updates
- **Log management**: Automatic rotation prevents disk space exhaustion
  - Before: 1+ GB log files, manual cleanup required
  - After: 50 MB max (configurable), automatic cleanup
- **Backward compatibility**: 100% - existing code works without changes
  - Manual scraping still uses GUI mode (headless=False by default)

### ✅ Validation

Tested with `pythonw.exe` (Task Scheduler environment):

**Before Fix (2025-12-29 16:32 - Headless viewport issue)**:
```
[2025-12-29 16:32:11] INFO: Champions parsed: 0/172 succeeded, 172 failed ❌
[2025-12-29 16:32:11] WARNING: Failure rate: 100.0%
[2025-12-29 16:32:11] ERROR: Move target (1661, 853) out of bounds (1366x683)
```

**After Fix (2025-12-29 17:05 - 1920x1080 + skip coordinates)**:
```
[2025-12-29 17:05:23] INFO: Scraping completed: 172/172 succeeded, 0 failed ✅
[2025-12-29 17:05:23] INFO: Duration: 16.6 minutes (995.9 seconds)
[2025-12-29 17:05:23] SUCCESS: Auto-update completed successfully
```

## [1.1.0] - 2025-12-29

**🎉 RELEASE MAJEURE - Sprints 1 & 2 Complétés**

Cette version marque la complétion de deux sprints majeurs axés sur la dette technique, la performance et les fonctionnalités essentielles. Le projet dispose désormais d'une base solide, testée et performante.

### ⚡ Performance

- **MAJOR**: Parallel web scraping implementation (PR #5)
  - **87% performance improvement** - Data updates now take 12 minutes instead of 90-120 minutes
  - ThreadPoolExecutor with 10 concurrent workers (optimized for i5-14600KF)
  - Automatic retry mechanism with exponential backoff (tenacity)
  - Thread-safe database operations with proper locking
  - Real-time progress tracking with tqdm progress bars
  - Komorebi window manager integration with fullscreen mode
  - Dynamic cookie acceptance (fixes hardcoded coordinates bug)
- **MAJOR**: Pre-calculated ban recommendations system (PR #19)
  - **Instant ban suggestions** during draft - no more 5-10 second calculation delays
  - Database-backed storage of ban recommendations for all custom pools
  - Automatic updates during data parsing (both manual and auto-update)
  - Fallback to real-time calculation if pre-calculated data unavailable
  - Optimized for pools of 10-20 champions (typical custom pools)
  - System pools excluded (too large for meaningful ban calculations)
- **Live Coach cache system** for instant draft recommendations
  - Warm cache at draft start eliminates SQL queries during picks (99% faster)
  - In-memory storage of all champion matchups from selected pool
  - Cache statistics tracking (hits/misses) for performance monitoring
  - Automatic cache clear on draft exit to free memory

### ✨ Features

- **MAJOR**: Proactive Draft Start UX (PR #19)
  - **Immediate strategy display** - Best blind pick + ban recommendations shown at game start
  - **No waiting** - Information appears before ban/pick phases begin
  - **Clear guidance** - "If you're first pick, this is your safest choice!"
  - **Adaptive recommendations** - Updates dynamically when enemy picks appear
  - **Better preparation** - Players can plan strategy from the very start
- **MAJOR**: Auto-Update Database system (Tâche #11, PR #14)
  - **Automated daily updates** via Windows Task Scheduler (3 AM default)
  - **Background execution** with BELOW_NORMAL priority (no PC blocking)
  - **12-minute updates** using ParallelParser (10 workers)
  - **Windows notifications** on success/failure (win10toast)
  - **Detailed logging** to `logs/auto_update.log`
  - **PowerShell setup wizard** (`setup_auto_update.ps1`)
  - **Dry-run test script** (`test_auto_update.py`)
  - **Zero manual maintenance** - Always up-to-date database
- **MAJOR**: Restored 24 missing Assistant methods from refactoring (+902 lines)
  - 7 draft & competitive methods: `draft()`, `competitive_draft()`, `blind_pick()`, etc.
  - 14 holistic trio analysis methods: `find_optimal_trios_holistic()`, `_evaluate_trio_holistic()`, etc.
  - 3 ban recommendation methods: `get_ban_recommendations()` with reverse lookup strategy
  - All methods updated to use dynamic DB queries instead of hardcoded CHAMPIONS_LIST
- **Live podium display** during optimal duo/trio optimization
  - Real-time updates every 50 evaluations
  - Top 3 rankings with medals (🥇🥈🥉)
  - Progress bar with percentage and viable count
  - ANSI escape codes for in-place terminal updates
- **Pool Statistics Viewer** (Tâche #5, PR #TBD)
  - **Comprehensive statistical analysis** for champion pools
  - **Distribution metrics**: mean, median, min, max, standard deviation, variance
  - **Coverage analysis**: champions with/without sufficient data, percentage
  - **Outlier detection**: champions with insufficient matchup data
  - **Performance rankings**: Top 5 and Bottom 5 performers by avg_delta2
  - **Integrated into Pool Manager** as Menu option 8
  - **15 unit tests** with 100% pass rate
- **New champions support**: Zaahen (TOP), Yunara (ADC)
- **Bidirectional advantage calculation** in draft coach (Tâche #TBD, PR #TBD)
  - **More accurate predictions** accounting for matchup asymmetry
  - Combines two perspectives: our advantage vs their advantage
  - Formula: `net_advantage = our_advantage - enemy_advantage_against_us`
    - Our advantage accounts for all 5 enemy slots (blind picks use avg_delta2)
    - Enemy advantage only includes enemies with reverse matchup data
    - Asymmetric calculation: weighted avg (ours) vs simple mean (theirs)
  - Handles asymmetric delta2 (e.g., Aatrox vs Darius ≠ Darius vs Aatrox)
  - Graceful degradation when enemy data missing (treats as neutral)
  - **Performance**: +1-5 database queries per enemy (<10ms total overhead)
  - **12 unit tests** with 100% pass rate (4 new tests for edge cases)
  - **Zero breaking changes** - seamlessly integrated into existing scoring
  - **Enhanced error handling** - Always logs DB errors, improved visibility

### 🐛 Fixes

- **CRITICAL**: Fixed live coach performance and UX issues (PR #TBD)
  - **Ban recommendations spam**: Now show ONLY during ban phase (before any picks)
    - Root cause: Phase name "BAN_PICK" contains "BAN" → rewrote `_is_ban_phase()` to check picks count
    - Impact: Clean draft experience, no more spam on every pick
  - **Wrong advice during picks**: Dynamic advice detection based on game state
    - Before: Always showed "[BAN]" advice during "BAN_PICK" phase
    - After: Shows "[BAN]" only when 0 picks, "[PICK]" when picks > 0
  - **Duplicate DB queries**: Removed redundant `get_champion_matchups()` calls in final analysis
    - Impact: 2x faster final team analysis
  - Added debug logging for troubleshooting (verbose mode support)
  - All 113 tests pass ✅

- Fixed `get_ban_recommendations()` AttributeError (method was lost during Sprint 1 refactoring)
- Fixed missing draft and holistic trio analysis methods (24 methods restored)
- Removed debug logging from optimal duo finder for cleaner output
- Fixed CHAMPIONS_LIST dependency by using dynamic `db.get_all_champion_names().values()`

### 📦 Added

- `scripts/auto_update_db.py` - Automated database update script (260 lines)
- `scripts/setup_auto_update.ps1` - Task Scheduler setup wizard (202 lines)
- `scripts/test_auto_update.py` - Dry-run test script (204 lines)
- `docs/AUTO_UPDATE_SETUP.md` - Complete setup guide (397 lines)
- `src/parallel_parser.py` - Parallel web scraping with ThreadPoolExecutor (389 lines)
- `src/analysis/pool_statistics.py` - Pool statistics calculator and formatter (271 lines)
- Live podium display method in `src/assistant.py` (36 lines)
- 24 restored methods in `src/assistant.py` (+902 lines total)
- `tests/test_pool_statistics.py` - Unit tests for pool statistics (376 lines, 15 tests)
- `win10toast>=0.9` dependency for Windows notifications

### 🔧 Changed

- `src/assistant.py`: Added `Dict` to type imports
- `src/assistant.py`: Refactored `_find_optimal_counterpick_duo()` to use live podium (117 lines)
- `src/assistant.py`: Updated all methods to use dynamic DB queries instead of hardcoded constants
- `src/ui/lol_coach_legacy.py`: Enhanced `show_pool_statistics()` with submenu for global vs individual analysis
- `src/constants.py`: Added Zaahen and Yunara champion entries
- `main.py`: Added `parse_all_champions_parallel()` and `parse_champions_by_role_parallel()` functions

### 📊 Impact

- **Automation**: Zero manual database maintenance (runs daily automatically)
- **Performance**: 87% faster data updates (12min vs 90-120min)
- **Completeness**: 54 total Assistant methods (vs 30 before restoration)
- **User Experience**: Live progress tracking, real-time podium, notifications
- **Reliability**: Automatic retries, thread-safe operations, background execution
- **Compatibility**: 100% backward compatible, all methods functional

### 🧪 Testing

- Auto-update script successfully tested with 172 champions
- Task Scheduler integration verified (3 AM daily execution)
- Dry-run test script validates all components
- Manual testing of parallel scraping with 10 workers
- Verification of all 24 restored methods accessibility
- Performance benchmarking: 12min for full champion pool (172 champions)
- Thread-safety validation with concurrent database writes
- **Pool statistics**: 15 unit tests with 100% pass rate (113 total project tests)

---

## [1.1.0] - 2025-12-14

### ♻️ Refactoring

- **MAJOR**: Dataclass migration for improved code readability (Tâche #14, PR #22)
  - **Objective**: Replace obscure tuple indexing (`m[3]`, `m[5]`) with readable object attributes (`m.delta2`, `m.games`)
  - **Impact**: 6 modules migrated (src/analysis/ + assistant.py) + tests backward compat
  - **Modules migrated**:
    - `src/models.py` - Created 3 immutable dataclasses (Matchup, MatchupDraft, ChampionScore) with validation
    - `src/db.py` - Added `as_dataclass` parameter for backward compatibility + bulk matchup loading
    - `src/analysis/scoring.py` - Migrated 9 tuple accesses to dataclass attributes
    - `src/analysis/tier_list.py` - Migrated 2 tuple accesses
    - `src/analysis/recommendations.py` - Migrated 2 tuple accesses
    - `src/analysis/pool_statistics.py` - Migrated 1 tuple access + method signature
    - `src/assistant.py` - Migrated 47 tuple accesses + 9 unpacking loops + holistic optimizer cache
    - `src/champion_utils.py` - Migrated to dataclass attributes
    - `src/draft_monitor.py` - Migrated to dataclass attributes
  - **Benefits**:
    - Type safety: Full IDE autocomplete and type checking
    - Readability: `m.delta2` instead of `m[3]`, `m.games` instead of `m[5]`
    - Immutability: Frozen dataclasses (`frozen=True`) = thread-safe, prevents accidental mutations
    - Validation: `__post_init__` with automatic data validation (winrate 0-100, etc.)
    - Backward compatible: 100% of existing code works without changes
  - **Tests**:
    - All tests passing (89% coverage maintained)
    - New: `tests/test_models.py` (389 lines) - Comprehensive dataclass tests
    - New: `tests/test_db_dataclass_migration.py` (139 lines) - Backward compatibility tests
  - **Performance**: Zero runtime impact (dataclasses compile to same bytecode as tuples)
- **MAJOR**: Holistic Optimizer performance boost (PR #22)
  - **99.5% speedup**: 1h06 (4,290s) → 20 seconds for 286 trio evaluations
  - **Throughput**: 15 sec/trio → 14 trios/sec
  - **Root cause**: N+1 query problem - 147,672 SQL queries (286 trios × 172 enemies × 3 champions)
  - **Solution**: Matchup cache in memory
    - New method: `Database.get_all_matchups_bulk()` - Single SQL query loads all matchups
    - Cache preloading before trio evaluation
    - O(1) dictionary lookups instead of SQL queries with JOINs
  - **Impact**: Holistic optimizer now usable in production (20s vs 1h06)
  - **Bonus**: Fixed redundant index creation messages (only show when actually creating)
- **MAJOR**: Refactored monolithic files into modular architecture (PR #2)
  - `assistant.py`: 2,381 → 190 lines (-92%)
  - `lol_coach.py`: 2,159 → 215 lines (-90%)
  - Created 9 new modules organized into `analysis/`, `ui/`, and `utils/`
  - Largest file reduced from 2,381 → 220 lines (-91%)

### 📦 Added

- **Analysis modules**:
  - `src/analysis/scoring.py` - Champion scoring algorithms (216 lines)
  - `src/analysis/tier_list.py` - Tier list generation (91 lines)
  - `src/analysis/recommendations.py` - Draft recommendations (116 lines)
  - `src/analysis/team_analysis.py` - Team composition analysis (129 lines)
- **Utils modules**:
  - `src/utils/display.py` - Emoji fallback for Windows terminals (30 lines)
  - `src/utils/champion_utils.py` - Champion validation/selection (220 lines)
- **UI modules**:
  - `src/ui/menu_system.py` - Main menu system (45 lines)
  - `src/ui/champion_data_ui.py` - Champion data management (105 lines)
  - `src/ui/draft_coach_ui.py` - Real-time draft coach UI (52 lines)
  - `src/ui/lol_coach_legacy.py` - Legacy UI functions (temporary)

### 🔧 Changed

- `src/assistant.py` - Replaced monolithic class with delegation pattern
- `lol_coach.py` - Replaced with minimal entry point delegating to UI modules
- `src/draft_monitor.py` - Fixed import for `safe_print` from utils.display

### 🐛 Fixed

- Type hint for `open_onetricks` parameter (str → Optional[bool])

### 📊 Impact

- **Maintainability**: Code now organized in focused modules (<500 lines each)
- **Testing**: Easier to write unit tests for isolated components
- **Onboarding**: Clearer code structure for new contributors
- **Foundation**: Clean base for future features and refactoring
- **Compatibility**: 100% backward compatible, all tests pass

---

## [1.0.1] - 2025-11-27

### 🔒 Security

- **CRITICAL**: Fixed SQL injection vulnerabilities in 6 database query methods
  - `get_champion_id()` - Line 86
  - `get_champion_by_id()` - Line 98
  - `get_champion_matchups()` - Line 110
  - `get_champion_matchups_by_name()` - Line 128
  - `add_matchup()` - Line 80
  - `init_champion_table()` - Line 43
- All SQL queries now use parameterized queries with `?` placeholders

### ⚡ Performance

- Added 6 database indexes for optimized query performance
  - `idx_champions_name` - Champion name lookups (50-80% faster)
  - `idx_matchups_champion` - Champion ID queries
  - `idx_matchups_enemy` - Enemy ID queries
  - `idx_matchups_pickrate` - Pickrate filtering
  - `idx_matchups_champion_pickrate` - Composite index for common queries
  - `idx_matchups_enemy_pickrate` - Composite index for reverse lookups
- Indexes are automatically created on database connection
- Expected performance improvement: 50-80% on name lookups, 60-90% on filtered matchup queries

### 📦 Added

- `requirements.txt` - Production dependencies with version pinning
- `requirements-dev.txt` - Development dependencies including PyInstaller
- `test_db_fixes.py` - Test suite for SQL injection fixes and index creation
- `SECURITY_FIXES.md` - Detailed documentation of security and performance fixes
- `CHANGELOG.md` - This file

### 🔧 Changed

- `src/db.py`:
  - Added `create_database_indexes()` method
  - Modified `connect()` to auto-create indexes
  - Modified `init_matchups_table()` to create indexes after table creation
  - Fixed all vulnerable SQL queries to use parameterized queries
- `README.md`:
  - Updated installation instructions to use `requirements.txt`
  - Added "Recent Updates" section with version 1.0.1 changes
  - Updated version number

### 🧪 Testing

- All tests pass successfully
- SQL injection prevention verified with special character handling
- Database index creation verified with automated tests

### 📊 Impact

- **Security**: Eliminated all SQL injection vulnerabilities
- **Performance**: 50-90% improvement on database queries
- **Maintainability**: Better dependency management with requirements files
- **Testing**: Automated test suite for critical functionality

---

## [1.0.0] - 2025-11-26

### Added

- Initial standalone release
- Real-time draft coach with LCU integration
- Champion pool management
- Team builder and optimization tools
- Database with 171 champions and 36,000+ matchups
- Portable executable distribution
- Documentation and build tools

---

**Legend:**
- 🔒 Security fixes
- ⚡ Performance improvements
- 📦 New features/files
- 🔧 Changes to existing functionality
- 🧪 Testing improvements
- 📊 Metrics and analysis
