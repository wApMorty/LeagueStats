# SPEC-37 — Écran « Données » : actualiser la base depuis le client

**Statut** : ✅ Livrée le 2026-10-20 (tâches 181 à 186) ; recette réelle de @pj35 à faire (§6, vérification de bout en bout).

**Origine** : @pj35, 2026-10-20 — « Il manque un bouton/écran pour gérer le parsing des données depuis le GUI. Une
page avec bouton "Actualiser" et état d'avancement (lane par lane, jauge 43/67 et champion en cours) semblerait
adaptée. »

**Effort** : ~2,5 jours, 6 tâches (§5).

---

## 1. Constat

Mesuré le 2026-10-20 sur le code et sur `data/db.db`, pendant un scrape lancé en ligne de commande à 09:28.

- **Le client n'a aucune entrée vers la mise à jour.** Aucune route de `src/client/app.py` n'appelle le pipeline
  (`grep -i "pipeline\|scrap" src/client` : rien). La mise à jour passe par le menu console 3
  (`src/ui/data_update_ui.py:128`) ou `python scripts/update_all.py`, deux appelants du même `run_pipeline()`
  (`src/pipeline.py:205`).
- **Durée réelle : 1 h 40.** `logs/update_all.log`, run du 2026-10-06 : 108,8 min, plan de 343 pages
  `{'top': 90, 'jungle': 68, 'middle': 77, 'bottom': 48, 'support': 60}`, de 17,5 à 26,6 min par lane. Le run du
  2026-10-20 planifie 347 pages (`top` 92, `jungle` 68, `middle` 78, `bottom` 48, `support` 61).
- **Les lanes passent l'une après l'autre, les champions d'une lane en parallèle.** `scrape_all_multilane`
  boucle sur les groupes de lane (`src/multilane.py:145`) ; `parse_page_by_role` soumet les champions de la lane à
  un `ThreadPoolExecutor` de `DEFAULT_MAX_WORKERS` = 5 fils (`src/config_constants.py:68`) et suit l'avancement par
  `tqdm` (`src/parallel_parser_roles.py:387` et `:415`). Plusieurs champions sont donc « en cours » à la fois.
  Avant les lanes : sauvegarde, API Riot, découverte des lanes (~1 min). Après : scores, bans, shrink, réparation
  ciblée éventuelle (~2 min).
- **Pendant le scrape, la base est vide.** `init_matchups_table` fait `DROP TABLE` (`src/repositories/matchups.py:32`,
  idem `synergies.py:35`). Relevé à 09:31 pendant le run en cours : 681 matchups, 579 synergies, 0 ligne dans
  `champion_scores` (57 612 matchups au run précédent, `db_meta.matchups_count`). Une draft pendant ces 1 h 40
  reçoit des recommandations sur une base vide.
- **Deux runs simultanés ne sont pas empêchés.** Aucun verrou dans `run_pipeline` : un run du client lancé pendant
  celui de la console referait le `DROP` au milieu de l'autre.
- **L'interruption sait déjà restaurer.** `KeyboardInterrupt` restaure la sauvegarde d'avant le scrape
  (`src/pipeline.py:438`) ; un fil du client ne reçoit pas de Ctrl+C, il lui faut son propre signal d'arrêt.
- **`_setup_logging()` vide les handlers du logger racine** (`src/pipeline.py:64`) : appelé dans le processus du
  client, il redirigerait tout le logging du client vers `logs/update_all.log` pour la suite de la session.
- **Le résumé du dernier passage existe à moitié.** `db_meta` porte `last_scrape_utc`, `last_scrape_status`,
  `matchups_count`, `synergies_count` (lus par `get_freshness_info`, `src/data_freshness.py`) ; le détail par lane
  n'est que dans le log.
- **La phase du client LoL est connue du serveur** : `bus.latest("phase")["kind"]` vaut `draft` en sélection des
  champions et `game` en partie (`src/draft/phase_tracker.py:26`, `src/config_constants.py:429`).

## 2. Objectif et arbitrages

Lancer la mise à jour des données depuis le client et en suivre l'avancement lane par lane, sans jamais laisser la
base vidée par une fermeture, un double lancement ou une draft en cours.

