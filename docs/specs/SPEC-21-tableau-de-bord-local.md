# SPEC-21 — Tableau de bord local (FastAPI + HTMX)

**Statut** : 🟡 **Rédigée le 2026-10-04**, architecture, écrans et cycle de vie validés par @pj35
(§2). Reste à valider : le démarrage d'office et le port (§2, « à valider »).

**Origine** : feature candidate 5 du `TODO.md` (ex-tâche #6, `ROADMAP_2026.md` Horizon 3),
repriorisée par @pj35 le 2026-09-26. SPEC-19 (§7, §8) et SPEC-20 ont livré leurs sorties
**en console d'abord**, en attendant cette GUI : courbe de LP, séries de Z par métrique, courbe
de win chance d'une partie.

**Effort** : ~6 jours, 9 tâches, 33 pts (§5).

---

## 1. Constat

Mesuré sur `data/db.db` le 2026-10-04 :

| Donnée | Volume | Lecture actuelle |
|---|---|---|
| `rank_snapshots` | 48 photos (SoloQ 37, Flex 11), du 2026-09-28 au 2026-10-02 | `lp_changes()` : une ligne de texte par file |
| `game_metrics` (joueur) | 43 parties, **toutes au poste top** ; 6 840 lignes | `profile()`, `trends()`, `patterns()` en console (commande `bilan`) |
| `game_records` avec timeline | 44 parties | `winprob/report.py::curve()` : sparkline de blocs ▁ à █ |
| `game_impact` | **0 ligne** (recette en partie réelle non faite) | `impact_review()` en console |
| `predictions` | 124 lignes, 114 labellisées (`spec13-v1` : 62) | `scripts/calibrate_model.py` : texte par décile |

Ce que la console ne donne pas : **une tendance se lit mal en texte**. Les séries sont courtes
aujourd'hui (43 parties, un seul poste) mais s'allongent à chaque partie. Le dépôt n'a aucune
dépendance web (`requirements.txt`) ; `fastapi 0.128`, `uvicorn 0.40`, `jinja2 3.1.6` sont
installés sur le poste mais ne sont pas déclarés ; l'API FastAPI du client a été retirée en 1.2.0 (`ROADMAP_2026.md`).

Contraintes du code existant :

- `Database.connect()` ouvre `sqlite3.connect(path)` sans `check_same_thread=False`, **imprime**
  `Connection to SQLite DB successful` et crée des index (écriture). Un thread serveur ne peut
  donc ni réutiliser la connexion de l'app, ni appeler `Database.connect()`.
- Les repositories (`CoachingRepository`, `PredictionsRepository`…) ne lisent que
  `db.connection` : tout objet doté de cet attribut leur convient.
- Le Live Coach (menu 1) est une boucle bloquante **dans le même processus** que le menu : un
  serveur doit déjà tourner quand on y entre.
- L'exe (75 Mo, un seul fichier) embarque `data/db.db` ; `config.get_resource_path()` résout les
  chemins gelés. `LeagueStatsCoach.spec` a `hiddenimports=[]`.

## 2. Objectif et arbitrages

**Objectif** : un tableau de bord local, en lecture seule, qui montre l'évolution du joueur
(rang, métriques, parties) et la qualité du modèle (calibration), sans toucher au Live Coach.

| Sujet | Décision |
|---|---|
| Architecture | **Validé (@pj35, 2026-10-04)** : approche C, FastAPI + Jinja2 + HTMX (plan de la ROADMAP). Écartées : page HTML statique (A) et serveur `http.server` sans dépendance (B), plus légères mais sans les routes et gabarits que @pj35 préfère. |
| Graphiques | **Validé** : SVG rendu côté serveur par des fonctions Python pures (testables en pytest). Aucune bibliothèque JS de graphiques ; le seul JS est `htmx.min.js`, copié dans `static/`. |
| Écrans du premier lot | **Validé** : courbe de LP par file ; séries `z_norm`/`z_objective` par métrique avec verdicts ; partie (courbe de win chance et impact) ; calibration du modèle de draft. |
| Cycle de vie | **Validé** : `uvicorn` en thread daemon dans le processus de l'app, lancé par une entrée du menu, idempotente (relancer ouvre seulement le navigateur). Écoute `127.0.0.1` uniquement. |
| Fraîcheur | **Sans objet** : les pages se calculent à chaque requête depuis la base, il n'y a rien à régénérer. |
| Taille de l'exe | **Validé : pas de limite.** La tâche 48 mesure la croissance et la consigne ; seul compte que l'exe démarre et serve les pages. |
| Écriture | **Validé** : lecture seule, aucune route `POST` dans ce lot. Fixer ou clore un axe de travail reste en console. |
| Démarrage d'office | **À valider** : défaut proposé, non ; l'entrée de menu suffit, un drapeau `--dashboard` peut venir ensuite. |
| Port | **À valider** : défaut proposé, port fixe `DASHBOARD_PORT = 8765` ; s'il est occupé, repli sur un port libre choisi par l'OS, affiché dans la console. |
| Langue | Français, sans i18n (décision ROADMAP). |

## 3. Approches considérées

- **A. Page HTML statique** générée en Python (SVG inline), ouverte par `webbrowser` : zéro
  dépendance, zéro serveur, mais pas de navigation dynamique.
- **B. `http.server` + SVG + HTMX** : zéro dépendance Python, filtres dynamiques, mais un routage
  et des gabarits à écrire à la main.
- **C. FastAPI + Jinja2 + HTMX — retenue** : routes, gabarits et tests (`TestClient`) standard.
  Coût : trois dépendances à déclarer, à empaqueter et à maintenir, et un exe plus gros.

## 4. Détail

### 4.1 Paquet `src/dashboard/`

| Module | Rôle |
|---|---|
| `src/config_dashboard.py` | `DashboardConfig` : `HOST = "127.0.0.1"`, `PORT = 8765`, fenêtres d'affichage (parties, points), couleurs ; réexporté par `config_constants.py` comme `config_coaching.py`. |
| `server.py` | `start(db_path) -> str` (URL) : démarre `uvicorn.Server` dans un thread daemon, **idempotent** (un second appel renvoie l'URL), best-effort (port impossible : `[ALERTE]` et retour `None`, jamais d'exception vers le menu). `stop()` pour les tests. |
| `app.py` | `create_app(db_path) -> FastAPI` (fabrique, pour les tests) ; routes `/`, `/rang`, `/progression`, `/parties`, `/parties/{game_id}`, `/calibration` ; fragments HTMX (`hx-get`, `hx-target`) pour le sélecteur de rôle, de file et de version du modèle. |
| `db.py` | `read_only(db_path)` : connexion `sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)` **par requête**, enveloppée dans un objet portant `.connection` pour les repositories existants. Ni index créé, ni message imprimé. |
| `data.py` | Fonctions pures qui préparent les séries (dictionnaires prêts à tracer) à partir des lignes lues : `rank_series()`, `metric_series()`, `game_curve()`, `reliability()`. |
| `charts.py` | Fonctions pures `line_chart()`, `reliability_chart()`, `bar_chart()` → chaîne SVG. Échelles, axes, graduations (paliers de rang pour les LP), `<title>`/`<desc>` pour l'accessibilité, couleurs par variables CSS (thème clair et sombre). |
| `templates/`, `static/` | `base.html`, une page par écran, `htmx.min.js` (version épinglée), `style.css`. |

### 4.2 Écrans

1. **Rang** : une courbe par file (SoloQ, Flex) sur l'échelle continue `lp_scale()` de
   `progression.py`, graduée en paliers ; variation sur la période. Sous deux photos par file :
   « pas assez de photos » (ignorance visible).
2. **Progression** : sélecteur de rôle (défaut : le poste le plus joué, `player_roles()`) ;
   tableau `profile()` (z moyen, parties) ; une petite courbe par métrique de la grille du rôle,
   moyenne glissante de `z_norm` et de `z_objective` (`player_history()`), marquée du verdict de
   `trends()` ; schémas actifs de `patterns()`. Sous `MIN_TREND_SAMPLE` parties, la métrique
   affiche « n/5 parties, pas de verdict » au lieu d'une courbe trompeuse.
3. **Parties** : liste des parties capturées (date, champion, poste, résultat) ; page d'une
   partie : courbe de win chance de l'équipe du joueur (nouvelle fonction
   `winprob.report.curve_points()`, extraite de `curve()` qui l'appelle), marqueurs des événements
   de `game_impact`, trois événements les plus coûteux et les plus rentables. Sans impact calculé :
   « impact non calculé pour cette partie », la courbe reste affichée si la timeline existe.
4. **Calibration** : diagramme de fiabilité (probabilité prédite contre fréquence observée par
   décile, taille des points = n), score de Brier, n, choix de `model_version` (jamais de mélange
   de versions, SPEC-05 §7). Nouvelle fonction `analysis.calibration.calibration_buckets()`,
   dont `calibration_curve()` devient une mise en forme (sortie texte **inchangée**, vérifiée
   par un test d'identité). Sous `MIN_ROWS_FOR_CALIBRATION` : même refus qu'en console.

### 4.3 Sécurité et robustesse

- Écoute sur `127.0.0.1` uniquement ; aucun secret ni clé affichés ; aucune route d'écriture.
- Toute valeur issue de la base ou du client LCU (noms de champion, pseudos) est échappée par
  Jinja2 (`autoescape` activé) ; le SVG est construit avec des nombres, les libellés sont
  échappés (`html.escape`).
- SQL paramétré, via les repositories existants ; requêtes nouvelles dans `src/repositories/`.
- Le serveur ne doit **jamais** gêner l'app : lancement et lecture best-effort ; une exception de
  page renvoie une page d'erreur HTTP 500 lisible, sans arrêter le thread.
- Lecture pendant que le Live Coach écrit : `timeout=5` ; sur `database is locked` persistant,
  page « base occupée, réessaie ».

### 4.4 Lancement

Menu principal : l'option 7 devient « Tableau de bord » et « Quitter » passe à 8 (`print_main_menu`,
`lol_coach.py`, `README.md`). Elle appelle `dashboard.server.start()`, imprime
`[INFO] Tableau de bord : http://127.0.0.1:8765`, ouvre `webbrowser.open()`, puis rend la main au
menu. Le serveur vit jusqu'à la sortie de l'app, y compris pendant le Live Coach.

### 4.5 Dépendances et empaquetage

- `requirements.txt` : `fastapi`, `uvicorn`, `jinja2` (bornes `>=` et `<` majeure, épinglées à
  l'installation d'après `pip show`) ; `httpx` en `requirements-dev.txt` pour `TestClient`.
- `LeagueStatsCoach.spec` : `datas` pour `src/dashboard/templates` et `static` ; `hiddenimports`
  d'`uvicorn` (`uvicorn.logging`, `uvicorn.loops.auto`, `uvicorn.protocols.http.auto`,
  `uvicorn.lifespan.on`) à confirmer par la tâche 48.
