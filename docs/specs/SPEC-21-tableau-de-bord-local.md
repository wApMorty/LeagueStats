# SPEC-21 — Client LeagueStats : l'interface enhanced du client LoL

**Statut** : 🟡 **Réécrite le 2026-10-04** (la version « tableau de bord en lecture seule » est
remplacée). Forme, périmètre, ordre, temps réel et niveau d'écriture validés par @pj35 (§2). Reste
à valider : les thèmes et la direction du motion design (§2, §4.3), les écritures du coaching et
le point d'entrée.

**Origine** : feature candidate 5 du `TODO.md` (ex-tâche #6, `ROADMAP_2026.md` Horizon 3),
repriorisée le 2026-09-26. Reformulée par @pj35 le 2026-10-04 : « bien plus qu'un rapport HTML en
fin de partie […] l'équivalent de mon propre client, entièrement customisable, qui servirait
d'interface enhanced par mon moteur pour interagir avec le client de base. On y mettrait toutes
les features de navigation du client de base, mais en rajoutant une section complète sur le
coaching, et en revoyant la draft et le post-game avec le Live Coach. » Ajout le même jour :
**la qualité des animations est un objectif de premier rang** (motion design poussé, thèmes à
discuter avec @pj35).

**Effort** : ~22 jours, 25 tâches, 109 pts, en six lots utilisables chacun seuls (§5).

---

## 1. Constat

Mesuré le 2026-10-04 sur `data/db.db` (lecture seule) et sur le client LoL ouvert de @pj35
(requêtes `GET` uniquement, aucune écriture) :

| Donnée | Volume | Lecture actuelle |
|---|---|---|
| `rank_snapshots` | 59 photos | `lp_changes()` : une ligne de texte par file |
| `game_metrics` (joueur) | 7 470 lignes | `profile()`, `trends()`, `patterns()` en console (`bilan`) |
| `game_records` | 48 parties capturées | `winprob/report.py::curve()` : sparkline de blocs ▁ à █ |
| `game_impact` | 11 532 lignes | `impact_review()` en console |
| `predictions` | 131 lignes | `scripts/calibrate_model.py` : texte par décile |

**Le LCU offre de quoi construire un client.** `GET /help` renvoie **1 473 fonctions et 937
événements** ; `/swagger/v3/openapi.json` répond 404, l'inventaire des endpoints vient donc de
`/help`. Lectures qui répondent 200 sur le client de @pj35 : `lol-summoner/v1/current-summoner`,
`lol-lobby/v2/lobby` (un lobby était ouvert) et `/members`, `lol-chat/v1/me`, `/friends` (157
entrées), `/conversations`, `lol-game-queues/v1/queues` (88 files), `lol-champions/v1/owned-champions-minimal`
(245 champions), `lol-perks/v1/pages` (14 pages), `lol-ranked/v1/current-ranked-stats`,
`lol-gameflow/v1/gameflow-phase`, `lol-challenges/v1/summary-player-data/local-player`,
`lol-regalia/v2/current-summoner/regalia`. `lol-matchmaking/v1/search` répond 404 hors recherche
(état normal). **Le WebSocket fonctionne** : connexion `wss://127.0.0.1:{port}` avec l'en-tête
`Authorization` de `LCUCredentials.auth_header`, abonnement `[5, "OnJsonApiEvent"]` accepté.
Les formes des réponses (hors celles déjà fixées par SPEC-08, 15, 19, 20) restent à relever par la
tâche 76.

**Ce que le code fait aujourd'hui** :

- `LCUClient` (`src/lcu_client.py`) est synchrone (`requests`), **sans WebSocket** : tout passe par
  du polling (`draft_config.POLL_INTERVAL`). Ni `websockets` ni `websocket-client` ne sont déclarés
  dans `requirements.txt` (installés sur le poste : `websockets 16.0`).
- Le Live Coach (`DraftMonitor`, `src/draft_monitor.py`) est une boucle **bloquante** lancée par le
  menu 1 dans le processus de la console ; ses sorties sont des `print`. Les recommandations ne
  sont **pas** une donnée : `DraftRecommender._print_results` / `provide`
  (`src/draft/recommendations.py:97-250`) construisent et impriment en un seul geste. Un écran de
  draft a besoin de la donnée.
- Les commandes du joueur (`r <champion> <lane>`, `outcome win`, `axe <métrique>`) entrent par une
  `queue.Queue` (`DraftMonitor._command_queue`, `src/draft/commands.py`) alimentée par un fil
  `input()` : une interface peut y déposer les mêmes chaînes sans toucher à la logique.
- Les actions sur la draft existent déjà : survol et verrouillage (`HoverAutomation`,
  `LCUClient` : `/lol-champ-select/v1/session/actions/{id}`), acceptation de la file
  (`/lol-matchmaking/v1/ready-check/accept`), runes et items (`src/draft/loadout_lcu.py`).
- `Database.connect()` ouvre `sqlite3.connect(path)` sans `check_same_thread=False`, **imprime**
  `Connection to SQLite DB successful` et crée des index (écriture) : un thread serveur ne peut ni
  réutiliser la connexion de l'app ni l'appeler. Les repositories ne lisent que `db.connection`.
- Aucune dépendance web ni de fenêtre dans `requirements.txt` ; `fastapi 0.128`, `uvicorn 0.40`,
  `jinja2 3.1.6`, `httpx` et `sse-starlette 3.4.1` sont installés mais non déclarés ; `pywebview`
  n'est **pas** installé. L'exe pèse 75 Mo (`LeagueStatsCoach.spec` : `hiddenimports=[]`,
  `datas=[('data/db.db', '.'), ('README.md', '.')]`).
- L'overlay de SPEC-20 (`src/winprob/overlay.py`, `tkinter`) est un processus à part.

## 2. Objectif et arbitrages

**Objectif** : un client de bureau, propre au produit, qui parle au client LoL par le LCU : les
écrans de navigation du client de base, une section **Coaching** complète, et une draft et un
post-game revus avec le Live Coach, le tout animé avec soin.

| Sujet | Décision |
|---|---|
| Forme | **Validé (@pj35, 2026-10-04)** : fenêtre native `pywebview` (WebView2) sur un serveur FastAPI local (JSON + SSE), front sans chaîne de build (HTMX + JS natif). Écartées : navigateur seul (A), SPA avec Node (C) (§3). Le client LoL reste ouvert, réduit : le LCU est son moteur. |
| Périmètre de navigation | **Validé** : profil, rang, historique ; lobby et file d'attente ; collection ; social. Boutique, butin, Clash, missions, TFT, replays : hors lot (§7). |
| Section Coaching | **Validé** : section complète (rang, progression, parties, calibration, accueil avec axes de travail, constats et bilan). |
| Draft et post-game | **Validé** : écran de draft interactif (état, recommandations, win chance, rôles, clic pour survoler et verrouiller via le LCU) et post-game qui remplace la sortie console ; la console reste en secours. |
| Ordre | **Validé** : coaching, draft et post-game d'abord ; puis profil/historique, collection, lobby/file, social (§5). |
| Temps réel | **Validé** : WebSocket LCU pour le client, **polling du Live Coach inchangé** ; la boucle de draft publie seulement son état sur un bus interne, en best-effort. |
| Écriture sur le LCU | **Validé** : lobby, file et draft en écriture ; social en **lecture seule** (ni message, ni invitation). |
| Customisation | **Validé pour ce lot : thème seul** (couleurs, police, densité, clair/sombre, mémorisés dans les préférences). Mise en page déplaçable et réglages du moteur depuis l'interface : **à rouvrir** (§7) ; la structure en composants ne les interdit pas. |
| Motion design | **Objectif de premier rang (@pj35, 2026-10-04)** : système de motion dédié (§4.3), pas de décor ajouté en fin de chantier. Les thèmes et leur direction artistique se discutent avec @pj35 **avant** la tâche 69 : **À valider**. |
| Bibliothèque d'animation | **À valider** : défaut proposé, CSS + Web Animations API + View Transitions (zéro dépendance) ; un moteur de ressorts (Motion, vendu dans `static/`) seulement si le spike (tâche 48) le justifie. |
| Cadre de la fenêtre | **Validé (@pj35, 2026-10-04) : sans bordure comme cible** (`frameless=True`), barre de titre et boutons Réduire/Agrandir/Fermer dessinés en HTML et animés, appelant `minimize()`, `maximize()`, `restore()`, `destroy()`. Le spike (tâche 48) vérifie sur le poste de @pj35 quatre points : déplacement limité à la barre de titre, redimensionnement par les bords (poignées HTML + `resize()`/`move()`), agrandissement qui respecte la barre des tâches, ombre et coins sous Windows 11 (l'ancrage et le survol de Agrandir sont probablement perdus). Si l'un ne se contourne pas proprement : repli sur la fenêtre standard à barre de titre sombre, sans autre perte. |
| Écritures du coaching dans la base | **À valider** : défaut proposé, oui, via une connexion d'écriture distincte et les repositories existants (fixer ou clore un axe, `outcome`) ; la lecture reste en `mode=ro`. Cela lève la règle « lecture seule » de la version précédente. |
| Point d'entrée | **À valider** : défaut proposé, `python lol_coach.py --client` et option 7 du menu ; démarrage d'office du client plus tard. |
| Port | **À valider** : défaut proposé, port libre choisi par l'OS (la fenêtre locale n'a pas besoin d'un port connu), affiché en `[INFO]`. |
| Taille de l'exe | **Validé** : pas de limite ; le spike mesure et consigne (§8). |
| Langue | Français, sans i18n (décision ROADMAP). |

**Décisions du `TODO.md` rouvertes par cette spec** (à acter dans « Hors périmètre (tranché) »,
@pj35 l'ayant demandé) : « GUI lourde » et l'écart de SPEC-21 v1 §7 « écrans de draft hors
périmètre ». Restent tranchés : SQLite seul, pas de backend distant, pas de multi-utilisateur, pas
d'i18n, mises à jour de données manuelles.

## 3. Approches considérées

**Forme du client**

- **A. Navigateur + FastAPI/HTMX** : zéro dépendance de plus, mais un onglet et non un client ; la
  qualité d'animation dépend du navigateur de @pj35.
- **B. Fenêtre `pywebview` (WebView2) sur FastAPI — retenue** : fenêtre dédiée, moteur Chromium déjà
  présent sous Windows 11, même serveur testable avec `TestClient`, pas de Node. Coût : une
  dépendance native à empaqueter ; `pywebview` exige le **fil principal** (comme `tkinter` pour
  l'overlay de SPEC-20), donc le Live Coach passe en fil de fond en mode client.
- **C. SPA React/Svelte avec build** : le plus souple pour un écosystème d'animation, mais impose
  Node/npm à un projet 100 % Python et à la CI.

**Temps réel**

- **WebSocket LCU pour le client — retenu.** Lobby, chat et phases de jeu arrivent en événements ;
  le polling coûterait des requêtes pour rien et serait lent.
- Polling partout : simple, mais lobby et chat deviennent lents.
- WebSocket y compris pour le Live Coach : réécrit le chemin critique de la draft, risque de
  régression en pleine partie ; rien ne le justifie.

## 4. Détail

### 4.1 Processus et fils

Mode client (`python lol_coach.py --client`) :

| Fil | Rôle |
|---|---|
| principal | fenêtre `pywebview` (obligatoire) |
| `uvicorn` (daemon) | FastAPI : pages, JSON, SSE, actions |
| Live Coach (daemon) | `DraftMonitor.start_monitoring()` inchangé, mais sans entrée console : pool lue dans `user_prefs.json`, commandes déposées dans `_command_queue` par l'interface |
| WebSocket LCU (daemon) | `lcu_events.py` : abonnement, reconnexion exponentielle bornée, republie sur le bus |

Le serveur a **son propre** `LCUClient` (lectures et actions) : `last_status_code` n'est pas sûr
entre fils tant que SPEC-23 tâche 62 ne l'a pas rendu local au fil, et une session `requests`
partagée avec la boucle de draft ne doit pas être touchée. `console=True` du `.spec` est conservé
tant que la console sert de secours.

### 4.2 Paquet `src/client/`

| Module | Rôle |
|---|---|
| `src/config_client.py` | `ClientConfig` : fenêtre (taille, minimum), fenêtres d'affichage, durées et courbes du motion (§4.3), noms de thèmes ; réexporté par `config_constants.py` comme `config_coaching.py`. |
| `server.py` | `start(db_path) -> str` : `uvicorn.Server` en fil daemon, idempotent, best-effort (échec : `[ALERTE]`, retour `None`, jamais d'exception vers le menu) ; `stop()` pour les tests. |
| `window.py` | Création de la fenêtre `pywebview` sans bordure, API exposée à la page (réduire, agrandir, restaurer, fermer, déplacer, redimensionner), repli fenêtre standard puis `webbrowser.open()` si WebView2 manque. |
| `app.py` | `create_app(db_path, bus, lcu) -> FastAPI` (fabrique) ; routes par section ; `/events` (SSE) ; fragments HTMX. |
| `db.py` | `read_only(db_path)` : `sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)` **par requête**, enveloppée dans un objet portant `.connection`. Ni index créé ni message imprimé. `writable(db_path)` pour les seules écritures du coaching (§2). |
| `bus.py` | `EventBus` : `publish(topic, payload)` jamais bloquant (file bornée, abandon du plus ancien), `subscribe(topics)` pour le SSE. |
| `lcu_events.py` | Client WebSocket LCU (`websockets`), filtre les 937 événements aux préfixes suivis (`/lol-gameflow`, `/lol-lobby`, `/lol-matchmaking`, `/lol-champ-select`, `/lol-chat`, `/lol-end-of-game`, `/lol-ranked`). |
| `lcu_proxy.py` | Lectures de navigation et actions autorisées : liste blanche d'endpoints, jamais de chemin passé tel quel par le front. |
| `data.py`, `charts.py` | Fonctions pures : séries prêtes à tracer et SVG (§4.4). |
| `templates/`, `static/` | Coque, une page par écran, `htmx.min.js` épinglé, `style.css`, `motion.js`, thèmes. |

### 4.3 Thème et motion design

Le motion est un **système**, pas des effets : tout passe par des jetons.

- **Jetons** (`config_client.py` et variables CSS) : durées (`instant`, `rapide`, `normal`,
  `lent`), courbes (`standard`, `entrée`, `sortie`, ressort), échelons de décalage (`stagger`),
  distances. Un thème surcharge couleurs, police, rayons, ombres **et** le caractère du motion
  (vif ou posé). Aucune valeur de durée en dur dans un gabarit.
- **Primitives** (`static/motion.js`, une centaine de lignes, testables à la main sur le banc
  `/_motion`) : transition de page (View Transitions API, repli en fondu), apparition échelonnée
  d'une liste, compteur numérique qui roule, tracé de courbe SVG (`stroke-dashoffset`), barre de
  win chance qui glisse, passage de carte au verrouillage d'un champion, pulsation de la file
  trouvée.
- **Contraintes de performance** : animer uniquement `transform` et `opacity` (compositeur) ;
  budget 16,7 ms par image mesuré au spike et sur le banc ; aucune animation ne bloque une
  interaction (annulable, jamais modale) ; **`prefers-reduced-motion`** respecté (durées
  quasi nulles, jamais d'effet seul porteur d'information).
- **Où le motion compte** : l'entrée dans la draft (picks qui se posent, rôles qui se résolvent,
  recommandation qui change), la file trouvée, la révélation du post-game (courbe de win chance
  qui se trace, impact par événement qui s'empile), les transitions entre sections.
- **Thèmes** : un fichier par thème (`static/themes/<nom>.css`, variables seulement). Le lot 1
  livre **un** thème sombre et un clair ; la direction artistique des suivants se décide avec
  @pj35 avant la tâche 69 (**à valider**). Choix mémorisé dans `user_prefs.json`.

### 4.4 Section Coaching (reprend le contenu de SPEC-21 v1, enrichi)

1. **Accueil** : axes de travail (`coaching_goals`), derniers constats, résumé du bilan,
   fraîcheur des données. Fixer ou clore un axe : écriture DB (§2, à valider).
2. **Rang** : une courbe par file sur l'échelle `lp_scale()`, graduée en paliers ; sous deux photos
   par file : « pas assez de photos » (ignorance visible).
3. **Progression** : sélecteur de rôle (défaut : le plus joué, `player_roles()`), tableau
   `profile()`, une courbe par métrique de la grille du rôle (moyenne glissante de `z_norm` et
   `z_objective`, `player_history()`) marquée du verdict de `trends()`, schémas de `patterns()`.
   Sous `MIN_TREND_SAMPLE` : « n/5 parties, pas de verdict ».
4. **Parties** : liste des parties capturées, page d'une partie (courbe de win chance via
   `winprob.report.curve_points()` extraite de `curve()`, marqueurs de `game_impact`, trois
   événements les plus coûteux et les plus rentables). Sans impact : « impact non calculé », courbe
   affichée si la timeline existe.
5. **Calibration** : diagramme de fiabilité, Brier, n, choix de `model_version` (jamais de mélange,
   SPEC-05 §7), via `analysis.calibration.calibration_buckets()` dont `calibration_curve()` devient
   une mise en forme (sortie texte **inchangée**, test d'identité). Sous `MIN_ROWS_FOR_CALIBRATION` :
   même refus qu'en console.

Les SVG sont construits côté serveur par des fonctions pures (`charts.py` : `line_chart`,
`reliability_chart`, `bar_chart`), couleurs par variables CSS, `<title>`/`<desc>` pour
l'accessibilité, chemins prêts pour l'animation de tracé.

### 4.5 Draft interactive et post-game (lot 2)

**Donnée avant affichage.** `src/draft/snapshot.py` définit `DraftSnapshot` (dataclass
sérialisable : phase, picks et bans par camp avec rôle, source et confiance, recommandations
`{champion, score, delta, profondeur, variation, parties}`, champions écartés et leur raison,
conseil, état du loadout). `DraftRecommender.provide` construit le snapshot **puis** l'imprime : la
**sortie console reste identique** (test d'identité sur un jeu fixe) ; `DraftMonitor` le publie sur
le bus, dans un `try/except` : **aucune exception ne doit interrompre le monitoring**
(`CLAUDE.md`). En mode console, le bus est absent et rien ne change.

**Écran de draft** : deux colonnes d'équipes avec rôles, bans, recommandations classées avec
variation attendue, win chance prédite en fin de draft, état du loadout. Actions par clic :
survoler et verrouiller (les mêmes appels que `HoverAutomation`), corriger un rôle (dépose
`r <champion> <lane>` dans `_command_queue`). Une action n'est acceptée que pour la phase et le
tour courants ; sinon refus lisible, jamais d'appel LCU.

**Post-game** : à l'événement `game_captured` (publié par `GameCapture.on_post_game`), la fenêtre
bascule sur la page de la partie en mode « revue » : lecture de la base, pas de duplication du
rapport texte. Y figurent la courbe de win chance, l'impact par événement, les écarts à la norme et
à l'objectif (`Finding`), la variation de LP, l'objectif jugé. Il remplace la sortie console du
rapport en mode client ; la console la garde en mode console.

### 4.6 Navigation (lots 3 à 6)

| Lot | Écran | Source LCU | Écriture |
|---|---|---|---|
| 3 | Profil, rang, régalia, défis | `lol-summoner`, `lol-ranked`, `lol-regalia`, `lol-challenges` | non |
| 3 | Historique et détail de partie (20 parties au plus, limite du LCU ; les parties capturées ajoutent la timeline et l'impact) | `lol-match-history` | non |
| 4 | Collection : champions possédés, pages de runes, sets d'items | `lol-champions`, `lol-perks`, `lol-item-sets` | non (l'import de SPEC-15 reste son propre chemin) |
| 5 | Lobby : files (`lol-game-queues`), postes, membres | `lol-lobby/v2` | **oui** : créer, choisir file et postes, quitter |
| 5 | File : recherche, annulation, acceptation | `lol-matchmaking` | **oui** : lancer, annuler, accepter |
| 6 | Social : amis, statuts, conversations | `lol-chat` | **non** (lecture seule) |

Chaque écran suit la même règle : une liste blanche d'endpoints dans `lcu_proxy.py`, un état vide
et un état « client LoL fermé » explicites, et **aucune supposition de forme** : les formes sont
relevées par la tâche 76 et figées en fixtures (`tests/fixtures/`), comme SPEC-19.

### 4.7 Sécurité et robustesse

Le client **écrit** désormais (LCU et, à valider, base) : le serveur local devient une surface
d'attaque pour toute page ouverte dans le navigateur de @pj35.

- Écoute sur `127.0.0.1` uniquement.
- **Jeton de session** aléatoire généré à chaque lancement, injecté dans la page, exigé dans un
  en-tête sur **toute** route `POST`/`PUT`/`DELETE` et sur le SSE ; contrôle des en-têtes `Host` et
  `Origin` (anti-DNS rebinding et anti-CSRF). Une requête sans jeton valide : 403, aucun appel LCU.
- Le mot de passe du LCU ne quitte jamais le serveur ; aucun secret affiché.
- Le front ne passe jamais un chemin LCU : il nomme une action, `lcu_proxy.py` la traduit.
- Toute valeur issue de la base ou du LCU (pseudos, noms, messages de chat) est échappée par Jinja2
  (`autoescape`) ; les libellés de SVG par `html.escape`.
- SQL paramétré, via les repositories ; requêtes nouvelles dans `src/repositories/`.
- Le client **ne doit jamais** gêner l'app ni le Live Coach : lancement et lectures best-effort,
  une exception de route renvoie une page d'erreur 500 lisible sans arrêter le fil.
- Lecture pendant que le Live Coach écrit : `timeout=5` ; sur `database is locked` persistant,
  page « base occupée, réessaie ».
- Le LCU n'est ni documenté ni garanti par Riot : un endpoint peut changer avec un patch. Chaque
  écran dégrade en « indisponible » plutôt qu'en erreur, et la liste blanche concentre les points
  à réparer.

### 4.8 Dépendances et empaquetage

- `requirements.txt` : `fastapi`, `uvicorn`, `jinja2`, `sse-starlette`, `websockets` (>= 14, pour
  `additional_headers`), `pywebview` ; bornes `>=` et `<` majeure, épinglées d'après `pip show` ;
  `httpx` en `requirements-dev.txt` pour `TestClient`.
- `LeagueStatsCoach.spec` : `datas` pour `src/client/templates` et `static` ; `hiddenimports`
  d'`uvicorn` et de `pywebview` à établir par la tâche 48. WebView2 est présent sous Windows 11 ;
  son absence déclenche le repli navigateur et un `[ALERTE]`.
- Gabarits et statiques résolus par `config.get_resource_path()`, jamais par chemin relatif.

### 4.9 Tests

Hermétiques (`temp_db`, `tmp_path`, faux `LCUClient`), `TestClient` sur `create_app(...)` : chaque
route répond 200 sur base remplie **et** vide, et « indisponible » sans LCU ; `charts.py`,
`data.py`, `bus.py`, `lcu_proxy.py` testés sans serveur ; le WebSocket testé sur un faux serveur
local ; `server.start()` sur un port libre avec `stop()`. Le motion n'est pas testable en pytest :
il se vérifie sur le banc `/_motion` et à la recette (§6, 10 et 11).

## 5. Tâches

Numéros à la suite du `TODO.md` (dernière : 67). **Les tâches 48 à 56 gardent leur numéro** (elles
n'étaient pas commencées) et sont réécrites ; les tâches 68 et suivantes s'y ajoutent. L'ordre
d'exécution est celui des lots.

**Lot 1 — Socle, thème, motion, section Coaching (55 pts)**

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 48 | **Spike d'empaquetage et de fluidité** : fenêtre `pywebview` servie par `uvicorn` depuis l'exe, une animation de test ; `hiddenimports` et `datas` trouvés ; taille, délai de démarrage et temps d'image mesurés et consignés (§8) ; vérifie les quatre points de la fenêtre sans bordure (§2) et tranche la bibliothèque d'animation | 5 | — |
| 49 | Socle : `config_client.py`, `db.py` (lecture seule), `server.py` (fil, idempotent, best-effort), `app.py` (fabrique), jeton de session et contrôle `Host`/`Origin` + tests | 5 | 48 |
| 68 | Coque : `window.py`, barre de titre maison (déplacement, poignées de redimensionnement, boutons animés), `base.html`, navigation par sections, transitions de page, états « client LoL fermé » et « base occupée » | 5 | 49 |
| 69 | Thème et motion : jetons, `motion.js` (primitives §4.3), banc `/_motion`, `prefers-reduced-motion`, deux thèmes (sombre, clair) arrêtés avec @pj35 | 5 | 68 |
| 70 | Bus et temps réel : `bus.py`, route SSE, `lcu_events.py` (WebSocket LCU, reconnexion), faux serveur de test | 5 | 49 |
| 50 | `charts.py` : `line_chart`, `reliability_chart`, `bar_chart`, échelles, axes, accessibilité, tracé animable + tests sur le SVG | 5 | 69 |
| 51 | Écran Rang : `data.rank_series()`, ignorance visible + tests | 3 | 50 |
| 52 | Écran Progression : `data.metric_series()`, sélecteur de rôle, verdicts, schémas, seuils d'échantillon + tests | 5 | 50 |
| 53 | Écran Parties : `winprob.report.curve_points()` extraite, liste, page d'une partie, états vides + tests | 5 | 50 |
| 54 | Écran Calibration : `analysis.calibration.calibration_buckets()` extraite, diagramme de fiabilité, choix de version + test d'identité de `calibration_curve()` | 3 | 50 |
| 71 | Accueil Coaching : axes de travail, constats, bilan ; fixer/clore un axe (si écriture validée) + tests | 3 | 51–54 |
| 55 | Lancement : `--client` et option 7 du menu (Quitter en 8), Live Coach en fil sans entrée console, message `[INFO]`/`[ALERTE]` + tests | 3 | 49, 70 |
| 56 | Empaquetage du lot : `requirements*.txt`, `.spec`, `build_app.py`, job `build` de la CI, exe vérifié, `README.md`, `docs/PROJECT_STRUCTURE.md`, `CHANGELOG.md` | 3 | 51–55, 71 |

**Lot 2 — Draft interactive et post-game (20 pts)**

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 72 | `DraftSnapshot` et recommandations structurées ; sortie console **identique** (test d'identité) ; publication best-effort sur le bus | 5 | 70 |
| 73 | Écran de draft (lecture) : équipes, rôles, bans, recommandations, win chance, loadout, motion de la draft | 5 | 72 |
| 74 | Actions de draft : survoler, verrouiller, corriger un rôle ; garde de phase et de tour ; tests avec faux LCU | 5 | 73 |
| 75 | Post-game : événement `game_captured`, page de revue animée (courbe, impact, constats, LP, objectif) | 5 | 72, 53 |

**Lot 3 — Profil et historique (13 pts)**

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 76 | **Spike des endpoints de navigation** : formes relevées sur le client de @pj35 pour les lots 3 à 6, fixtures, corrections de §4.6 | 3 | 70 |
| 77 | Profil, rang, régalia, défis | 5 | 76 |
| 78 | Historique (20 parties) et détail ; liaison aux parties capturées | 5 | 76, 53 |

**Lots 4 à 6 et clôture (21 pts)**

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 79 | Collection : champions possédés, pages de runes, sets d'items (lecture) | 5 | 76 |
| 80 | Lobby : files, postes, membres ; créer, choisir, quitter | 5 | 76 |
| 81 | File : lancer, annuler, accepter ; pulsation « partie trouvée » ; cohabitation avec l'auto-accept du Live Coach | 5 | 80 |
| 82 | Social en lecture seule : amis, statuts, conversations | 3 | 76 |
| 83 | Clôture : exe vérifié, `README.md`, `docs/PROJECT_STRUCTURE.md`, `CHANGELOG.md`, statuts, `TODO.md` | 3 | 74, 75, 77–79, 81, 82 |

Total : 55 + 20 + 13 + 21 = **109 pts**. Chaque lot se clôt par une recette de @pj35 (§6, 10).

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, tests des tâches 48 à 56 et 68 à 83 compris ; `black --check`
   et `pylint src/ --fail-under=8.0` propres.
2. Sur base vide (`temp_db`), toutes les routes de la section Coaching répondent **200** avec un
   message d'état vide ; sans client LoL (faux LCU en échec), les écrans de navigation répondent
   200 avec « client LoL fermé », jamais une 500.
3. Sur la base de production copiée, `/rang` trace deux courbes (SoloQ, Flex) et
   `/progression?role=top` affiche les métriques de la grille du rôle top, avec un verdict
   uniquement là où `trends()` en donne un.
4. `calibration_curve()` et la sortie console du Live Coach (recommandations, tâche 72) sont
   **identiques** à celles d'avant la refonte (tests d'identité sur jeux fixes) ; `/calibration`
   affiche le même Brier et le même n que `python scripts/calibrate_model.py`.
5. **Sécurité** : le serveur n'écoute que sur `127.0.0.1` (test sur l'adresse liée) ; toute route
   `POST`/`PUT`/`DELETE` et le SSE répondent 403 sans jeton de session valide ou avec un `Origin`
   étranger (test) ; aucun appel LCU n'a lieu dans ce cas (faux LCU) ; un nom de champion contenant
   `<script>` est rendu échappé (test) ; `lcu_proxy.py` refuse tout endpoint hors liste blanche.
6. **Écritures** : aucun appel `POST`/`PUT`/`PATCH`/`DELETE` vers le LCU hors lobby, file et draft ;
   aucune route d'envoi de message ni d'invitation (test sur la liste blanche).
7. **Isolation** : les fils serveur, WebSocket et Live Coach sont des daemons ; l'app se ferme
   normalement ; un port ou un WebSocket indisponible ne lève aucune exception dans le menu ni dans
   la boucle de draft (messages `[ALERTE]`) ; une exception dans la publication du bus n'interrompt
   pas le monitoring (test avec bus en échec).
8. Ouvrir le client pendant que le Live Coach écrit ne le bloque jamais (lecture `mode=ro`,
   `timeout=5`) ; `data/db.db` n'a pas bougé après consultation (mtime et contenu), hors écritures
   explicites du coaching.
9. **Draft** : avec un faux LCU rejouant une session de champ select, le snapshot publié contient
   équipes, rôles et recommandations ; l'action « verrouiller » n'émet l'appel LCU que pour la phase
   et le tour courants (tests, tâches 72 et 74).
10. **Recette de bout en bout** (@pj35) : `python build_app.py`, lancer l'exe, ouvrir le client ;
    dérouler une vraie file jusqu'au post-game (acceptation, draft avec survol et verrouillage au
    clic, revue de partie) ; thème clair et sombre lisibles. Reste ⬜ dans le `TODO.md` tant qu'elle
    n'est pas faite.
11. **Motion** : sur le banc `/_motion` et sur les écrans de draft et de post-game, **p95 du temps
    d'image ≤ 16,7 ms** sur le poste de @pj35 (mesure consignée en §8) ; `prefers-reduced-motion`
    coupe les animations non essentielles ; aucune animation ne retarde une action.
12. Mesures du spike (tâche 48) consignées en §8 : taille de l'exe avant/après, délai de démarrage,
    temps d'image.
13. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec, `docs/specs/README.md` et `TODO.md` à jour.

## 7. Hors périmètre

- ❌ **Boutique, butin (loot), Clash, missions, TFT, replays, honneur** : aucune de ces features
  n'a été retenue par @pj35 ; la boutique et le butin engagent en plus des achats.
- ❌ **Écriture sociale** (messages, invitations, gestion des amis) : lecture seule (@pj35,
  2026-10-04), surface de risque la plus forte pour un LCU non garanti.
- ❌ **Mise en page déplaçable et réglages du moteur depuis l'interface** : thème seul pour ce lot ;
  à rouvrir avec leur coût (stockage des dispositions ; sortie des constantes de
  `config_constants.py`, contraire à la règle actuelle).
- ❌ **Overlay et écran « en partie »** : l'overlay de SPEC-20 reste un processus à part ; un écran
  de partie en cours dans le client n'est pas demandé.
- ❌ **Réécriture de la boucle de draft** : le Live Coach garde son polling ; le client s'y branche
  par un bus, rien de plus.
- ❌ **Chaîne de build front** (Node, React, Svelte) : écartée (§3).
- ❌ **Accès réseau** (autre machine, mobile) et authentification : `127.0.0.1` seulement.
- ❌ **Réécriture des sorties console** : `report.py`, `calibrate_model.py` et l'affichage de draft
  restent, le client s'y ajoute.
- ❌ **Automatiser le jeu** : le client agit sur la draft, le lobby et la file à la demande de
  @pj35 ; rien dans la partie elle-même.

## 8. Mesures du spike (tâche 48)

À consigner : taille de l'exe avant (75 064 370 octets le 2026-10-03) et après, délai de démarrage
jusqu'à la première page affichée, temps d'image (médiane, p95) d'une animation de test dans
WebView2, `hiddenimports` et `datas` retenus, résultat des quatre vérifications de la fenêtre sans bordure (et repli éventuel) et décision sur la bibliothèque
d'animation.