| Sujet | Décision |
|---|---|
| Où tourne la mise à jour | **Validé (@pj35, 2026-10-20)** : fil daemon dans le processus du client, `run_pipeline` appelé tel quel avec un rappel de progression et un signal d'arrêt. Marche dans l'exe sans drapeau ni sous-processus. |
| Draft ou partie en cours | **Validé (@pj35, 2026-10-20)** : « Actualiser » grisé en phase `draft` et `game`, avec la raison ; refus aussi côté serveur (409). Une mise à jour lancée avant continue ; l'écran Draft affiche alors un bandeau « Données en cours de mise à jour ». |
| Contenu de l'écran | **Validé (@pj35, 2026-10-20)** : bouton « Actualiser », étape courante, une jauge par lane (`43/67`, échecs), champions en cours, temps écoulé, **temps restant estimé**, **résumé du dernier passage** (date, statut, volumes, bilan par lane). Pas de bouton « Arrêter » ni de « Recalcul seul ». |
| Navigation | **Validé (@pj35, 2026-10-20)** : entrée « Données » dans le groupe Coaching, après Calibration. |
| Double lancement (client et console) | **Validé (@pj35, 2026-10-20)** : verrou `data/update.lock` contenant le PID, posé et levé par `run_pipeline` ; un run refuse de démarrer si ce PID vit encore (`psutil`, déjà en dépendance). Vaut pour la console comme pour le client. |
| Fermeture de la fenêtre en cours de mise à jour | **Validé (@pj35, 2026-10-20)** : dialogue de confirmation ; « oui » arrête proprement (pages en cours terminées), restaure la sauvegarde d'avant le scrape, puis ferme. |

## 3. Approches considérées

1. **Fil dans le client, progression en mémoire, page relue par htmx (retenue).** `run_pipeline` reçoit
   `progress` et `stop` ; un objet `UpdateJob` du client tient l'état et le fragment de la page se relit toutes les
   2 s tant qu'un run tourne (`hx-trigger="every 2s"`). Un seul chemin d'appel, aucun format de fichier, rien à
   ajouter à l'exe. Prix : la fermeture de la fenêtre doit être gardée (§4.5).
2. **Sous-processus `update_all.py` et fichier de progression.** Survit à la fermeture, mais l'exe n'a pas
   d'interpréteur : il faudrait un drapeau `--update` dans `lol_coach.py`, un fichier JSON de progression écrit par
   le pipeline et relu par le client, et deux processus à surveiller. Écartée par @pj35.
