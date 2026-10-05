# SPEC-21 — Client LeagueStats : l'interface enhanced du client LoL

**Statut** : 🟡 **Réécrite le 2026-10-04** (la version « tableau de bord en lecture seule » est
remplacée). Forme, périmètre, ordre, temps réel et niveau d'écriture validés par @pj35 (§2). Tâche 48 (spike) faite le
2026-10-04, mesures en §8. Tâches 49 (socle), 68 (coque, mesures en §9) et 70 (bus, SSE, WebSocket LCU) faites le
2026-10-04 ; port libre choisi par l'OS validé. **Plan revu le 2026-10-05** à la réception du handoff de design « Alchimie »
(`docs/design/client_alchimie/`) : 37 tâches, et une fiche par écran à coder (§4.10, §5). **Validé le
2026-10-05** : ordre des lots, taille de la fenêtre, thème clair reporté, écrans sans maquette extrapolés
d'« Alchimie ». Point d'entrée validé le 2026-10-05. Reste à valider : les écritures du coaching.

**Origine** : feature candidate 5 du `TODO.md` (ex-tâche #6, `ROADMAP_2026.md` Horizon 3),
repriorisée le 2026-09-26. Reformulée par @pj35 le 2026-10-04 : « bien plus qu'un rapport HTML en
fin de partie […] l'équivalent de mon propre client, entièrement customisable, qui servirait
d'interface enhanced par mon moteur pour interagir avec le client de base. On y mettrait toutes
les features de navigation du client de base, mais en rajoutant une section complète sur le
coaching, et en revoyant la draft et le post-game avec le Live Coach. » Ajout le même jour :
**la qualité des animations est un objectif de premier rang** (motion design poussé, thèmes à
discuter avec @pj35).

**Effort** : ~33 jours, 37 tâches, 163 pts, en six lots utilisables chacun seuls (§5) ; 25 pts
faits (tâches 48, 49, 68, 69, 70).

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
| Motion design | **Objectif de premier rang (@pj35, 2026-10-04)** : système de motion dédié (§4.3), pas de décor ajouté en fin de chantier. Direction artistique **fournie le 2026-10-05** : thème « Alchimie » (grimoire d'alchimiste nocturne), handoff dans `docs/design/client_alchimie/` (§4.10). |
| Reprise du design | **Validé (@pj35, 2026-10-05)** : les écrans sont **recréés** en gabarits Jinja, CSS statique et JS vanilla ; aucun HTML des prototypes `*.dc.html` n'est copié, `support.js` n'est pas porté. `motion.js` est repris presque tel quel dans `static/` (contrat des attributs `data-*`). Polices **embarquées** en woff2 (Cormorant Garamond, Alegreya Sans, Noto Sans Runic, licence OFL) : aucun appel à Google Fonts à l'exécution, l'interface marche hors ligne. |
| Thème clair | **Validé (@pj35, 2026-10-05)** : le handoff ne définit que « Alchimie » (sombre) et @pj35 retravaillera le design plus tard. Le client livre ce seul thème ; le clair est reporté et rouvert avec ses maquettes (les variables CSS ne l'interdisent pas) ; le réglage « Thème » de la navigation affiche « Alchimie » en lecture seule. Lève « un thème sombre et un clair » de la version du 2026-10-04. |
| Ordre des lots | **Validé (@pj35, 2026-10-05)** : le handoff conseille coque, motion, draft, file trouvée et transition, puis post-game et écrans du coaching. Les lots sont réordonnés dans cet esprit (§5). La règle « coaching, draft et post-game d'abord » reste vraie, seule la séquence interne change ; la draft passe avant le coaching parce que c'est l'écran clé et celui qui sollicite le plus le motion. |
| Assets de la draft | **Défaut proposé** : Data Dragon (portraits, runes, sorts, objets, skins) servi par le serveur local depuis un cache disque ; version lue dans la config (14.24.1 dans le prototype, à remplacer par la version du client). Hors ligne, le cache seul répond ; une icône absente rend un emplacement neutre. |
| Écrans sans maquette | **Validé (@pj35, 2026-10-05)** : Parties, Calibration, Profil, Collection, Lobby, Social, la variante Défaite du post-game et les états vides sont **extrapolés** du système « Alchimie » (jetons, cartes, grilles, courbes) sur le modèle des écrans définis, sans validation préalable. Si une direction manque vraiment, Claude s'arrête et le signale : @pj35 fait alors une pause pour retravailler le design. |
| Bibliothèque d'animation | **Tranché par le spike (tâche 48, 2026-10-04)** : CSS + Web Animations API + View Transitions, zéro dépendance. WebView2 est un Chromium 154 qui expose les View Transitions ; 80 cartes animées plus un tracé SVG tiennent un p95 de 6,2 ms par image (§8). Un moteur de ressorts n'est justifié par aucune mesure ; à rouvrir seulement si un effet précis l'exige. Le handoff (2026-10-05) ajoute un calque `<canvas>` de particules (1 600 au plus, braises continues) : **non mesuré à ce jour**, la tâche 84 consigne le p95 sur le banc `/_motion` ; leviers de repli au README du handoff (plafond, débit des braises, plume de tracé). |
| Cadre de la fenêtre | **Validé (@pj35, 2026-10-04) : sans bordure** (`frameless=True`), barre de titre et boutons Réduire/Agrandir/Fermer dessinés en HTML et animés. **Confirmé par le spike** sur le poste de @pj35 (§8) : déplacement par la barre de titre exact, redimensionnement par la poignée d'angle bas-droit exact (aller-retour JS vers Python : 0,7 ms), coins arrondis et bordure fournis par Windows 11. **Deux écarts à traiter en tâche 68** : le bouton Agrandir ne doit pas appeler `maximize()` (la fenêtre recouvre la barre des tâches), il place la fenêtre sur la zone utile de l'écran ; et il n'y a aucun redimensionnement natif par les bords (poignées HTML sur les quatre côtés et quatre coins ; **seuls le coin bas-droit et les bords droit et bas ont été essayés** : gauche et haut exigent `resize()` puis `move()` synchronisés, risque de saut, à mesurer en tâche 68). L'ancrage Win+Flèche est sans objet : @pj35 utilise Komorebi (gestionnaire de fenêtres en mosaïque, dont les barres expliquent la zone utile de 46 à 1032 px), et prévoit un usage surtout en plein écran ; il n'est pas critique (2026-10-04). |
| Écritures du coaching dans la base | **À valider** : défaut proposé, oui, via une connexion d'écriture distincte et les repositories existants (fixer ou clore un axe, `outcome`) ; la lecture reste en `mode=ro`. Cela lève la règle « lecture seule » de la version précédente. |
| Point d'entrée | **Validé (@pj35, 2026-10-05)** : `python lol_coach.py --client` et option 7 du menu ; démarrage d'office du client plus tard. |
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
| `assets.py` | Data Dragon local : version configurable, cache disque, route `/assets/...` (portraits, runes, sorts, objets, skins), `runesReforged.json` ; best-effort (tâche 86). |
| `templates/`, `static/` | Coque, une page par écran (§4.10), `htmx.min.js` épinglé, `style.css` (jetons « Alchimie »), `motion.js` (repris du handoff), `shell.js`, `fonts/`, un module JS par écran qui a du comportement (`draft.js`, `champions.js`, `runes.js`, `found.js`). |

### 4.3 Thème et motion design

Le motion est un **système**, pas des effets : tout passe par des jetons.

- **Jetons** (`config_client.py` et variables CSS) : durées (`instant`, `rapide`, `normal`,
  `lent`), courbes (`standard`, `entrée`, `sortie`, ressort), échelons de décalage (`stagger`),
  distances. Un thème surcharge couleurs, police, rayons, ombres **et** le caractère du motion
  (vif ou posé). Aucune valeur de durée en dur dans un gabarit.
- **Primitives** (`static/motion.js`, 340 lignes reprises du handoff, contrat `data-*` inchangé, vérifiées à la main sur le banc `/_motion`) : `data-trace` (tracé SVG avec plume d'étincelles), `data-rise`, `data-pop`, `data-fade`, `data-spell` (runes vers lettres), `data-count`, `data-spin`, `data-glow`, `data-tilt`, puis `Motion.seal` (sceau apposé), `impact` (image de choc adoucie), `burst`, `converge`, `embers`, `shake`, `flash`. Seul ajout : `Motion.opts()`, qui lit le réglage Motion de `<html data-motion>`. Les moments signature (transition de page, partie trouvée, sceau, ban, courbes) sont décrits au README du handoff et réalisés par les tâches 87, 88, 93, 94 et 95.
- **Contraintes de performance** : animer uniquement `transform` et `opacity` (compositeur) ;
  budget 16,7 ms par image mesuré au spike et sur le banc ; aucune animation ne bloque une
  interaction (annulable, jamais modale) ; **`prefers-reduced-motion`** respecté **avec un réglage de remplacement dans le client** (Système / Complet / Réduit, mémorisé dans `user_prefs.json`) : sur le poste de @pj35, Windows a les animations désactivées (`SPI_GETCLIENTAREAANIMATION` = 0) et WebView2 annonce `reduce` (§8) ; un client qui suivrait aveuglément le système n'animerait rien. Défaut proposé : Complet (**à valider**). Durées
  quasi nulles, jamais d'effet seul porteur d'information).
- **Où le motion compte** : l'entrée dans la draft (picks qui se posent, rôles qui se résolvent,
  recommandation qui change), la file trouvée, la révélation du post-game (courbe de win chance
  qui se trace, impact par événement qui s'empile), les transitions entre sections.
- **Thème** : variables CSS dans `style.css` (jetons du README du handoff : fonds, texte, accents et leurs complémentaires, arbres de runes, teinte par rôle, ombres), couleurs en OKLCH. Un seul thème, « Alchimie » ; un thème clair serait un second fichier de variables (`static/themes/<nom>.css`), à rouvrir avec ses maquettes (§2). Le réglage Motion est mémorisé dans `user_prefs.json` (clé `motion`, hors de `UserPrefs` : `save_user_prefs` la reporte quand le Live Coach réécrit le fichier, et un fichier créé par le seul client laisse le Live Coach poser ses questions habituelles).

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

### 4.5 Draft interactive et post-game (lots 2 et 4)

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

### 4.6 Navigation (lots 5 et 6)

| Lot | Écran | Source LCU | Écriture |
|---|---|---|---|
| 5 | Profil, rang, régalia, défis | `lol-summoner`, `lol-ranked`, `lol-regalia`, `lol-challenges` | non |
| 5 | Historique et détail de partie (20 parties au plus, limite du LCU ; les parties capturées ajoutent la timeline et l'impact) | `lol-match-history` | non |
| 6 | Collection : champions possédés, pages de runes, sets d'items | `lol-champions`, `lol-perks`, `lol-item-sets` | non (l'import de SPEC-15 reste son propre chemin) |
| 6 | Lobby : files (`lol-game-queues`), postes, membres | `lol-lobby/v2` | **oui** : créer, choisir file et postes, quitter |
| 6 | File : recherche, annulation, acceptation | `lol-matchmaking` | **oui** : lancer, annuler, accepter |
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
- `LeagueStatsCoach.spec` : `datas` pour `src/client/templates` et `static` ; **aucun** `hiddenimports`
  pour `uvicorn` ni `pywebview` tant que le code les importe (spike, §8). WebView2 est présent sous Windows 11 ;
  son absence déclenche le repli navigateur et un `[ALERTE]`.
- Gabarits et statiques résolus par `config.get_resource_path()`, jamais par chemin relatif.

### 4.9 Tests

Hermétiques (`temp_db`, `tmp_path`, faux `LCUClient`), `TestClient` sur `create_app(...)` : chaque
route répond 200 sur base remplie **et** vide, et « indisponible » sans LCU ; `charts.py`,
`data.py`, `bus.py`, `lcu_proxy.py` testés sans serveur ; le WebSocket testé sur un faux serveur
local ; `server.start()` sur un port libre avec `stop()`. Le motion n'est pas testable en pytest :
il se vérifie sur le banc `/_motion` et à la recette (§6, 10 et 11).

### 4.10 Design « Alchimie » et écrans à coder

Source : `docs/design/client_alchimie/` (`README.md` : jetons, positions, états, motion, sources de
données ; `*.dc.html` : prototypes, ouvrables avec `python -m http.server` dans ce dossier). Haute
fidélité : couleurs, polices, tailles, textes et animations sont définitifs ; **les données des
prototypes sont fictives** (pool GRIND, Sion contre Darius, LP, skins possédés simulés).

**Règles de traduction** (valent pour toutes les tâches d'écran)

- Un écran = un gabarit Jinja, des classes dans `style.css` et au plus un module JS vanilla ; pas de
  style inline, sauf une valeur que la donnée calcule (teinte, pourcentage, position).
- Chaque bloc nomme sa source de données (tableau ci-dessous) ; aucune valeur de prototype en dur.
- Rafraîchissement par zone : un fragment htmx par zone, rechargé sur l'événement du bus (SSE) plutôt
  que par écran entier ; sur `htmx:load`, `Motion.intro` puis `Motion.ambient` rejouent les animations
  du fragment, sauf en mode Réduit.
- Accessibilité : les runes sont décoratives (`aria-hidden`), jamais seules porteuses de sens ; le sens
  passe par le texte ; Échap ferme les overlays.
- Chaque écran a son état vide, et les états « client LoL fermé » et « base occupée » de la coque.
- **Taille de la fenêtre** (**validé, 2026-10-05**) : le handoff est dessiné à 1920×986 et la fenêtre s'ouvre à
  1280×800 (`WINDOW_SIZE`). Décision : les écrans du coaching sont fluides (colonne principale
  souple, colonne latérale de 440 px) ; la draft garde les positions et tailles du handoff et se met à
  l'échelle (`transform: scale()`) sous 1920×986. À régler sur ta fenêtre réelle (Komorebi, usage surtout
  en plein écran).

**Vue d'ensemble**

| Écran | Route et fragments | Données | Tâches |
|---|---|---|---|
| Coque | `base.html`, `partials/nav.html` ; `POST /prefs/motion` | `user_prefs.json`, `LcuProbe` | 69, 84, 94 |
| Accueil | `/` ; `/accueil/axes` (+ écritures si validées) | `coaching/goals.py`, `findings.py`, `progression.py`, `rank_snapshots`, `game_records` | 71 |
| Rang | `/rang` | `coaching/ranked.py` (`lp_scale`), `rank_snapshots` | 51 |
| Progression | `/progression?role=` | `coaching/grid.py`, `metrics.py`, `progression.py` | 52 |
| Draft | `/draft` ; fragments `/draft/sceaux`, `/draft/bans`, `/draft/rangee`, `/draft/loadout`, `/draft/champions`, `/draft/runes` ; `POST /draft/action/...` | `DraftSnapshot`, `draft/recommendations.py`, `analysis/ban_recommendations.py`, `winprob/`, `draft/loadout.py`, LCU `lol-champ-select`, `lol-champions`, `lol-perks` | 72–74, 85–92 |
| File trouvée | overlay de la coque, déclenché par la phase gameflow `ReadyCheck` | LCU ready-check, auto-accept du Live Coach (`user_prefs`) | 93 |
| Transition de page | `shell.js` (navigation htmx) | — | 94 |
| Post-game | `/postgame` (dernière partie capturée) et `/parties/{id}` ; événement `game_captured` | `winprob/report.py`, `winprob/impact.py`, `coaching/findings.py`, `goals.judge`, `rank_snapshots` | 75, 95 |
| Parties, Calibration, Profil, Collection, Lobby, Social | sans maquette (§2) | §4.4 et §4.6 | 53, 54, 77–82 |

**Fiches** (les cotes et positions exactes sont au README du handoff, section de l'écran)

- **Coque (69, 84, 93, 94).** Barre de titre de 36 px : logo en pentacle, pastille « Client LoL
  connecté / fermé » au point pulsé, boutons de 46 px (fermer rouge au survol), liseré dégradé cuivre →
  violet → menthe → magenta. Zone centrale : « Champ select en cours » (93) ; « Lancer la file »,
  recherche et « Annuler » viennent avec la tâche 81 (écriture lobby et file). Navigation de 220 px en
  trois groupes (Coaching, Partie, Client), une rune décorative par entrée, entrée active teintée,
  entrées sans écran grisées (info-bulle « lot suivant »), masquée pendant la draft. Pied : Thème
  (« Alchimie », lecture seule) et Motion (Système / Complet / Réduit, mémorisé). Défaut Complet : Windows
  annonce `reduce` sur le poste de @pj35.
- **Accueil (71).** En-tête « Coaching · rôle principal X » et état de la base ; deux cartes d'axe
  (violet, bleu) : origine (proposé par le coach / fixé par toi), métrique, rôle et cible, cinq pastilles
  tenu / non tenu, « Tenu x fois sur les 5 dernières », « Clore l'axe » ; place libre : proposition
  (`goals.propose`), « Fixer cet axe », « Choisir une autre métrique ». Tableau des derniers constats
  (Métrique / Toi / Norme · objectif / Écart / σ, barre divergente centrée sur la norme). Colonne
  latérale : carte Rang et sparkline sur 30 jours, 10 dernières parties en portraits cerclés, bilan du
  rôle. États : sans axe, sans partie capturée, base vide. Fixer et clore écrivent en base (§2, à valider).
- **Rang (51).** Courbe de 1124×560 sur l'échelle continue de `lp_scale()` (100 LP par division),
  libellés de paliers à gauche, bandes de fond Platine / Émeraude, séparation or à 400 ; Solo en dégradé
  bleu → vert avec aire, Flex violet → magenta, dernier point lumineux et étiquette « Émeraude II · 47 LP » ;
  histogramme divergent des LP des 20 dernières parties ; cartes par file (palier, LP en compteur, V / D /
  taux de victoire, delta sur 30 jours). Sous 2 photos, une file n'a pas de courbe : « pas assez de photos ».
- **Progression (52).** Puces de rôle (teinte par rôle, nombre de parties) ; grille du rôle, une ligne par
  métrique de `coaching/grid.py` : losange coloré, poids (●● principal, ● secondaire), Toi, Norme,
  Objectif, tendance (sparkline de 190×40 : z face à la norme en plein, face à l'objectif en pointillé),
  verdict en progrès / en recul / stable. Sous `MIN_TREND_SAMPLE` (5) : pas de verdict, pastille en
  pointillé « n/5 parties, pas de verdict ». Colonne latérale : échantillon, schémas de `patterns()`
  (pentacle coloré et phrase), légende.
- **Draft, cadre et sceaux (73).** Plein écran sans navigation (la navigation revient en glissant à la
  sortie). En-tête : fil d'Ariane, titre qui se transmute (runes → lettres), chrono circulaire de 64 px,
  bans alliés et adverses (pastilles de 32 px barrées). Sceaux d'équipe : deux anneaux tournants (160 s,
  sens opposés), pentacle de rayon 190, un rôle par branche, portraits de 92 px ; moi à la pointe haute
  (104 px, cercle pointillé tournant tant que je ne suis pas verrouillé) ; adversaire inconnu : cercle
  pointillé rose et rune ᛃ pulsée. Balance : jauge verticale de 46×270 (menthe → bleu pour nous, magenta
  pour eux, curseur or), pourcentage de 58 px animé sur 800 ms, note « si X est verrouillé ». Écoute le
  bus par `fetch` avec jeton (`EventSource` n'envoie pas d'en-tête) et recharge le fragment concerné.
- **Draft, bans (87).** Mon ban : pastille de 40 px, bordure magenta en pointillé lumineux, aperçu de la
  cible à 50 % ; bans adverses cachés (ᛜ). Rangée basse « Bans conseillés · menaces pour ton pool » : 4
  cartes (« +2,9 pts si banni » et justification, de `BanRecommender`). Bouton principal « Bannir X »
  (magenta). Après le ban : tampon, explosion magenta, 1,1 s plus tard révélation des bans adverses en
  cascade (120 ms) puis apparition des picks adverses (150 ms), puis phase de picks.
- **Draft, picks (88).** 4 cartes de recommandation (lien de couleur en haut : or, menthe, bleu, violet) :
  portrait, nom, parties, win % à 2 décimales, delta en points (menthe ou rose), « Suite attendue : … ».
  Clic = survol (LCU, garde de phase et de tour) ; « Verrouiller X » en haut à droite de la rangée. Survol :
  éclosion du portrait et 26 runes qui convergent. Verrouillage : sceau apposé (impact frame, 170
  étincelles, secousse).
- **Draft, grimoire des champions (89).** Overlay de 1480×950, ouvert par « Tous les champions », mon
  portrait ou mon emplacement de ban : recherche sans accents, puces de rôle (Top par défaut), « Pool
  GRIND uniquement », compteur ; grille de portraits de 76 px ; tri recommandations, pool, alphabétique ;
  méta (win %, « pool », « +x pts » en ban), losange or du pool ; indisponibles à 40 %, en gris, barrés, avec
  leur raison (banni / allié / adverse / intention alliée / ton intention) ; barre basse (sélection,
  « Double-clic pour … », « Fermer », action). Échap ferme.
- **Draft, skins (90).** Après le verrouillage, la rangée basse devient la sélection de skin : cartes de
  104×188 (art de chargement, nom, cadenas et gris si non possédé, losange or si choisi), splash du skin
  choisi en fond (opacité 0,24, masque radial), « n skins possédés sur m ». Possession lue dans le LCU
  (le prototype la simule) ; le choix s'écrit dans le champ select.
- **Draft, loadout (91).** Colonne de 440 px : carte de page de runes teintée par l'arbre principal (rune
  majeure de 72 px, 3 de 44 px, arbre secondaire 2 de 36 px, fragments, « Modifier › ») ; sorts
  d'invocateur (tuiles D et F, popover de 9 sorts, « Échanger D ⇄ F », choisir un sort déjà pris échange les
  deux) ; objets en lecture seule ; pied : note d'état, « Envoyer au client », « Rétablir OneTricks »,
  pastille « Modifiée à la main ». **La modification manuelle prime sur l'import automatique** du
  lock-in (SPEC-15, ADR-003) : le drapeau vit dans le snapshot et l'import le respecte.
- **Draft, éditeur de runes (92).** Overlay ouvert par un clip-path circulaire, runes qui éclosent en
  cascade : arbre principal (majeure + 3 rangées), arbre secondaire (2 runes de rangées différentes ; une
  troisième rangée remplace la plus ancienne), fragments (3 rangées), « Annuler » / « Appliquer la page ».
  Les chemins de runes écrits à la main dans le prototype sont validés contre `runesReforged.json` (86).
- **File trouvée (93).** Overlay de la coque : fond radial sombre, pilier de lumière, cercle de 720 px
  (anneau runique de 60 s, pentacle menthe, pentacle inversé magenta de −90 s), anneau de compte à rebours
  de 10 s, « Partie trouvée » / « n s pour répondre », « Accepter » (menthe) et « Refuser ». Auto-accept du
  Live Coach (acceptation à 4 s) signalé s'il est actif. Acceptation : « Acceptée », grosse explosion, éclair,
  secousse de 16 px, anneaux ×9, effondrement `scale(.2) rotate(160deg)` vers la draft.
- **Transition de page (94).** Le contenu s'assombrit (560 ms) pendant qu'un cercle runique de 520 px se
  trace et que 44 runes convergent ; implosion (860 ms), explosion, éclair cuivre, secousse de 8 px,
  ouverture par `clip-path: circle()` de 0 à 75 % (820 ms). Mode Réduit : changement instantané.
- **Post-game (75, 95).** Sceau de victoire de 104 px (menthe), titre « Victoire » de 64 px, contexte
  (champion, matchup, durée, file) ; axes tenu / non tenu ; gain de LP en compteur (dégradé or → menthe) ;
  courbe de win chance de 1124×430 tracée à l'encre (dégradé bleu → violet → menthe → or), marqueurs par
  type (Baron violet, tour or, dragon orange, larves violet, héraut bleu, kill menthe, mort rose) ; « Les
  plus coûteux » et « Les plus rentables » (3 lignes chacun) ; colonne : impact par événement (ΔP de
  l'équipe, barres divergentes, « toi » pour les miens), impact attribué et résidu, écarts à la norme et à
  l'objectif. Sans impact : « impact non calculé », courbe affichée si la timeline existe. **La variante
  Défaite n'est pas maquettée** : défaut proposé, même mise en page, sceau et titre en rose.
- **Sans maquette (53, 54, 77–82).** Parties, Calibration, Profil, Collection, Lobby, Social : même
  système (cartes de 6 px, grilles, courbes de `charts.py`), extrapolés sans validation préalable (§2) ; une
  direction manquante est signalée avant de coder.

## 5. Tâches

Numéros à la suite du `TODO.md` (dernière : 67). Les tâches 48 à 56 et 68 à 83 viennent des versions du
2026-10-04 ; **84 à 95 sont ajoutées le 2026-10-05** après le handoff de design. L'ordre d'exécution est
celui des lots, **réordonnés d'après le handoff** (§2, à valider) : coque, motion, draft, file trouvée et
transition, coaching et post-game, puis la navigation. Les tâches d'écran renvoient à leur fiche du §4.10.
Les tâches 48, 49, 55, 68, 69, 70 et 84 sont faites (84 : la mesure du p95 reste à la recette).

**Lot 1 — Socle, coque et motion (31 pts)** — étapes 1 et 2 du handoff

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 48 | ✅ **Spike d'empaquetage et de fluidité** : fenêtre `pywebview` servie par `uvicorn` depuis l'exe, une animation de test ; `hiddenimports` et `datas` trouvés ; taille, délai de démarrage et temps d'image mesurés et consignés (§8) ; vérifie les quatre points de la fenêtre sans bordure (§2) et tranche la bibliothèque d'animation | 5 | — |
| 49 | ✅ Socle : `config_client.py`, `db.py` (lecture seule), `server.py` (fil, idempotent, best-effort), `app.py` (fabrique), jeton de session et contrôle `Host`/`Origin` + tests | 5 | 48 |
| 68 | ✅ Coque : `window.py`, barre de titre maison (déplacement, poignées de redimensionnement, boutons animés), `base.html`, navigation par sections, transitions de page, états « client LoL fermé » et « base occupée » | 5 | 49 |
| 70 | ✅ Bus et temps réel : `bus.py`, route SSE, `lcu_events.py` (WebSocket LCU, reconnexion), faux serveur de test | 5 | 49 |
| 69 | ✅ **Jetons, polices et coque « Alchimie »** : jetons OKLCH et `@font-face` locaux dans `style.css` ; `base.html` (barre de titre : logo pentacle, pastille animée, liseré dégradé) ; navigation à trois groupes, entrées sans écran grisées ; pied Thème / Motion ; réglage Motion persisté (`save_motion`, `POST /prefs/motion`, `data-motion` sur `<html>`) ; `WINDOW_BACKGROUND` ; tests | 5 | 68 |
| 84 | 🟡 **`motion.js` et banc `/_motion`** (`motion.js` repris et branché le 2026-10-05 ; reste le banc et la mesure) : reprise de `motion.js` du handoff (+ `Motion.opts()`), `Motion.intro` et `ambient` sur `htmx:load`, braises coupées en Réduit ; banc `/_motion` (p95 du temps d'image par scène : braises, 1 600 particules, tracé, sceau) ; mesures consignées en §10 | 3 | 69 |
| 55 | ✅ Lancement : `--client` et option 7 du menu (Quitter en 8), Live Coach en fil sans entrée console, message `[INFO]`/`[ALERTE]` + tests | 3 | 49, 70 |

**Lot 2 — Draft Alchimie (51 pts)** — étape 3 du handoff, l'écran clé

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 72 | ✅ `DraftSnapshot` et recommandations structurées (phase, tour, picks et bans par camp, recommandations `{champion, score, delta, profondeur, variation, parties, suite attendue}`, écartés et raison, état du loadout) ; sortie console **identique** (test d'identité) ; publication best-effort sur le bus | 5 | 70 |
| 85 | ✅ Bans conseillés et balance dans le snapshot : `BanRecommender` structuré (gain en points, justification), win chance de fin de draft et « si X est verrouillé » (`winprob`) | 3 | 72 |
| 86 | ✅ Assets et formes LCU de la draft : `assets.py` (Data Dragon local, version configurable, cache disque, `/assets/...`, `runesReforged.json`) ; relevé des formes LCU en lecture seule (skins possédés, pages de runes, sorts, actions et bans du champ select) figées en `tests/fixtures/` | 5 | 49 |
| 74 | ✅ Actions de draft : survoler, verrouiller, bannir, corriger un rôle ; garde de phase et de tour ; refus lisible sans appel LCU ; tests avec faux LCU | 5 | 72 |
| 73 | ✅ Draft, cadre : gabarit plein écran sans navigation, en-tête, sceaux d'équipe, balance, chrono, consommateur SSE (`fetch` avec jeton), fragments rechargés sur le bus | 5 | 72, 84, 86 |
| 87 | ✅ Draft, phase de bans : mon ban, aperçu, bans cachés, « Bans conseillés », « Bannir X », tampon, révélation en cascade | 5 | 73, 74, 85 |
| 88 | ✅ Draft, phase de picks : 4 cartes de recommandation, survol (éclosion, runes), « Verrouiller X », sceau apposé | 5 | 73, 74 |
| 89 | ✅ Draft, grimoire des champions : overlay, recherche sans accents, rôle, pool, tri, indisponibles et raison, barre basse | 5 | 88 |
| 90 | ✅ Draft, sélection de skin : rangée basse après verrouillage, possession lue dans le LCU, splash en fond, écriture du choix | 3 | 86, 88 |
| 91 | Draft, colonne loadout : page de runes, sorts (popover, échange), objets, « Envoyer au client », « Rétablir OneTricks », « Modifiée à la main » qui prime sur l'import | 5 | 86, 88 |
| 92 | Draft, éditeur de runes : overlay circulaire, arbres, secondaire sur deux rangées, fragments, appliquer / annuler | 5 | 91 |

**Lot 3 — File trouvée et transition de page (8 pts)** — étape 4 du handoff

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 93 | **File trouvée** : overlay de la coque sur la phase `ReadyCheck`, compte à rebours de 10 s, accepter / refuser (LCU, avec jeton), mention de l'auto-accept, effondrement vers la draft ; « Champ select en cours » dans la barre de titre ; tests avec faux LCU | 5 | 84, 55 |
| 94 | **Transition de page signature** : cercle runique, runes, implosion, clip-path ; remplace le fondu de View Transitions ; la navigation glisse à la sortie de la draft ; Réduit = instantané ; jamais de clic perdu | 3 | 84, 73 |

**Lot 4 — Coaching et post-game (39 pts)** — étape 5 du handoff

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 50 | `charts.py` : `line_chart`, `reliability_chart`, `bar_chart`, barres divergentes, sparklines, bandes de paliers ; échelles, axes, accessibilité, tracé à l'encre animable + tests sur le SVG | 5 | 84 |
| 51 | Écran Rang : `data.rank_series()`, courbes Solo et Flex, histogramme des LP, cartes par file, ignorance visible + tests | 5 | 50 |
| 52 | Écran Progression : `data.metric_series()`, puces de rôle, grille, verdicts, schémas, seuils d'échantillon + tests | 5 | 50 |
| 53 | Écran Parties : `winprob.report.curve_points()` extraite, liste, page d'une partie, états vides + tests (sans maquette) | 5 | 50 |
| 54 | Écran Calibration : `analysis.calibration.calibration_buckets()` extraite, diagramme de fiabilité, choix de version + test d'identité de `calibration_curve()` (sans maquette) | 3 | 50 |
| 71 | Accueil Coaching : axes, constats, colonne latérale ; fixer / clore un axe (si écriture validée) + tests | 5 | 51–53 |
| 75 | Post-game, données et page : événement `game_captured`, `/postgame` et `/parties/{id}` en mode revue, impact, constats, LP, objectif jugé, variante Défaite | 5 | 72, 53 |
| 95 | Post-game, mise en scène : sceau de victoire, courbe de win chance à l'encre, marqueurs, impact empilé, compteurs | 3 | 75, 84 |
| 56 | Empaquetage : `requirements*.txt`, `.spec` (`templates`, `static`, `fonts`), `build_app.py`, job `build` de la CI, exe vérifié, `README.md`, `docs/PROJECT_STRUCTURE.md`, `CHANGELOG.md` | 3 | 55, 71, 75, 92 |

**Lot 5 — Profil et historique (13 pts)**

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 76 | **Spike des endpoints de navigation** : formes relevées sur le client de @pj35 pour les lots 5 et 6, fixtures, corrections de §4.6 | 3 | 70 |
| 77 | Profil, rang, régalia, défis (sans maquette) | 5 | 76 |
| 78 | Historique (20 parties) et détail ; liaison aux parties capturées (sans maquette) | 5 | 76, 53 |

**Lot 6 — Collection, lobby, file, social et clôture (21 pts)**

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 79 | Collection : champions possédés, pages de runes, sets d'items (lecture) | 5 | 76 |
| 80 | Lobby : files, postes, membres ; créer, choisir, quitter | 5 | 76 |
| 81 | File : lancer, annuler, accepter ; barre de titre (« Lancer la file », recherche, chrono, « Annuler ») ; cohabitation avec l'auto-accept du Live Coach | 5 | 80, 93 |
| 82 | Social en lecture seule : amis, statuts, conversations | 3 | 76 |
| 83 | Clôture : exe vérifié, `README.md`, `docs/PROJECT_STRUCTURE.md`, `CHANGELOG.md`, statuts, `TODO.md` | 3 | 56, 77–79, 81, 82, 95 |

Total : 31 + 51 + 8 + 39 + 13 + 21 = **163 pts**, 37 tâches, dont 25 pts faits. Chaque lot se clôt par
une recette de @pj35 (§6, 10).

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
    clic, revue de partie) ; chaque écran comparé à son prototype (`docs/design/client_alchimie/`), thème « Alchimie » lisible à 1280×800 et à 1920×986. Reste ⬜ dans le `TODO.md` tant qu'elle
    n'est pas faite.
11. **Motion** : sur le banc `/_motion` et sur les écrans de draft et de post-game, **p95 du temps
    d'image ≤ 16,7 ms** (calque de particules et braises compris) sur le poste de @pj35 (mesure consignée en §8) ; en mode Système ou Réduit,
    `prefers-reduced-motion: reduce` coupe les animations non essentielles, en mode Complet elles
    tournent quel que soit le système ; aucune animation ne retarde une action.
12. Mesures du spike (tâche 48) consignées en §8 : taille de l'exe avant/après, délai de démarrage,
    temps d'image.
13. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec, `docs/specs/README.md` et `TODO.md` à jour.
14. **Design** : aucun `*.dc.html` ni `support.js` sous `src/client/` ; polices servies par `/static/fonts/`
    et aucun gabarit n'appelle un domaine externe (test) ; les jetons de couleur du README du handoff sont
    dans `style.css` (test) ; `<html data-motion>` reflète `user_prefs.json`, `POST /prefs/motion` répond
    403 sans jeton et 400 sur une valeur inconnue (tests).

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
- ❌ **Thème clair** : reporté, le handoff ne le définit pas (§2, validé).
- ❌ **Vitesse du motion réglable** (prop `speed` du prototype) : multiplicateur fixé à 1, pas d'interface.
- ❌ **Chaîne de build front** (Node, React, Svelte) : écartée (§3).
- ❌ **Accès réseau** (autre machine, mobile) et authentification : `127.0.0.1` seulement.
- ❌ **Réécriture des sorties console** : `report.py`, `calibrate_model.py` et l'affichage de draft
  restent, le client s'y ajoute.
- ❌ **Automatiser le jeu** : le client agit sur la draft, le lobby et la file à la demande de
  @pj35 ; rien dans la partie elle-même.

## 8. Mesures du spike (tâche 48, 2026-10-04)

Poste de @pj35 (Windows 11, écran 1920×1080 à ~164 Hz, Python 3.13.15, `pywebview 6.2.1`,
`pythonnet 3.2.0`, WebView2 = Chromium/Edge 154). Prototype : `scripts/spike_client_window.py` et
`scripts/spike_client_page.html` ; `python scripts/spike_client_window.py --auto --out r.json`
rejoue les mesures, sans argument il ouvre la fenêtre pour la manipuler à la main.

**Empaquetage** (PyInstaller 6.15, onefile, fenêtré)

| Mesure | Résultat |
|---|---|
| Exe du spike seul (FastAPI, uvicorn, pywebview, pythonnet, Pillow, psutil) | 43,99 Mo |
| Exe du produit avec les nouvelles dépendances (copie du `.spec`, chemins absolus, `hiddenimports=['fastapi','uvicorn','jinja2','sse_starlette','websockets','webview']` **seulement** pour les inclure, `lol_coach.py` ne les important pas encore) | **82 294 510 octets**, contre 75 064 370 le 2026-10-03 : **+7,2 Mo** (le `db.db` embarqué, 33,9 Mo aujourd'hui, a pu grossir entre-temps) |
| `hiddenimports` | **Aucun** pour `uvicorn` ni `pywebview` : l'exe du spike, qui les importe, tourne sans, grâce aux hooks de `pyinstaller-hooks-contrib`. Commande : `python -m PyInstaller --onefile --noconsole --add-data <abs>/spike_client_page.html;. --specpath build/spike scripts/spike_client_window.py`. |
| `datas` | `--add-data page.html;.` ; le gabarit se lit par `sys._MEIPASS` dans l'exe, `scripts/` sinon (même schéma que `config.get_resource_path()`). |
| `uvicorn` sans console | `log_config=None` obligatoire : `sys.stdout` vaut `None` dans un exe fenêtré et le logging d'`uvicorn` plante. |
| Chemins | Un `--specpath` sur un autre disque que les sources fait échouer PyInstaller (`relpath`) ; les `.spec` du projet restent sur `D:`. |

**Démarrage jusqu'à la première image** : source 1,8 s ; exe 2,0 à 2,5 s (6 exécutions : 2,01 à 2,18 s sauf une à
2,50 s ; dont 2,18 s au premier lancement d'un exe neuf). **Une première exécution d'un exe fraîchement
construit n'a jamais affiché la page** (40 s d'attente, non reproduite sur 6 exécutions dont un
autre exe neuf) : à surveiller à la recette.

**Temps d'image** (deux scènes de 3 s, ~495 images chacune)

| Scène | Médiane | p95 | p99 | Max | Images > 16,7 ms |
|---|---|---|---|---|---|
| 80 cartes en `transform` + `opacity` (source) | 6,1 ms | 6,2 ms | 6,2 ms | 18,2 ms | 1 (la première) |
| Tracé SVG (`stroke-dashoffset`) + compteur à chaque image (source) | 6,1 ms | 6,1 ms | 6,2 ms | 6,3 ms | 0 |
| Mêmes scènes dans l'exe | 6,1 ms | 6,2 ms | 6,2 ms | 12,1 ms | 0 |

Critère 11 tenu sur ces scènes (p95 ≤ 16,7 ms). Transition de page (View Transitions) : 260 à 327 ms,
durée de l'animation par défaut. Aller-retour JS vers Python (`pywebview.api`) : 0,7 ms.

**Fenêtre sans bordure** (mesurée sur la fenêtre réelle, glissements de souris synthétiques)

| Point | Résultat |
|---|---|
| Style Windows | ni `WS_CAPTION` ni `WS_THICKFRAME` ; `WM_NCHITTEST` répond « client » partout, y compris sur les bords : **aucun redimensionnement natif** |
| Déplacement par la barre de titre (`pywebview-drag-region`, `easy_drag=False`) | glissement de +150/+100 px : la fenêtre bouge de +150/+100 exactement |
| Redimensionnement par la poignée HTML d'angle bas-droit (les bords gauche et haut ne sont pas essayés) | glissement de +100/+60 : taille +100/+60 exactement |
| `maximize()` natif | rectangle 1920×1080, **recouvre la barre des tâches** (zone utile : 46 à 1032) |
| Placement sur la zone utile (`resize` + `move`) | rectangle exactement égal à la zone utile ; retour à la taille précédente exact |
| Coins et bordure | coins arrondis et bordure fine fournis par Windows 11 (`shadow=True`, défaut de `pywebview`) |
| Ancrage Win+Flèche gauche | sans effet ; non critique : @pj35 utilise Komorebi, qui gère l'ancrage, et vise un usage en plein écran |

Décision : **la fenêtre sans bordure est retenue**, avec les deux écarts de §2 à traiter en tâche 68.
Repli (fenêtre standard, option `--standard` du prototype) non nécessaire.

**Animations de Windows** : `prefers-reduced-motion: reduce` est vrai dans WebView2 sur ce poste
(`SPI_GETCLIENTAREAANIMATION` = 0, relevé par `windows_animations` du JSON). D'où le réglage de remplacement de §4.3.

**Prise en main par @pj35 (2026-10-04)** : faite. Déplacement, poignée d'angle et boutons conviennent ;
l'ancrage Win+Flèche marche mal à cause de Komorebi, sans conséquence. À garder en tête pour la
tâche 68 : sous Komorebi, la fenêtre peut être replacée par le gestionnaire ; le bouton Agrandir
(zone utile) reste valable, et un vrai plein écran (touche dédiée) peut s'ajouter si @pj35 le
veut.

## 9. Mesures de la coque (tâche 68, 2026-10-04)

Sondes sur la fenêtre réelle de la tâche 68 (échelle 100 %, zone utile 0,46 à 1920×986), événements
`pointer*` synthétiques envoyés aux poignées HTML, rectangle de la fenêtre relevé à chaque pas. Les
sondes ont été interrompues à la demande de @pj35 (le curseur partait en pleine partie) : toutes les poignées
ne sont pas couvertes.

| Geste | Résultat |
|---|---|
| Poignées gauche (`w`), haut (`n`), angles haut-gauche, haut-droit, bas-gauche | variation de taille exacte, **bord opposé fixe à chaque pas** (un seul `SetWindowPos`, `resize(fix_point=...)`) : pas de saut. Le risque du §2 est levé. |
| Poignée droite (`e`) | exacte, bord gauche fixe |
| Poignées bas (`s`) et angle bas-droit (`se`) | non rejouées ici ; même `fix_point` par défaut que `e`, angle bas-droit déjà mesuré au spike |
| Agrandir (bouton et double-clic sur la barre) puis Restaurer | rectangle exactement égal à la zone utile (0, 46, 1920, 1032 en bord), retour exact à la taille d'avant |
| Navigation htmx (`hx-boost`), titre, historique | l'écran change sans rechargement, titre à jour, un seul `#view` |
| Page d'erreur 503 (base occupée) échangée dans `#view` | affichée (réglage `responseHandling` de htmx) |
| Pastille « Client LoL fermé » | rafraîchie toutes les 5 s |

**Non vérifié** : le jeton de session sur une requête htmx `POST` (le serveur n'a pas vu la requête dans la
sonde interrompue) ; à contrôler à la recette.