- Les gabarits se résolvent par `config.get_resource_path()`, jamais par un chemin relatif au
  répertoire courant.

### 4.6 Tests

Hermétiques (`temp_db`, `tmp_path`), `TestClient` sur `create_app(temp_db)` : chaque route répond
200 sur une base remplie **et** sur une base vide ; les fonctions de `charts.py` et `data.py` sont
testées sans serveur ; le test de `server.start()` utilise un port libre et appelle `stop()`.

## 5. Tâches

Numéros à la suite du `TODO.md` (dernière : 47).

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 48 | **Spike d'empaquetage** : une page « bonjour » servie par `uvicorn` depuis l'exe, `hiddenimports` et `datas` trouvés, taille de l'exe et délai de démarrage mesurés et consignés ici (§6) | 3 | — |
| 49 | Socle : `config_dashboard.py`, `db.py` (lecture seule), `server.py` (thread, idempotent, best-effort), `app.py` (fabrique), `base.html`, `htmx`, `style.css`, route `/` (fraîcheur des données, compteurs) + tests | 5 | 48 |
| 50 | `charts.py` : `line_chart`, `reliability_chart`, `bar_chart`, échelles et axes, thèmes, accessibilité + tests sur le SVG produit | 3 | 49 |
| 51 | Écran Rang : `data.rank_series()`, route `/rang`, ignorance visible + tests | 3 | 50 |
| 52 | Écran Progression : `data.metric_series()`, sélecteur de rôle HTMX, verdicts, schémas, seuils d'échantillon + tests | 5 | 50 |
| 53 | Écran Parties : `winprob.report.curve_points()` extraite, liste, page d'une partie, états vides + tests | 5 | 50 |
| 54 | Écran Calibration : `analysis.calibration.calibration_buckets()` extraite, diagramme de fiabilité, choix de version + test d'identité de `calibration_curve()` | 3 | 50 |
| 55 | Lancement : option 7 du menu (Quitter en 8), `webbrowser.open`, messages `[INFO]`/`[ALERTE]`, repli de port + tests | 3 | 49 |
| 56 | Empaquetage final : `requirements*.txt`, `.spec`, `build_app.py`, job `build` de la CI, vérification de l'exe, `README.md`, `docs/PROJECT_STRUCTURE.md`, `CHANGELOG.md` | 3 | 51–55 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, tests des tâches 48 à 56 compris ; `black --check` et
   `pylint src/ --fail-under=8.0` propres.