3. **Progression par le bus et SSE** (comme l'écran Draft). Écartée : un rafraîchissement toutes les 2 s suffit à
   une tâche de 1 h 40, et le polling htmx n'ajoute ni sujet de bus ni script.

## 4. Détail

### 4.1 Progression et arrêt dans le pipeline (`src/parallel_parser_roles.py`, `src/multilane.py`, `src/pipeline.py`)

Un seul type de rappel, `Progress = Callable[[dict], None]`, défini dans `src/pipeline.py` et transmis vers le bas.
*Livré dans `src/progress.py` avec `PipelineCancelled` et `emit` : les placer dans `pipeline.py` ou `multilane.py`
fermait un cycle d'imports avec `parallel_parser_roles.py`.*
Chaque appel est enveloppé par `_emit(progress, event)` (dans `src/multilane.py`, importé par le parser) qui avale
toute exception : la progression ne doit jamais faire échouer un scrape.

Événements (dictionnaires, clé `step`) :

| `step` | Émis par | Autres clés |
|---|---|---|
| `"preparation"` | `run_pipeline` puis `scrape_all_multilane` | `detail` : `"Sauvegarde"`, `"Champions (API Riot)"`, `"Découverte des lanes"` |
| `"plan"` | `scrape_all_multilane`, après `group_champions_by_lane` | `lanes` : `{lane_label: nb_champions}` dans l'ordre de scrape (`lane or "default"`) |
| `"start"` | `parse_page_by_role`, dans le fil de travail, avant `get_champion_page_data` | `lane`, `champion` |
| `"done"` | `parse_page_by_role`, dans la boucle `as_completed` | `lane`, `champion`, `ok` (bool : matchups écrits) |
| `"recalcul"` | `run_pipeline`, avant `calculate_global_scores` | — |
| `"reparation"` | `run_pipeline`, avant `_repair_incomplete_champions` | — |

Signatures :

```python
def parse_page_by_role(self, db, champion_list, lane, normalize_func, include_matchups=True,
                       include_synergies=True, init_tables=False,
                       progress: Optional[Progress] = None,
                       stop: Optional[threading.Event] = None) -> dict
def scrape_all_multilane(db, parser, normalize_func, champions=None, include_matchups=True,
                         include_synergies=True, progress=None, stop=None) -> dict
def run_pipeline(..., progress: Optional[Progress] = None,
                 stop: Optional[threading.Event] = None) -> PipelineResult
```

Arrêt : nouvelle exception `PipelineCancelled(Exception)` dans `src/pipeline.py`. `parse_page_by_role` teste
`stop.is_set()` à chaque tour de `as_completed` : si oui, `future.cancel()` sur les tâches non démarrées, sortie de
boucle, `raise PipelineCancelled`. `scrape_all_multilane` le teste aussi avant chaque lane. `run_pipeline` attrape
`PipelineCancelled` dans la même branche que `KeyboardInterrupt` (restauration de la sauvegarde, notification
« Interrompu », `status="failed"`, `error="Interrompu"`). Le `tqdm` existant reste (console).

Bilan par lane : après le scrape, `run_pipeline` écrit `db_meta.last_scrape_lanes`, JSON
`{lane_label: {"success": n, "failed": n, "total": n, "duration_s": s}}` tiré de `stats["matchups"]` (ou
`stats["synergies"]` si matchups exclus), à côté de `last_scrape_utc` (`src/pipeline.py:301`).

### 4.2 Verrou de run (`src/pipeline.py`)

`run_pipeline` pose le verrou avant la sauvegarde, y compris en `recompute_only` (le recalcul fait aussi des `DROP`) :

```python
def _acquire_lock(path: Path) -> Optional[int]:
    """Pose le verrou ; renvoie le PID du run vivant qui le tient déjà, sinon None."""
def _release_lock(path: Path) -> None
```

Fichier `data/update.lock` (constante `UPDATE_LOCK_FILE` dans `data_quality_config`, `src/config_constants.py`),
contenu : le PID. Verrou tenu par un PID mort (`psutil.pid_exists` faux) ou fichier illisible : écrasé. Verrou tenu :
`run_pipeline` renvoie `PipelineResult(status="failed", error="Mise à jour déjà en cours (PID n)")` sans rien
toucher. Levée dans le `finally` existant. La fixture autouse `_isolate_logs` (`tests/conftest.py:45`) redirige aussi le chemin
du verrou vers `tmp_path` : jamais `data/update.lock` réel.

### 4.3 Tâche de mise à jour du client (`src/client/donnees.py`, nouveau)

```python
class UpdateJob:
    """Une mise à jour à la fois, dans un fil daemon ; état lu par l'écran Données."""
    def __init__(self, run: Callable[..., PipelineResult] = run_pipeline,
                 clock: Callable[[], float] = time.monotonic) -> None
    def start(self) -> Optional[str]      # None si lancé, sinon la raison du refus (« déjà en cours »)
    @property
    def running(self) -> bool
    def snapshot(self) -> dict            # copie sous verrou, voir ci-dessous
    def cancel(self, timeout: float) -> bool  # pose `stop`, attend la fin du fil ; True si fini à temps
```

- `start` lance `run(progress=self._on_progress, stop=self._stop)` dans un fil daemon `donnees-update`. Avant
  l'appel, le fil sauve `logging.getLogger().handlers` et le niveau, et les remet dans un `finally` (§1, logging du
  client intact).
- `snapshot()` : `{"state": "idle"|"running"|"ok"|"partial"|"failed", "step": str, "lanes": [{"lane", "done",
  "total", "failed", "current": [champions triés]}], "started_at": float, "elapsed_s": float, "eta_s":
  Optional[float], "error": Optional[str], "report": str}`. `current` = champions reçus en `start` et pas encore en
  `done`.
- **Temps restant** : `eta_s = pages_restantes × (temps écoulé depuis l'événement plan / pages faites)`, `None` sous
  `DONNEES_ETA_MIN_PAGES` pages faites. Approximation assumée : pas de terme pour le recalcul final (~2 min).
- Fonction pure de vue : `donnees_view(snapshot: dict, freshness: FreshnessInfo, last_lanes: dict, phase_kind: str,
  now: datetime) -> dict` (libellés français, `ago()` et `thousands()` de `src/client/data.py`, raison du bouton
  grisé : phase `draft` ou `game`, run en cours). `last_lanes` est lu de `db_meta.last_scrape_lanes` (JSON invalide
  ou absent : `{}`).

Constantes dans `src/config_client.py` (`ClientConfig`) :

| Constante | Valeur | Origine |
|---|---|---|
| `DONNEES_POLL_S` | 2 | Une page se termine toutes les ~12 s (1 079 s pour 90 pages à 5 fils, log du 2026-10-06, soit ~60 s par page et par fil) : 2 s montre chaque champion qui passe. |
| `DONNEES_ETA_MIN_PAGES` | 5 | Une estimation sur moins d'une page par fil n'a pas de sens. |
| `DONNEES_CLOSE_TIMEOUT_S` | 240 | Pages en cours à terminer (~60 s par page et par fil, plus les nouveaux essais) puis copie de la sauvegarde. |

### 4.4 Écran Données (`src/client/app.py`, gabarits, CSS)

- `create_app(..., update_job: Optional[UpdateJob] = None)` ; absent (tests, mode démo), un `UpdateJob()` est créé.
  Passé par `server.start(..., update_job=...)` depuis `launch.py`.
- `NAV` : `NavItem("donnees", "Données", "ᛚ", 205, "/donnees")` dans le groupe Coaching, après Calibration.
- Routes :
  - `GET /donnees` : page complète (`templates/donnees.html`) qui inclut le fragment.
  - `GET /donnees/etat` : fragment `templates/partials/donnees_etat.html`. Tant que `state == "running"`, la racine
    du fragment porte `hx-get="/donnees/etat" hx-trigger="every {{ poll }}s" hx-swap="outerHTML"` ; sinon pas de
    polling.
  - `POST /donnees/actualiser` : refus 409 avec la raison si phase `draft` ou `game` ou `job.start()` refuse (run
    du client ou verrou d'un autre processus, lu par `_acquire_lock` au démarrage du fil puis remonté dans
    `snapshot()["error"]`) ; sinon renvoie le fragment.
- Gabarit : bouton « Actualiser » (désactivé avec `title` = raison), étape courante, une ligne par lane avec un
  `<progress value="done" max="total">` natif, `43/67`, nombre d'échecs, champions en cours ; temps écoulé et
  restant ; bloc « Dernier passage » (date et âge, statut ok / partiel / échec, matchups et synergies, bilan par
  lane). Styles dans `static/style.css`, avec les variables de couleur existantes.
- Écran Draft : le contexte de `draft.html` et de `/draft/stage` reçoit `updating = update_job.running` ; vrai, un
  bandeau `Données en cours de mise à jour : recommandations sur une base incomplète` en tête de l'écran.

### 4.5 Fermeture pendant une mise à jour (`src/client/window.py`, `src/client/launch.py`)