2. Sur une base vide (`temp_db`), les routes `/`, `/rang`, `/progression`, `/parties`,
   `/calibration` répondent **200** avec un message d'état vide, jamais une erreur.
3. Sur la base de production copiée (`data/db.db`), `/rang` trace deux courbes (SoloQ, Flex) et
   `/progression?role=top` affiche les métriques de la grille du rôle top, avec un verdict
   uniquement là où `trends()` en donne un.
4. `calibration_curve()` renvoie **exactement** le même texte qu'avant la refonte (test d'identité
   sur un jeu fixe) ; `/calibration` affiche le même Brier et le même n que
   `python scripts/calibrate_model.py`.
5. Aucune route n'accepte `POST`, `PUT` ni `DELETE` (test) ; le serveur n'écoute que sur
   `127.0.0.1` (test sur l'adresse liée) ; un nom de champion contenant `<script>` est rendu
   échappé (test).
6. Le thread serveur est un daemon : l'app se ferme normalement tant qu'il tourne ; un port
   occupé ne lève aucune exception dans le menu (message `[ALERTE]`, l'app continue).
7. Ouvrir le tableau de bord pendant que `python lol_coach.py` écrit dans la base ne bloque
   jamais le Live Coach (lecture seule, `timeout=5`) ; `data/db.db` est inchangée après
   consultation (mtime et contenu).
8. **Vérification de bout en bout** : `python build_app.py`, lancer l'exe de
   `LeagueStatsCoach_Release/`, choisir l'option 7 : le navigateur s'ouvre sur les quatre écrans,
   thème clair et sombre lisibles. Recette à faire par @pj35 (reste ⬜ dans le `TODO.md`).
9. Mesure de l'exe (tâche 48) consignée en fin de spec : taille avant, après, délai de démarrage.
10. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec et `docs/specs/README.md` à jour.

## 7. Hors périmètre

- ❌ **Écriture depuis la GUI** (fixer, clore un axe de travail, appliquer une calibration) :
  décisions manuelles en console, à rouvrir une fois les écrans de lecture éprouvés.
- ❌ **Écrans de draft** (tier list, Team Builder, Live Coach) : la console reste leur interface ;
  le Live Coach exige un retour immédiat que cette GUI ne vise pas.
- ❌ **Mise à jour en direct** (WebSocket, rafraîchissement automatique) : un rechargement de page
  suffit pour un outil consulté entre les parties.
- ❌ **Accès réseau** (autre machine, mobile) et toute authentification : `127.0.0.1` seulement.
- ❌ **Bibliothèque de graphiques JS** (Chart.js et autres) : le SVG serveur couvre ces quatre écrans.
- ❌ **Réécriture des sorties console** : `report.py` et `calibrate_model.py` restent, la GUI s'ajoute.