- `window.run(url, should_close: Callable[[], bool] = lambda: True)` : abonné à `window.events.closing` de
  pywebview 6.2.1 (vérifier l'API à la tâche : retour `False` du gestionnaire = fermeture annulée). Le
  gestionnaire appelle `should_close()`.
- `launch.py` construit `UpdateJob()`, le passe au serveur, et fournit `should_close` : si `job.running`,
  `window.create_confirmation_dialog("Mise à jour en cours", "Fermer arrête la mise à jour et restaure la base
  d'avant. Fermer ?")` ; non → `False` ; oui → `job.cancel(DONNEES_CLOSE_TIMEOUT_S)` puis `True`.
- `finally` de `run_client` : `job.cancel(...)` si `job.running` (repli navigateur et Ctrl+C).
- Best-effort : toute exception du gestionnaire laisse la fenêtre se fermer (`[ALERTE]` en console).

### 4.6 Tests

- `tests/test_parallel_parser.py` : `parse_page_by_role` avec un faux `_scrape_champion_page_with_retry` : événements
  `start`/`done` par champion ; `stop` posé après le premier `done` → `PipelineCancelled`, tâches restantes non
  scrapées ; un rappel qui lève ne casse pas le scrape.
- `tests/test_multilane.py` : `plan` émis avec les lanes dans l'ordre de `scraping_config.LANES` ; `stop` posé
  entre deux lanes → la seconde n'est pas scrapée.
- `tests/test_pipeline.py` (style existant, mocks) : `PipelineCancelled` → sauvegarde restaurée, `status="failed"` ;
  `last_scrape_lanes` écrit ; verrou tenu par un PID vivant → refus sans sauvegarde ni scrape ; PID mort → écrasé ;
  verrou levé après un run réussi et après un échec.
- `tests/test_client_donnees.py` (nouveau) : `UpdateJob` avec un faux `run` piloté par des événements
  (`current`, `done/total`, ETA `None` puis calculée, handlers du logger racine restaurés, second `start` refusé) ;
  routes : `/donnees` rend la page, `/donnees/etat` porte le polling seulement en cours, `POST /donnees/actualiser`
  refusé (409) en phase `draft` et `game`, bandeau Draft quand `running`.
- `tests/test_client_launch.py` (nouveau) : `should_close` refuse sur « non », appelle `cancel` sur « oui »
  (dialogue simulé, aucune vraie fenêtre).

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 181 | Progression et arrêt : `progress`/`stop` dans `parse_page_by_role`, `scrape_all_multilane`, `run_pipeline` ; `PipelineCancelled` restaure ; `db_meta.last_scrape_lanes` | 5 | — |
| 182 | Verrou `data/update.lock` (PID, `psutil`) dans `run_pipeline`, `UPDATE_LOCK_FILE` | 2 | — |
| 183 | `src/client/donnees.py` : `UpdateJob` (fil, état, ETA, logging restauré, `cancel`) et `donnees_view` ; constantes `DONNEES_*` | 3 | 181 |
| 184 | Écran Données : routes, `NAV`, gabarits, CSS, refus en `draft`/`game`, bandeau de l'écran Draft | 5 | 182, 183 |
| 185 | Fermeture gardée : `window.run(should_close)`, dialogue de confirmation, `cancel` dans `launch.py` | 2 | 183 |
| 186 | Clôture : `CHANGELOG.md`, statuts, README des specs, `docs/PROJECT_STRUCTURE.md`, recette @pj35 | 1 | 184, 185 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests du §4.6.
2. `python -m pytest tests/test_parallel_parser.py tests/test_multilane.py tests/test_pipeline.py -v` : un `stop` posé
   en cours de lane lève `PipelineCancelled` et `run_pipeline` restaure la sauvegarde (test dédié vert).
3. `grep -n "PipelineCancelled" src/pipeline.py` montre la branche qui restaure, à côté de `KeyboardInterrupt`.
4. Un second `run_pipeline` pendant qu'un autre processus vivant tient `update.lock` renvoie `status="failed"` sans
   appeler `backup_database` ni le scrape (test dédié vert) ; `grep -n "UPDATE_LOCK_FILE" src/config_constants.py`.
5. `POST /donnees/actualiser` renvoie 409 quand `bus.latest("phase")["kind"]` vaut `draft` ou `game` (test dédié).
6. `GET /donnees/etat` ne contient `hx-trigger="every` que si un run est en cours (test dédié).
7. Après un run (faux pipeline en test), les handlers du logger racine sont ceux d'avant le run.
8. `grep -n "\"donnees\"" src/client/app.py` : l'entrée de navigation est dans le groupe Coaching.
9. Aucune nouvelle valeur de réglage en dur : `DONNEES_POLL_S`, `DONNEES_ETA_MIN_PAGES`, `DONNEES_CLOSE_TIMEOUT_S`
   dans `src/config_client.py`.
10. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec, `docs/specs/README.md` et `docs/PROJECT_STRUCTURE.md` à jour.

**Vérification de bout en bout** : `python lol_coach.py --client`, client LoL fermé, écran Données → « Actualiser ».
La jauge de la première lane avance, les champions en cours défilent, l'estimation apparaît après 5 pages. Pendant ce
temps, `python scripts/update_all.py` refuse de démarrer (verrou). Fermer la fenêtre → dialogue ; « oui » → la base
retrouve son volume d'avant (`sqlite3 data/db.db "select count(*) from matchups"`). Relancer, laisser finir : le bloc
« Dernier passage » montre la date du jour et le bilan par lane. Recette réelle de @pj35 (1 h 40 de scrape).

## 7. Hors périmètre

- ❌ Bouton « Arrêter » : non retenu par @pj35 ; l'arrêt n'existe qu'à la fermeture de la fenêtre.
- ❌ « Recalcul seul » et options (matchups seuls, pool) depuis l'écran : restent en console (`--recompute-only`,
  menu 3).
- ❌ Scraper dans une copie de la base pour garder la draft utilisable pendant 1 h 40 : écarté par @pj35 (fusion des
  pools et revues écrites pendant le run). Le bouton grisé en draft et le bandeau couvrent le risque.
- ❌ Mise à jour automatique ou planifiée depuis le client : décision tranchée (mises à jour manuelles).
- ❌ Lecture du log `update_all.log` dans l'écran : le bilan par lane passe par `db_meta`.
- ❌ Priorité basse du processus (`_set_process_priority` du CLI) : elle ralentirait aussi le Live Coach ; Firefox
  tourne dans ses propres processus.
