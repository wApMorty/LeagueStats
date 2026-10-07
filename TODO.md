# TODO — LeagueStats Coach

**Mis à jour** : 2026-10-07 (SPEC-25 : suivi de phase et capture de fin de partie)
**Source** : analyse d'état du 2026-09-05, vérifiée sur le code et la base de production.
Constats détaillés dans les specs elles-mêmes (`docs/specs/`). Historique complet : `docs/archive/`
(`AUDIT_2026_06.md`, `AUDIT_2026_08.md`, `BACKLOG_2026_08.md`, `specs/SPEC-01` à `SPEC-07`).

> **Le backlog SPEC-01 à SPEC-07 (coché soldé le 2026-09-01) avait un angle mort** : les items
> B2 ("lecture filtrée par lane") et D3 ("langue unifiée") étaient cochés faits alors que 4 zones
> du produit blendaient encore toutes les lanes (Live Coach fin de draft, bans, Team Builder,
> Tournament Coach) — corrigé le 2026-09-04, avec la CI (cassée par la migration lane du jour même)
> et l'hygiène du dépôt. Détail dans `CHANGELOG.md [Unreleased]`.
>
> **Un 5e résidu a été trouvé le 2026-09-05** : le « meilleur blind pick » du hover initial
> (`src/draft/automation.py`) scorait sur l'agrégat toutes-lanes, sur un chemin exercé à **chaque**
> draft (`user_prefs.json` porte `auto_hover: true`). Corrigé par SPEC-09 E3.

---

## Priorités actuelles — lot SPEC-14 → SPEC-17 (replanifié le 2026-09-24)

Besoin affiné avec @pj35 le 2026-09-23 : [SPEC-14](docs/specs/SPEC-14-draft-finale-head-to-head.md),
[SPEC-15](docs/specs/SPEC-15-import-runes-items.md), [SPEC-16](docs/specs/SPEC-16-moteur-optimisation-builds.md).
**Replanifié le 2026-09-24** après le spike OneTricks ([ADR-003](docs/adr/ADR-003-onetricks-temps-reel.md)) :
l'import prend la build OneTricks en temps réel (2 pages par draft, comme la recherche manuelle
de @pj35). La collecte par patch (`build_snapshots`) et SPEC-16 A+ sont **abandonnées**, tandis que
le spike Coachless et SPEC-16 A sont **reportés**.

**Estimation** en points Fibonacci (1 ≈ une heure, 3 ≈ une demi-journée, 5 ≈ une journée, 8 ou
plus = à redécouper avant de démarrer).

### Sprint 1 — Quick win et spike ✅ (2026-09-24)

| # | Tâche | Spec | Pts | État |
|---|---|---|---|---|
| 2 | Spike OneTricks : débit toléré, filtre par adversaire, historique | SPEC-15 §2.2.1 | 2 | ✅ OneTricks retenu en temps réel (ADR-003) |
| 7 | `GameEvaluator.has_matchup_data()` + tests | SPEC-14 §2.2 | 1 | ✅ |
| 8 | Tableau miroir ordonné par lane, colonne DUEL | SPEC-14 | 3 | ✅ |

### Sprint 2 — Import OneTricks dans le client (~18 pts) ✅ (2026-09-26)

**Objectif** : au lock-in, les runes, les items et les sorts les plus joués par les one-tricks
sont dans le client, puis affinés dès que l'adversaire direct est locké (seuls les composants
que le duel change significativement sont substitués), sans jamais
toucher aux pages ni aux sets du joueur.

| # | Tâche | Spec | Pts | Dépend de | État |
|---|---|---|---|---|---|
| 10 | `loadout.fetch_page()` + `pick_build()` : page OneTricks, `__NEXT_DATA__`, User-Agent navigateur, timeout, cache (champion, lane, adversaire), fixture enregistrée | SPEC-15 §3.1 | 3 | — | ✅ |
| 10b | `loadout.adapt_to_matchup()` : substitutions significatives du duel (test binomial, α dans `config_constants.py`), noms lisibles pour la console | SPEC-15 §3.2.1 | 3 | 10 | ✅ |
| 11 | `loadout.apply_build()` : page de runes `LS`, set d'items préservant ceux du joueur, sorts avec Flash sur sa touche habituelle | SPEC-15 §3.3 | 5 | 10 | ✅ |
| 12 | Déclenchement sur `completed: True` (et non sur `player_champion`), affinage au lock de l'adversaire direct via `adapt_to_matchup`, relance sur trade, flag `AUTO_IMPORT_LOADOUT` | SPEC-15 §3.2 | 3 | 10b, 11 | ✅ |
| 13 | Tests §3.5 (11 critères) | SPEC-15 §3.5 | 3 | 12 | ✅ |
| 14 | Recette en partie réelle : vérifier les corps de requête LCU contre le client (non documentés par Riot) | SPEC-15 §3.3 | 1 | 12 | ✅ Validée par @pj35 le 2026-09-26 |

### Sprint 3 — Recherche minimax plus pertinente et plus profonde (~12 pts) ✅ (2026-09-24)

**Objectif** ([SPEC-17](docs/specs/SPEC-17-recherche-plus-profonde.md), validée par @pj35 le
2026-09-24) : à budget constant (2 s, mono-thread), la recherche n'examine que des picks
réellement joués sur leur lane, atteint la fin de la draft dès B2 et une profondeur ≥ 5 en premier
pick (aujourd'hui 5 et 3). Indépendant du sprint 2 : peut démarrer sans attendre la tâche 14.

**Ordre** : le bench d'abord (il fournit la base de comparaison de chaque commit suivant), puis
les trois leviers, parallélisables entre eux, du moins risqué au plus structurant. Le calibrage de
`SEARCH_TOP_N` n'a de sens qu'une fois les trois leviers en place.

| # | Tâche | Spec | Pts | Dépend de | État |
|---|---|---|---|---|---|
| 21 | `scripts/bench_search.py` : scénarios B1/B2, copie temporaire de la base, `--budget`/`--top-n`, profondeur, nœuds/s, top 3, variante principale. Relever la base de référence avant tout changement | SPEC-17 §4.4 | 2 | — | ✅ Base : B1 3/10, B2 5/7, ~40 k nœuds/s |
| 22 | Cache des paires dans `GameEvaluator` (`matchup_logit`/`synergy_logit`, `dict` d'instance, invariant de durée de vie documenté) + tests | SPEC-17 §4.3, §4.5.4 | 2 | 21 | ✅ B1 4, B2 6 |
| 23 | Générateur par popularité : `MatchupsRepository.get_lane_popularity()` + délégué `db.py`, `CandidatePool._ranked()` basculé, docstrings et commentaire `SEARCH_TOP_N` + tests | SPEC-17 §4.1, §4.5.1 | 3 | 21 | ✅ |
| 24 | Lane des alliés : `PickTurn.lane`, renseignée par `DraftStateParser` depuis `ally_positions`, `_moves()` restreint à cette lane si libre (repli sinon) + tests | SPEC-17 §4.2, §4.5.2-3 | 3 | 21 | ✅ B1 5, B2 7/7 |
| 25 | Calibrer `SEARCH_TOP_N` (8 / 10 / 12) au bench, retenir le plus grand qui tient §2.2, consigner la couverture de games dans le commentaire | SPEC-17 §4.1 | 1 | 22, 23, 24 | ✅ N = 8 (10 et 12 : B2 6/7) |
| 26 | Critères d'acceptation §6 (bench B2 7/7, B1 ≥ 5, aucune variante hors top-N), `CHANGELOG.md`, statut de la spec | SPEC-17 §6 | 1 | 25 | ✅ |

### Lot en cours — SPEC-19, coach de gameplay (🟢 validée par @pj35 le 2026-09-26)

[SPEC-19](docs/specs/SPEC-19-coach-de-gameplay.md) : analyse de chaque partie SoloQ/Flex en fin de
partie (écarts à la norme et à l'objectif, par rôle), puis suivi de progression (schémas
récurrents, axes de travail). Source LCU seule, Live Client Data API plus tard, pas de clé API
Riot (@pj35). Tout est stocké après chaque partie (valeur brute, `z_norm`, `z_objective`) et
les LP sont suivis depuis le LCU. Découpage détaillé en SPEC-19 §11 (tâches 27 à 38, ~33 pts) :

| Phase | Contenu | Pts | État |
|---|---|---|---|
| 0 | Spike LCU : `scripts/spike_gameplay_dump.py`, résultats en SPEC-19 §3.4 | 2 | ✅ 2026-09-28 |
| 1 | Capture du brut en fin de partie et rattrapage au démarrage (**au plus tôt** : chaque partie non capturée est perdue), photos de classement (LP) | 7 | ✅ 2026-09-29 |
| 2 | Métriques des 10 participants, exploration (faite sur 24 parties, grille révisée en SPEC-19 §5.3) | 5 | ✅ 2026-09-29 |
| 3 | Grille par rôle, moteur de constats, rapport console | 8 | ✅ 2026-09-29 |
| 4 | Récurrence, tendances, axes de travail, bilan (commandes `bilan`, `axe`, menu 4) | 11 | ✅ 2026-09-29 |
| — | Recette en partie réelle : rapport de fin de partie, rappel d'axe en draft | 1 | ⬜ |
| — | Refaire l'exploration vers 50 parties (`scripts/explore_gameplay.py`), réviser la grille et `GRID_VERSION` | 1 | ⬜ |

### Lot suivant — SPEC-20, win chance et impact (🟡 rédigée le 2026-10-01)

[SPEC-20](docs/specs/SPEC-20-win-chance-et-impact.md) : modèle de win chance entraîné sur des
parties tierces collectées via le LCU (sondé le 2026-10-01 : historiques et timelines tiers
servis), impact de chaque événement attribué aux joueurs, puis overlay en jeu (Live Client API).
Répond à la confusion cause/effet des constats de SPEC-19. Ordre validé par @pj35, arbitrages
§2 à valider. Découpage en SPEC-20 §10 (tâches 39 à 47, ~30 pts) :

| Phase | Contenu | Pts | État |
|---|---|---|---|
| 1 | Collecte LCU continue en tâche de fond du Live Coach (`data/crawl.db`), une semaine de mesure | 6 | 🟡 tâche 39 faite (2026-10-02), reste la semaine de mesure (tâche 40) |
| 2 | État de partie, modèle logistique, calibration, réentraînement déclenché par les données | 10 | 🟡 tâches 41, 42 et 42b faites (2026-10-02) ; critère du §11.2 tenu à 5 300 parties (Brier 0,155, écart 2,3 pts en validation croisée poolée, 3,3 pts en découpage temporel ; protocole à confirmer, SPEC-20 §4.3 bis) ; reste à brancher le réentraînement au Live Coach (processus détaché, `.exe` figé à trancher) |
| 3 | Impact par événement, rapport de fin de partie | 7 | ✅ tâches 43 et 44 (2026-10-02, `impact.py`, `report.py`, migration `c8f3a1d95e26`) ; reste la recette en partie réelle |
| 4 | Impact dans le bilan et les schémas de SPEC-19 | 3 | ✅ tâche 45 (2026-10-02, section du bilan : impact par partie et par type d'événement) ; révision de la grille de SPEC-19 à rouvrir sur données |
| 5 | Live Client API et overlay en jeu | 4 | ✅ tâches 46 et 47 (2026-10-02, `live.py`, `overlay.py`) ; reste la recette en partie réelle de l'overlay |

### Lot suivant — SPEC-21, client LeagueStats (🟡 plan revu le 2026-10-05)

[SPEC-21](docs/specs/SPEC-21-tableau-de-bord-local.md) : de « tableau de bord en lecture seule » à
**client de bureau** (fenêtre `pywebview` sur FastAPI, front sans build) qui parle au client LoL par
le LCU : navigation (profil, historique, collection, lobby/file, social en lecture seule), section
**Coaching** complète, draft interactive et post-game avec le Live Coach, **motion design poussé**.
WebSocket LCU pour le client, polling du Live Coach inchangé. Forme, périmètre, temps réel et niveau
d'écriture validés le 2026-10-04. **Le 2026-10-05**, le handoff de design « Alchimie »
(`docs/design/client_alchimie/`) a fait passer le plan à 37 tâches et 163 pts, avec une fiche par écran
(SPEC-21 §4.10) ; validés le 2026-10-05 : ordre des lots, taille de la fenêtre, thème clair reporté,
écrans sans maquette extrapolés, point d'entrée, écritures du coaching (fixer et clore un axe). Six lots utilisables seuls,
SPEC-21 §5 :

| # | Tâche | Pts | Dépend de | État |
|---|---|---|---|---|
| **Lot 1 — Socle, coque et motion (31 pts)** | | | | |
| 48 | Spike d'empaquetage et de fluidité : fenêtre `pywebview` depuis l'exe, taille, démarrage, temps d'image | 5 | — | ✅ 2026-10-04 : exe +7,2 Mo (82,3 Mo), démarrage 2,0 à 2,5 s, p95 6,2 ms par image, sans bordure confirmée (SPEC-21 §8) ; prise en main par @pj35 faite ; une première exécution d'un exe neuf n'a pas affiché la page (non reproduite), à surveiller à la recette |
| 49 | Socle : config, connexion lecture seule, serveur en thread, fabrique d'app, jeton de session | 5 | 48 | ✅ 2026-10-04 : 25 tests ; port libre choisi par l'OS (validé) ; `fastapi`/`uvicorn` déclarés dès maintenant pour que la CI reste verte (le reste des dépendances à leur tâche) ; `writable()` laissé à la tâche 71 (écritures du coaching à valider) |
| 68 | Coque : fenêtre, navigation, transitions de page, états « client fermé » | 5 | 49 | ✅ 2026-10-04 : 30 tests ; poignées gauche/haut mesurées sans saut (`resize(fix_point)`, SPEC-21 §8) ; **recette @pj35 à faire** : poignées `s`/`se`, jeton de session sur une requête htmx POST, transition de page à l'œil (aucun test d'interface sans ton accord) |
| 70 | Bus, SSE et WebSocket LCU | 5 | 49 | ✅ 2026-10-04 : 18 tests (faux serveur WebSocket local) ; `LcuEvents` pas encore lancé (tâche 55) ; consommateur JS du SSE (`fetch` avec jeton, `EventSource` n'envoie pas d'en-tête) à écrire avec le premier écran qui l'utilise (tâche 73) |
| 69 | Jetons, polices et coque « Alchimie » (barre de titre, navigation, réglage Motion) | 5 | 68 | ✅ 2026-10-05 : 17 tests ajoutés, suite complète verte (1571) ; réglage Motion dans la clé `motion` de `user_prefs.json`, hors de `UserPrefs` (le Live Coach réécrit le fichier, et un fichier créé par le client ne doit pas lui cacher ses questions) ; **recette @pj35 à faire** : rendu à l'œil dans la fenêtre (aucun test d'interface sans ton accord) |
| 84 | `motion.js` et banc `/_motion` | 3 | 69 | ✅ 2026-10-05 : `motion.js` repris et branché (`htmx:load`, braises, mode Réduit) ; banc `/_motion` (4 scènes : braises, 1 600 particules, tracé, sceau ; p95 par scène) ; **mesure du p95 à faire par @pj35** (bouton « Tout mesurer » dans la fenêtre : aucun test d'interface sans ton accord), à consigner en SPEC-21 §8 (critère 11) |
| 55 | Lancement : `--client`, option 7 du menu (Quitter en 8), Live Coach en fil sans entrée console, message `[INFO]`/`[ALERTE]` + tests | 3 | 49, 70 | ✅ 2026-10-05 : 14 tests ; point d'entrée validé par @pj35 ; `DraftMonitor(console_input=False)`, le fil attend le client LoL (15 s) ; `LcuEvents` lancé ; **recette @pj35** : `python lol_coach.py --client` avec le vrai client LoL ouvert puis fermé |
| **Lot 2 — Draft Alchimie (51 pts)** | | | | |
| 72 | `DraftSnapshot`, recommandations structurées, sortie console identique | 5 | 70 | ✅ 2026-10-05 : 11 tests ; sortie console identique (chaînes relevées avant la refonte) ; `DraftSnapshot` publié sur le bus (sujet `draft`), delta face à la position actuelle (`GameEvaluator.win_probability`) ; emplacements, survols et temps restant lus dans le champ select |
| 85 | Bans conseillés et balance dans le snapshot | 3 | 72 | ✅ 2026-10-05 : 6 tests ; `ban_advice` structuré (gain, meilleure réponse, matchups ; 4 bans, la console en garde 3), balance actuelle et projetée (`GameEvaluator`, pas `winprob` qui reste le modèle de partie) ; « si X est verrouillé » = la probabilité du classement de X |
| 86 | Assets Data Dragon locaux et formes LCU de la draft | 5 | 49 | ✅ 2026-10-05 : 26 tests ; `assets.py` (cache disque, version auto ou de la config, `/assets/{kind}/{name}`, noms validés, image absente = emplacement neutre) ; **relevé des formes LCU fait le 2026-10-05 client ouvert hors champ select** (`scripts/dump_lcu_draft_forms.py`) : skins (`ownership.owned`, id = champion×1000+num, `loadScreenPath`), pages de runes (`selectedPerkIds` = 6 runes + 3 fragments), arbres, inventaire figés dans `tests/fixtures/lcu_forms/` ; **reste à relever en champ select** (session, actions, bans, `pickable`/`bannable`) : `session_ban.json` et `session_pick.json` sont construites d'après les formes connues, à remplacer (relancer le script pendant une draft) |
| 74 | Actions de draft : survoler, verrouiller, bannir, corriger un rôle | 5 | 72 | ✅ 2026-10-05 : 38 tests avec faux LCU ; `lcu_proxy.py` (liste blanche en lecture et en écriture), `draft_actions.py` (survoler, verrouiller, bannir, survoler un ban ; 409 lisible hors phase et hors tour, sans écriture), `POST /draft/action/{nom}` et `POST /draft/role` (commande `r` du Live Coach) ; fixtures `tests/fixtures/lcu_forms/session_*.json` **construites d'après les formes connues du LCU, à confronter au relevé réel** (client fermé) |
| 73 | Draft, cadre : en-tête, sceaux, balance, consommateur SSE | 5 | 72, 84, 86 | ✅ 2026-10-05 : 27 tests ; `draft_view.py` (vue pure du snapshot), `/draft` et `/draft/stage`, synchronisation par clé et empreinte (`draft.js` : SSE avec jeton, nœuds inchangés non touchés), mise à l'échelle sous 1920×950, chrono, balance animée sur 800 ms ; `DraftRecommender.refresh` republie à chaque survol ou tour ; **rendu à l'œil à faire par @pj35** (aucun test d'interface sans ton accord) |
| 87 | Draft, phase de bans | 5 | 73, 74, 85 | ✅ 2026-10-05 : 7 tests ; rangée « Bans conseillés » (gain, justification), cible visée = survol de ban dans le client, « Bannir X » (409 lisible hors phase), tampon magenta, révélation en cascade des bans puis des picks adverses au passage aux picks ; **rendu et animations à voir par @pj35** |
| 88 | Draft, phase de picks | 5 | 73, 74 | ✅ 2026-10-05 : 8 tests ; 4 cartes (win % à 2 décimales, écart signé, suite attendue), clic = aperçu immédiat + survol dans le client à mon tour (409 lisible sinon), « Verrouiller X », sceau apposé quand le client confirme le lock ; rendu et animations à voir par @pj35 |
| 89 | Draft, grimoire des champions | 5 | 88 | ✅ 2026-10-05 : 14 tests ; `draft_grimoire.py` + `/draft/champions` + `champions.js` : tri recommandations / pool / alphabétique, recherche sans accents, puces de rôle (mon rôle par défaut), pool, indisponibles avec leur raison, victoire prédite de **tous** les champions libres calculée par le Live Coach sur ma lane (173 champions : 1 ms à chaud, ~0,5 s à froid) et gains de ban de toutes les menaces lues, double-clic = action ; rendu à voir par @pj35 |
| 90 | Draft, sélection de skin | 3 | 86, 88 | ✅ 2026-10-05 : 13 tests (forme LCU relevée sur le client réel : `skins_annie.json`) ; possession lue dans le LCU et gardée 60 s, cartes 104×188 (cadenas et gris si non possédé), splash du skin choisi, `POST /draft/skin` (409 si non possédé ou avant le verrouillage), écriture par `my-selection` ; rendu à voir par @pj35 |
| 91 | Draft, colonne loadout | 5 | 86, 88 | ✅ 2026-10-05 : 28 tests ; `draft_loadout.py` (page prévue lue sur OneTricks sans bloquer la boucle de draft, ou déjà écrite dans le client ; validation contre les arbres de Data Dragon), `runes.js` (colonne : carte de page, sorts avec popover et échange, objets en lecture seule), « Envoyer au client » (runes + sorts par la liste blanche), « Modifiée à la main » / « Rétablir OneTricks » : `loadout manual|auto` arrête ou rend l'import du lock-in (`LoadoutImporter.manual`) ; rendu à voir par @pj35 |
| 92 | Draft, éditeur de runes | 5 | 91 | ✅ 2026-10-05 : 13 tests dont les règles d'édition exécutées sous node (`rune_logic.js` : 3ᵉ rangée secondaire chasse la plus ancienne, même rangée remplace, arbre principal pris au secondaire) ; chaque page produite est validée par le serveur contre les arbres de Data Dragon (chemins écrits à la main du prototype remplacés par `runesReforged.json`) ; overlay circulaire, éclosion en cascade, Annuler / Appliquer ; rendu à voir par @pj35 |
| **Lot 3 — File trouvée et transition de page (8 pts)** | | | | |
| 93 | File trouvée : overlay, accepter / refuser | 5 | 84, 55 | ✅ 2026-10-05 : 19 tests avec faux LCU ; `found.py` (`/found/state`, `POST /found/accept|decline`, refus 409 hors file trouvée, liste blanche), `found.js` (overlay : convergence de 90 runes, pilier, anneau de 10 s, impact, acceptation avec explosion et effondrement, mention de l'auto-accept ; pastille « Champ select en cours »), `sse.js` partagé avec la draft ; **à confirmer en partie réelle** : la forme du `timer` du ready-check (décompte = 10 s moins le timer) ; rendu à voir par @pj35 |
| 94 | Transition de page signature | 3 | 84, 73 | ✅ 2026-10-05 : 9 tests ; `transition.js` remplace les View Transitions : cercle runique tracé et 44 runes en convergence pendant que le contenu s'assombrit, implosion de 860 ms (= `hx-swap swap:860ms` de #view), puis explosion, éclair cuivre, secousse de 8 px et ouverture par `clip-path` ; la navigation glisse à la sortie de la draft ; Réduit = remplacement instantané ; le voile ne capte aucun clic et un nouveau clic relance la transition ; durées en config ; **rendu à voir par @pj35** (l'extension Chrome était déconnectée, pas de capture) |
| **Lot 4 — Coaching et post-game (39 pts)** : fait le 2026-10-05, recette @pj35 à faire | | | | |
| 50 | `charts.py` : graphiques SVG purs, tracé animable | 5 | 84 | ✅ 2026-10-05 : 23 tests ; `line_chart` (bandes, filets gradués, repères, dernier point lumineux), `sparkline`, `bar_chart` divergent, `reliability_chart`, `diverging` ; dégradés en `userSpaceOnUse` (une courbe plate ne serait pas dessinée en `objectBoundingBox`) ; classes CSS des graphiques (`ch-*`, `spark-*`) posées avec le premier écran qui les utilise (tâche 51) |
| 51 | Écran Rang | 5 | 50 | ✅ 2026-10-05 : 18 tests ; `data.rank_view` (courbes Solo et Flex sur l'échelle de `lp_scale()`, photos qui répètent leur voisine omises de la courbe, histogramme des LP, cartes par file), `/rang`, `CoachingRepository.rank_history()`, `coaching.js` (barres, lignes, pile) ; lecture en `mode=ro`, tables absentes = état vide ; **rendu à voir par @pj35** (aucun test d'interface sans ton accord) |
| 52 | Écran Progression | 5 | 50 | ✅ 2026-10-05 : 21 tests ; `data.progression_view` (puces de poste, grille de `coaching/grid.py`, Toi / Norme / Objectif, tendance = moyenne glissante du z sur 10 parties, verdict de `trends()`, schémas de `patterns()`), `/progression?role=` ; puces rechargées par htmx sans transition de page ; **`trends()` compare deux moitiés de 5 parties : sous 5 parties « n/5 », de 5 à 9 « n/10 », le message le dit** ; rendu à voir par @pj35 |
| 53 | Écran Parties : win chance, impact par événement | 5 | 50 | ✅ 2026-10-05 : 22 tests sur la partie réelle 7998195590 (fixtures du spike) ; `winprob.report.curve_points()` extraite de `curve()` (sortie texte identique, test d'identité), `review.games_view` / `game_page`, `/parties` et `/parties/{id}` (404 lisible), `CoachingRepository.recent_games`, `game_record`, `game_roles`, `rank_after_game`, `prediction` ; événements vus de l'équipe du joueur (un kill compte par la ligne de sa victime, un objectif par celles de l'équipe qui le prend) ; sans impact « impact non calculé », sans timeline ou sans modèle la courbe le dit ; mise en page post-game, constats, LP et axes avec la tâche 75 ; **rendu à voir par @pj35** |
| 54 | Écran Calibration | 3 | 50 | ✅ 2026-10-05 : 15 tests ; `analysis.calibration.calibration_buckets()` extraite (`calibration_curve()` en est la mise en forme, sortie texte identique : test d'identité sur un jeu fixe), `data.calibration_view`, `/calibration?version=` (versions jamais mélangées, diagramme de fiabilité, Brier, n, tableau par classe) ; sous `MIN_ROWS_FOR_CALIBRATION` le même refus que la console ; mêmes Brier et n que `scripts/calibrate_model.py` (test qui exécute le script) ; rendu à voir par @pj35 |
| 71 | Accueil Coaching : axes, constats, colonne latérale | 5 | 51–53 | ✅ 2026-10-05 : 25 tests ; `home.py` (axes avec leurs cinq pastilles, places libres et proposition du coach, derniers constats en barres divergentes, carte de rang et sparkline, dix dernières parties, bilan du rôle), `goals.next_proposal()` (proposer sans écrire), `db.writable()` (`mode=rw`, jamais créée), **écritures validées par @pj35 le 2026-10-05** : `POST /accueil/axe` (fixer, ou choisir une autre métrique) et `POST /accueil/axe/{id}/clore`, derrière le jeton et le contrôle `Origin` ; **rendu et clic à voir par @pj35** |
| 75 | Post-game, données et page de revue | 5 | 72, 53 | ✅ 2026-10-05 : 24 tests ; `GameCapture.on_post_game` publie `game_captured` (la plus récente des parties prises, best-effort) et, bus branché, **la revue remplace le rapport console** (partie et impact ; le reste de la console inchangé) ; `/postgame` (dernière partie, « Revue de partie · il y a … ») et `/parties/{id}` : LP et rang, axes jugés (`goal_verdicts`), pile des 10 événements les plus lourds, impact attribué et résidu (recalculé seulement avec le modèle qui a rangé les lignes), écarts à la norme et à l'objectif, variante Défaite (rose) ; `coaching.js` bascule sur `/postgame` à l'événement, **sauf pendant une draft** ; mise en scène (sceau, compteurs) à la tâche 95 ; **à voir en partie réelle par @pj35** |
| 95 | Post-game, mise en scène | 3 | 75, 84 | ✅ 2026-10-05 : 9 tests ; sceau de 104 px (menthe en victoire, rose en défaite) apposé une fois à l'arrivée par `Motion.seal` (menthe, or, blanc ou rose, cuivre, blanc) avec secousse de 9 px, en Réduit posé sans particules ni secousse (câblage de `coaching.js` exécuté sous node avec un `Motion` factice), titre qui se transmute, LP en compteur, courbe tracée à l'encre, marqueurs qui apparaissent le long du tracé, pile d'impact (un événement toutes les 110 ms) ; **à voir par @pj35** (aucun test d'interface sans ton accord ; le p95 sur cette page reste à mesurer, critère 11) |
| 56 | Empaquetage : dépendances, `.spec`, CI, exe vérifié, docs | 3 | 55, 71, 75, 92 | ✅ 2026-10-05 : 10 tests ; `.spec` embarque `src/client/templates` et `static` (polices comprises) sous leur chemin de développement, dépendances déjà déclarées (test qui compare les imports du client à `requirements.txt`), `scripts/check_exe_assets.py` (étape de la CI : 38 fichiers du client et 8 modules dans l'archive, sans lancer l'exe) ; **exe construit le 2026-10-05 : 82,8 Mo (spike : 82,3), les 38 fichiers et les 8 modules y sont** ; README, `PROJECT_STRUCTURE.md`, `CHANGELOG.md` ; **recette @pj35** : lancer l'exe, ouvrir le client (un premier lancement d'un exe neuf n'avait pas affiché la page au spike, à surveiller) |
| **Lot 5 — Profil et historique (13 pts)** : fait le 2026-10-05, recette @pj35 à faire | | | | |
| 76 | Spike des endpoints de navigation, fixtures | 3 | 70 | ✅ 2026-10-05 : 19 lectures `GET` (`scripts/dump_lcu_nav_forms.py`), 17 fixtures dans `tests/fixtures/lcu_nav/` (19 tests), SPEC-21 §10 ; **lobby et file non relevés** (aucun lobby ouvert, 404 : formes construites d'après `/help`, à confronter à un vrai lobby) ; l'historique n'a renvoyé qu'une partie |
| 77 | Profil, rang, régalia, défis | 5 | 76 | ✅ 2026-10-05 : 16 tests sur les fixtures de la tâche 76 ; `profil.py` (`read_profile`, `profile_view` pures), `/profil` (identité et XP, cartes Solo et Flex dans le style de `/rang`, régalia, défis : catégories et trois meilleurs), `screen()` de `app.py` : « client fermé » ou « indisponible » (aussi sur une forme inattendue), jamais une 500 ; liste blanche étendue (ranked, regalia, challenges) ; `profileicon` ajouté aux assets ; **rendu à voir par @pj35** (aucun test d'interface sans ton accord) |
| 78 | Historique (20 parties) et détail | 5 | 76, 53 | ✅ 2026-10-05 : 17 tests ; `historique.py` (`read_history`, `read_game`, vues pures), `/historique` (portrait, résultat, KDA, sbires par minute, durée, file, badge « Capturée ») et `/historique/{id}` (deux équipes, objectifs, bans, dix joueurs avec dégâts et objets, joueur repéré par son `puuid`), lien vers `/parties/{id}` pour une partie capturée (`CoachingRepository.captured_game_ids`) ; entrée « Historique » dans la navigation ; files nommées en français (Normale, ARAM, Partie rapide, Arena, Clash) ; **rendu à voir par @pj35** |
| **Lot 6 — Collection, lobby, file, social, clôture (21 pts)** : fait le 2026-10-05, recette @pj35 à faire | | | | |
| 79 | Collection (lecture) | 5 | 76 | ✅ 2026-10-05 : 12 tests ; `collection.py` (`read_collection` ne lit que l'onglet demandé), `/collection?vue=champions|runes|objets&role=` : champions possédés (filtre par classe, portraits, rotation), pages de runes (page active d'abord, rune majeure), sets d'objets (champions associés, blocs) ; lecture seule ; **rendu à voir par @pj35** |
| 80 | Lobby : créer, choisir, quitter | 5 | 76 | ✅ 2026-10-05 : 35 tests avec faux LCU ; `lobby.py` (files proposées = non personnalisées de la Faille et de l'ARAM, disponibles et visibles ; `create`, `leave`, `set_positions` gardés par la phase du client lue à l'appel, refus 409 sans écriture), `/lobby`, `/lobby/etat` (corps relu par `lobby.js` aux événements du LCU, sans animation ni perte du focus d'une liste), `POST /lobby/creer|quitter|postes` derrière le jeton ; liste blanche : ouvrir, quitter, postes ; aucune invitation ni gestion du groupe ; **formes du lobby construites d'après `/help`, à confronter à un vrai lobby ; rendu à voir par @pj35** |
| 81 | File : lancer, annuler ; barre de titre | 5 | 80, 93 | ✅ 2026-10-05 : 24 tests avec faux LCU ; `lobby.file_state`, `start`, `cancel` (chef du groupe, hors recherche, restriction du lobby citée ; annuler refusé hors `Matchmaking`, jamais pendant une partie trouvée), `GET /file/state`, `POST /file/lancer|annuler` derrière le jeton ; barre de titre : « Lancer la file » puis « En file m:ss · estimée » avec « Annuler » (`file.js`), mêmes boutons sur l'écran Lobby ; liste blanche : recherche du lobby seulement ; cohabitation avec l'auto-accept : l'info-bulle de la recherche le signale, la partie trouvée reste celle de `found.js` ; **forme de `lol-matchmaking/v1/search` construite d'après `/help`, à confirmer en vraie file ; rendu à voir par @pj35** |
| 82 | Social en lecture seule | 3 | 76 | ✅ 2026-10-05 : 19 tests ; `social.py` (`read_social`, `social_view` pures), `/social` : profil de chat, amis en partie (file, champion, rang), connectés, hors ligne (repliés), conversations (non lus, dernier message tronqué) ; **aucune écriture** : liste blanche limitée à `me`, `friends`, `conversations`, aucune route d'envoi ni d'invitation (tests des critères 5 et 6) ; pseudos et messages échappés ; **rendu à voir par @pj35** |
| 83 | Clôture : exe vérifié, docs, statuts | 3 | 56, 77–79, 81, 82, 95 | ✅ 2026-10-05 : exe construit (82,9 Mo, spike 82,3), `check_exe_assets.py` : 48 fichiers du client et 8 modules présents ; README, `PROJECT_STRUCTURE.md`, `CHANGELOG.md`, statuts de la spec et du README des specs ; **recette @pj35** : lancer l'exe, parcourir Profil, Historique, Collection, Lobby (ouvrir, postes, quitter), file (lancer, annuler), Social ; confronter les formes du lobby et de la file au client réel |

### Lot suivant — SPEC-24, retours sur le client (✅ livrée le 2026-10-07, recettes @pj35 à faire)

[SPEC-24](docs/specs/SPEC-24-retours-gui-bans-ordre-en-partie.md) : le ban visé n'arrive pas dans le client
LoL (cause **non établie**, le chemin n'a jamais vu une vraie phase de bans : relevé d'abord) ; ordre de pick
affiché et swaps d'ordre et de rôle (boutons et conseil chiffré) ; écran « En partie » (analyse de la draft,
plan de build et suivi des achats, courbe de win chance). Rouvre SPEC-21 §7 (« écran en partie »). Trois lots
utilisables seuls, 16 tâches (96 à 111, 61 pts) ; arbitrages « à valider » en SPEC-24 §2 :

| # | Tâche | Pts | Dépend de | État |
|---|---|---|---|---|
| **Lot 1 — Bans et acteur courant (8 pts)** | | | | |
| 96 | `dump_lcu_draft_forms.py --watch`, relevé d'une draft classée et d'une normale par @pj35, fixtures réelles | 3 | — | ✅ 2026-10-07 : relevé d'une draft classée (file 420, 73 formes) ; fixtures réelles anonymisées `session_ban`, `session_ban_simultane`, `session_pick`, `session_swaps` (reçue), `session_swaps_sent`, `bannable_*` (jeton du chat retiré) ; constats en SPEC-24 §4.1 ; **non relevé** : draft normale, chemins `POST` des swaps (le relevé est en lecture seule) |
| 97 | Ban : cause racine sur le relevé, correctif, régression rouge puis verte, audit de `hover_champion` (console) | 3 | 96 | ⬜✅ 2026-10-07 : 3 défauts relevés (liste `[-1]` qui refusait chaque ban, survol console écrit sur l'action de pick, tour lu sur `current_actor` alors que bans et picks sont simultanés) ; 8 tests de régression rouges avant, `ban_logic.js` sans présélection (5 tests node), refus du client expliqués ; **écart** : cartes non filtrées sur `bannable-champion-ids` (inutilisable, SPEC-24 §4.2) ; recette @pj35 : valider un ban depuis le client LeagueStats en draft classée |
| 98 | `current_actor` de la cellule 0 (`if state.current_actor:` écrase l'acteur) et `acting_cells` : correctif et régression | 2 | — | ✅ 2026-10-06 : 4 tests, rouge avant le fix ; `parse` teste `is not None` et remplit `acting_cells` (`isInProgress`), `phases` teste `is None` ; les autres appelants de `current_actor` / `local_player_cell_id` relus, aucun autre test sur la valeur |
| **Lot 2 — Ordre de pick et swaps (24 pts)** | | | | |
| 99 | `pick_order` et `swaps` dans `DraftState` et `DraftSnapshot`, console identique | 3 | 96, 98 | ⬜✅ 2026-10-07 : 8 tests sur les fixtures réelles ; `DraftState.pick_order` (rang 1 à 10 dans l'ordre des actions, permutation vérifiée), `DraftState.swaps` (`Swap(kind, id, cell_id, state)`), `SnapshotPlayer.pick_order`, `DraftSnapshot.swaps` (sans `id`, qui reste côté serveur), `is_acting` lu sur `acting_cells` (cellule 0 et lots comprises), empreinte du tick étendue (cellule locale, acteurs, échanges) ; console inchangée (tests d'identité de la tâche 72 verts) ; `swap_advice` viendra avec la tâche 102 |
| 100 | Ordre de pick à l'écran : numéro sur chaque sceau, anneau du joueur en cours | 3 | 99 | ⬜✅ 2026-10-07 : 5 tests ; médaillon `.d-order` (n° 1 à 10, couleur de camp, infobulle « Pick n° N ») sur chaque sceau dont le moi, anneau `.d-acting` du joueur en cours (cellule 0 et lots de deux comprises), dès la phase de bans, rien sans actions du LCU, rang dans l'empreinte `sig` ; **rendu à voir par @pj35** |
| 101 | Actions de swap : liste blanche, `draft_swaps.run`, `POST /draft/swap/{kind}/{action}` | 5 | 96, 99 | ⬜✅ 2026-10-07 : 27 tests sur les fixtures réelles ; `draft_swaps.run` (demander `AVAILABLE`, accepter et refuser `RECEIVED`, annuler `SENT`, l'`id` lu dans la session pour la cellule nommée, jamais du front), un seul motif ajouté à `WRITES` (les huit chemins `POST`, testé contre la liste attendue, aucun autre chemin d'échange accepté), `POST /draft/swap/{kind}/{action}?cell_id=` (403 sans jeton, 409 sans écriture hors état attendu, 422) ; cadre validé par @pj35 ; **chemins `POST` d'après `/help`, jamais exercés en vrai : recette** |
| 102 | Conseil de swap de rôle (`swap_advice.role_swaps`) | 3 | 99 | ⬜✅ 2026-10-07 : 10 tests ; `swap_advice.role_swaps` (gain = `win_probability` après − avant en points ; seulement un échange de rôle ouvert, `AVAILABLE` ou `RECEIVED`, avec un champion des deux côtés, moi survolé ou verrouillé ; meilleur gain d'abord), `SWAP_MIN_GAIN_PTS = 1,0` dans `draft_config`, calculé dans `DraftRecommender._publish` seulement quand la session liste un échange de rôle ouvert, cache sur picks, lanes et échanges, best-effort (évaluateur qui lève : conseil vide) ; `SnapshotSwapAdvice` dans `DraftSnapshot.swap_advice` ; **écart de signature** : `allies` est un dict cellule -> (champion, lane), les échanges nommant l'autre joueur par sa cellule |
| 103 | Conseil de swap d'ordre, bench, calibrage du seuil (**conditionnelle** au bench) | 5 | 102 | ⬜✅ clos 2026-10-07 sans conseil d'ordre (décision @pj35) : bench fait (`scripts/bench_swap_advice.py`), stabilité 2/2 mais sans sens (la recherche écarte les tours qui précèdent le mien) ; les boutons d'ordre restent (tâches 101 et 104) ; à rouvrir avec une recherche qui chaîne la racine (SPEC-24 §4.6) |
| 104 | Carte « Échanges » : icônes, popover, bandeau de demande reçue, annuler | 5 | 100, 101, 102 | ⬜✅ 2026-10-07 : 8 tests ; sur la légende d'un allié dont la session liste un échange : « ⇄ ordre » et « ⇄ rôle » (avec « +1,2 pts » du coach), « ✕ » pour annuler une demande envoyée, rien pour `INVALID` ; demande reçue : bandeau « X te propose d'échanger … » avec Accepter et Refuser (et le gain du coach pour un rôle) ; refus 409 en toast (`post` existant) ; l'`id` n'est jamais envoyé par le front (testé) ; fragments keyés avec empreinte (contrat `data-sync` testé) ; **écart** : boutons directs sur la légende et bandeau dans le fragment de l'écran, pas de popover ni de bandeau dans `#d-overlays` (même effet, un clic de moins) ; **rendu à voir par @pj35** |
| **Lot 3 — En partie (29 pts)** | | | | |
| 105 | Spike Live Client en partie réelle (@pj35) et page OneTricks (ordre des compétences), fixtures | 3 | — | ⬜✅ 2026-10-07 : spike en partie réelle (une lecture `GET`, 10 joueurs) : `items`, `championName`, `position`, `currentGold`, `abilities` (niveaux courants seulement) vérifiés ; **OneTricks publie l'ordre des compétences** (`skillPaths`, `earlySkillPaths`, `maxSkillOrders`, déjà gardés par `_trim`) ; fixtures `spike_live/allgamedata_items.json` (noms remplacés) et `onetricks_skills_yorick_top.json` ; SPEC-24 §4.9 |
| 106 | `FinalAnalysis` structuré et publié (sujet `game`), loadout étendu des substitutions, console identique | 5 | — | ✅ 2026-10-06 : 17 tests ; `build_final_analysis` (données seules : une ligne par lane dans l'ordre de `face_offs`, probabilité, écart, évaluation, loadout), `analyze` imprime à partir de la structure et la publie (`game`), `reset_for_next_game` publie `None` ; `LoadoutImporter.state(with_duel=True)` ajoute substitutions (catégorie, ancien, nouveau, parts, raison) et noms d'objets, `state()` de la draft inchangé ; console identique, relevée sur le code d'avant (`tests/fixtures/final_analysis_console.txt`, 5 jeux) |
| 107 | `LiveGame` : fil de lecture, série de win chance, état sur le bus | 5 | 105 | ⬜✅ 2026-10-07 : 14 tests (`fetch` factice, `tick()` à la main) ; `src/client/ingame.py` (`LiveGame`, sujet `ingame` : `idle` une fois, `live` avec `p`, `delta`, `series`, `objectives`, `me`, `ended` série gardée), même `overlay.Tracker` que l'overlay (même probabilité, testé), aucune lecture hors `InProgress`, exception du `fetch` ou de la phase annoncée une fois en `[INFO]`, série bornée (`INGAME_MAX_POINTS`) et remise à zéro quand le temps de jeu recule, fin de partie par phase ou par `INGAME_GRACE_POLLS` lectures vides ; fil démarré par `run_client` (phase via `LcuProbe` + liste blanche) ; constantes `INGAME_*` dans `client_config` |
| 108 | Écran « En partie » : cadre, navigation, pastille, face-à-face de la draft | 5 | 106, 107 | ⬜✅ 2026-10-07 : 17 tests ; `GET /en-partie` et `/en-partie/stage` (200 dans `idle`, `live`, `ended`, aucune route d'écriture sous `/en-partie`, testé), entrée « En partie » dans le groupe Partie, pastille « En partie » dans la barre de titre pendant `live` (sur toutes les pages, **sans bascule automatique**, testé), horloge, win chance et variation, face-à-face de la draft (chevrons de duel, « peu de données »), « analyse indisponible » sans `FinalAnalysis`, « pas de modèle : python -m src.winprob.retrain --force » ; `en_partie.js` relit le fragment à chaque événement `ingame` ; **rendu à voir par @pj35** |
| 109 | Courbe de win chance en direct | 3 | 107, 108 | ⬜✅ 2026-10-07 : 7 tests ; `charts.line_chart` sur la série (axe en minutes, bande des 50 %, dernier point lumineux, repères dragon / Héraut / Nashor / tour / inhibiteur tirés des événements Live Client, couleur de gain ou de perte selon le camp), variation sur la dernière minute, moins de deux points : un message et pas de courbe, client ouvert en cours de partie (`INGAME_LATE_START_S`) : l'écran le dit, objectifs d'avant le premier point non repérés, point de départ de la draft non tracé ; **rendu à voir par @pj35** |
| 110 | Build : plan d'objets, suivi des achats, ordre des compétences si publié | 5 | 105, 108 | ⬜✅ 2026-10-07 : 16 tests ; `en_partie.build_view` : plan d'objets du loadout de `FinalAnalysis` (blocs, noms français de Data Dragon, `Assets.items()` nouveau), objets possédés cochés, prochain objet (Core puis première paire de bottes, les alternatives ne comptent pas), coût restant (assemblage + composants non possédés) et manque d'or (`activePlayer.currentGold`), `items` absent de l'API : « achats indisponibles » (distinct d'une liste vide), substitutions du duel avec leur raison, **ordre des compétences** (`loadout_import._skills` d'après `maxSkillOrders` / `skillPaths` de la page OneTricks, ligne absente quand la page ne le publie pas) ; **rendu à voir par @pj35** |
| 111 | Clôture : exe vérifié, docs, SPEC-21 §7, statuts | 3 | 104, 109, 110 | ⬜✅ 2026-10-07 : `python build_app.py` (83,1 Mo) puis `check_exe_assets.py` : 52 fichiers du client et 11 modules (dont `ingame`, `en_partie`, `draft_swaps`) présents ; README, `PROJECT_STRUCTURE.md`, `CHANGELOG.md`, SPEC-21 §7 (« écran en partie » rouvert et livré), statuts ; **recette @pj35** : lancer l'exe, ouvrir « En partie » pendant une partie (courbe qui avance, plan qui se coche à l'achat), valider un ban et demander, recevoir, accepter un échange en draft classée |

### Lot suivant — SPEC-25, suivi de phase et capture de fin de partie (🟡 rédigée le 2026-10-07)

[SPEC-25](docs/specs/SPEC-25-suivi-de-phase-et-capture-de-fin-de-partie.md) : les LP et l'écran de fin ne sont plus
capturés depuis le 2026-10-05 (11 parties) ; les deux endpoints ne répondent que sur l'écran de fin et sont
lus toutes les 6 à 10 s dans une boucle de 2 à 5 s/tour. `PhaseTracker` (événements WebSocket `/lol-gameflow` +
sondage de rattrapage) comme source unique de la phase, capture déclenchée par la transition hors de la boucle du
monitor, pastille de phase dans la barre de titre. Spike d'une fin de partie réelle d'abord (@pj35). Passe avant
la tâche 64 de SPEC-23. Découpage en SPEC-25 §5 (tâches 112 à 118, 24 pts) :

| # | Tâche | Pts | Dépend de | État |
|---|---|---|---|---|
| 112 | Spike : `scripts/dump_lcu_endgame.py`, une fin de partie réelle par @pj35, fixtures | 3 | — | ⬜✅ 2026-10-07 : 3 tests ; relevé de 1 689 s (partie classée perdue), fixtures `tests/fixtures/lcu_endgame/`, constats en SPEC-25 §4.0 : phase par événement sans délai (`"None"` hors lobby, chaîne), endpoints pleins de `PreEndOfGame` à la sortie d'`EndOfGame` (25 s ici), lecture en 1 ms, **événement `/lol-ranked` porteur de la notification complète (tâche 117 confirmée)** ; « Rejouer » rapide non couvert |
| 113 | `PhaseTracker` : événements, sondage de rattrapage, `kind`, sujet `phase`, constantes | 5 | 112 | ⬜✅ 2026-10-07 : 31 tests ; `PhaseTracker` (événement `/lol-gameflow/v1/gameflow-phase`, sondage de rattrapage `PHASE_POLL_S` / `PHASE_POST_POLL_S`, `kind_of`, sujet `phase` sur le bus, rappels qui peuvent lever, phase inconnue journalisée une fois), `phase` = None après `PHASE_STALE_S` sans confirmation (le monitor relit alors lui-même), lecteur sur un `LCUClient` propre avec recherche des identifiants au plus une fois par `PHASE_CREDENTIALS_RETRY_S`, rejeu de la fin de partie réelle |
| 114 | `DraftMonitor` et `MonitorLifecycle` sur le tracker : zéro lecture de phase par tour | 3 | 113 | ⬜✅ 2026-10-07 : 5 tests ; `MonitorLifecycle.gameflow()` : une lecture de phase par tour au plus (0 quand le tracker la connaît, 1 au repli, contre 3 avant), `handle_ready_check` sur la même source, fenêtre d'après-partie ouverte par le rappel du tracker même si la boucle n'a jamais vu la phase ; 3 tests existants passent de `is_in_*` à `get_gameflow_session` (le repli) |
| 115 | Capture hors boucle (`read_transients`, `PostGameWatcher`), erreurs affichées une fois, régression | 5 | 112, 113 | ⬜✅ 2026-10-07 : 11 tests dont la régression (rouge sans le fil : aucune LP écrite, et `AttributeError` sur le code d'avant ; verte après) ; `GameCapture.read_transients(lcu)` sans base, `_lp_by_game` et verrou, `write_lp_snapshots` rejoue une notification refusée par une base verrouillée, `ranked.snapshot_after_game(note, db)` et `valid_notification`, `PostGameWatcher` (module `src/coaching/post_game_watcher.py` à part pour que le critère 7 tienne : `capture.py` importe sqlite3) lit chaque `PHASE_POST_POLL_S` avec son client, une dernière lecture à la sortie de `post`, borné par `POST_GAME_RETRY_WINDOW`, erreurs de capture affichées une fois en `[ALERTE]` hors `-v` |
| 116 | Pastille de phase dans la barre de titre, `LiveGame` sur le tracker | 3 | 113 | ⬜✅ 2026-10-07 : 8 tests ; la pastille `#tb-phase` de la barre de titre remplace la pastille « En partie » (même emplacement, lien vers l'écran En partie, jamais de bascule de page) : six états rendus (Hors partie, En file, Champion select, En partie, Fin de partie, Client LoL fermé) d'après `bus.latest("phase")` au chargement puis le sujet `phase` en SSE (`client_config.PHASE_LABELS`, plus « Erreur de partie » et « Phase inconnue »), `LiveGame` lit la phase du tracker avec la sonde `LcuProbe` en repli quand le tracker est muet ; **rendu à voir par @pj35** |
| 117 | **Conditionnelle** au spike : notification de LP lue dans l'événement `/lol-ranked` | 3 | 112, 115 | ⬜ |
| 118 | Clôture : exe, docs, `CHANGELOG.md`, SPEC-23 et SPEC-24, statuts | 2 | 114, 115, 116 | ⬜ |

### Lot suivant — SPEC-22, attribution complète de l'impact (🟡 rédigée le 2026-10-04)

[SPEC-22](docs/specs/SPEC-22-attribution-complete-impact.md) : le « −20 pts non attribué » du rapport
d'impact vient à −23 pts des objectifs perdus, que personne ne porte (mesuré sur 45 parties) ;
l'impact cumulé du joueur est biaisé vers le haut d'autant. Objectifs perdus débités aux absents,
niveaux face à l'adversaire de lane, récupération après respawn ; le modèle de SPEC-20 reste
unique. Vision, placement et vague hors périmètre (@pj35, 2026-10-04). Conventions du §2 à valider.
Découpage en SPEC-22 §5 (tâches 57 à 61, 16 pts) :

| # | Tâche | Pts | Dépend de | État |
|---|---|---|---|---|
| 57 | `scripts/bench_impact_residual.py` : base de référence du résidu (−20,3 / 25,1 pts) | 2 | — | ⬜ |
| 58 | Objectifs perdus : lignes `lost_*` aux coéquipiers absents | 3 | 57 | ⬜ |
| 59 | `WinModel.logit_parts`, segments par joueur, lignes `levels` et `respawn` | 5 | 58 | ⬜ |
| 60 | Convention versionnée dans `model_version`, `raw_eog`, recalcul des 45 parties | 3 | 59 | ⬜ |
| 61 | Rapport, bilan, libellés, mesure finale, `CHANGELOG.md` | 3 | 60 | ⬜ |

### Lot suivant — SPEC-23, débit de la collecte (🟡 rédigée le 2026-10-04)

[SPEC-23](docs/specs/SPEC-23-debit-collecte-concurrent.md) : la collecte de SPEC-20 passe par le LCU, pas
par l'API publique : les 30 000 req/10 min (50 req/s) ne la bornent pas, c'est un plafond de référence.
Mesuré à ~2 req/s au pic (3 364 parties/h), une unité de travail par tick. Pool de threads (requêtes
seules, écritures dans la boucle), spike par paliers sur une copie de `crawl.db` (arrêt sur latence,
erreurs ou premier 429), débit réduit en partie, croisière une fois `CRAWL_TARGET_GAMES` atteint.
Architecture et critère d'arrêt validés par @pj35 le 2026-10-04 ; cible et croisière à valider.
Découpage en SPEC-23 §5 (tâches 62 à 67, 16 pts) :

| # | Tâche | Pts | Dépend de | État |
|---|---|---|---|---|
| 62 | `LCUClient.last_status_code` thread-local, session de collecte à pool dimensionné | 2 | — | ⬜ |
| 63 | `Crawler` : exécuteur, jetons, en vol, 429, mesures ; constantes ; tests | 5 | 62 | ⬜ |
| 64 | Débit en partie et croisière : `step(phase)`, `_target_reached()` | 3 | 63 | ⬜ |
| 65 | `scripts/bench_crawl_rate.py` (copie temporaire, paliers, critères d'arrêt) | 3 | 63 | ⬜ |
| 66 | Spike réel par @pj35 (client ouvert, Live Coach fermé), `CRAWL_RATE_RPS` fixé | 2 | 64, 65 | ⬜ |
| 67 | Docs : SPEC-20 §2/§3.1/§9, `CHANGELOG.md`, statuts | 1 | 66 | ⬜ |

### Hors sprint — SPEC-18 phase A ✅ (2026-09-24)

[SPEC-18](docs/specs/SPEC-18-force-intrinseque.md) remplace l'ancienne tâche « shrink de
`avg_delta2` » : mesuré, `avg_delta2` n'a aucun signal au niveau du champion (nul par
construction). La tier list blind pick et le survol du blind pick sont classés au winrate de lane
rétréci. Le modèle de prédiction ne change pas (approche C, @pj35).

### Reporté — non planifié

| Tâche | Spec | Rouvrir quand |
|---|---|---|
| Recherche parallèle à la racine (`multiprocessing`, phase 2) | SPEC-17 §5 | Après le sprint 3, si le bench montre une profondeur < 5 en premier pick, ou si le premier pick reste mal conseillé à l'usage |
| Recherche en tâche de fond pendant le chrono de pick (« pondering ») | SPEC-17 §7 | Après le sprint 3, si la profondeur reste le facteur limitant ; chantier d'UI (sortir `rank()` de la boucle du monitor) |
| Force intrinsèque dans `GameEvaluator` (SPEC-05 §3.3, jamais implémentée) | SPEC-18 §3 | `scripts/compare_intrinsic_strength.py` donne une borne basse d'IC > 0 (au 2026-09-24 : +0,019 d'AUC, IC [−0,053 ; +0,090] sur 72 parties) |
| Modèle de win chance plus riche (arbre boosté, puis réseau de neurones), entraînement éventuellement dans un projet adjacent | SPEC-20 §13 | La logistique de la phase 2 est mesurée (Brier, calibration, coût de l'exclusion de l'or) et laisse une marge |
| Moteur d'optimisation, phase A (shrinkage mesuré du WPA) | SPEC-16 §2 | Coachless donne son autorisation écrite : le spike (SPEC-15 §2.1.1, 2026-09-24) confirme un WPA par composant avec échantillons, mais les CGU interdisent l'accès direct à l'API |

**Abandonné** (ADR-003) : la table `build_snapshots`, l'étape de collecte du pipeline, l'alerte
`data_freshness.py` (anciennes tâches 3 à 6 et 9), et SPEC-16 A+ (anciennes tâches 19-20).

---

## Lot SPEC-08 → SPEC-10 ✅ Soldé (2026-09-06)

**Validées par @pj35 le 2026-09-05.** Specs autoportantes dans [`docs/specs/`](docs/specs/README.md).
Les trois chantiers sont mergés sur master ; 1206 tests passent (990 avant le lot), couverture
globale 65,5 % → 72,51 %, seuil CI relevé 45 % → 60 %.

| Rang | Chantier | Spec | État |
|---|---|---|---|
| 1 | **Fermer la boucle de mesure** (résultat de partie automatique via LCU) | [SPEC-08](docs/specs/SPEC-08-boucle-de-mesure.md) | ✅ **Mergée le 2026-09-06** |
| 2 | **Rendre l'ignorance visible** (champions écartés affichés, seuil de lane 10 % → 5 %) | [SPEC-09](docs/specs/SPEC-09-ignorance-visible.md) | ✅ **Mergée le 2026-09-06** |
| 3 | **Couverture du chemin critique temps réel** | [SPEC-10](docs/specs/SPEC-10-couverture-chemin-critique.md) | ✅ **Mergée le 2026-09-06** — `pool_selection_ui.py` 2,6 % → 100 %, `lcu_client.py` 18,6 % → 83,7 % |
| 4 | **Calibration du modèle** | — | ⏳ **En attente de données** — le diagnostic se déclenche tout seul désormais (SPEC-12, mergé le 2026-09-06 : `OutcomeTracker` affiche `[CALIBRATE]` dès 30 prédictions labellisées, puis tous les +20). Tout ajustement de `K_MATCHUP`/`K_SYNERGY`/`SAME_LANE_WEIGHT` reste une décision manuelle, avec bump de `MODEL_VERSION` |
| 5 | **Évolution du modèle prédictif** (lane restante + robustesse au pire pick) | [SPEC-11](docs/specs/SPEC-11-lane-restante-et-recherche.md) 🟡 | ✅ **Étages a et b (portée réduite) mergés le 2026-09-06** — le vrai minimax multi-plis reste non actionable |
| — | Autres features candidates | — | À rouvrir après la calibration, aucune n'est bloquante |

### Dette signalée par SPEC-10 ✅ Soldée (2026-09-11)

- [x] `LCUClient._find_credentials_process()` (`src/lcu_client.py`) : token tronqué renvoyé tel
      quel au lieu d'échouer proprement — `password` réinitialisé à None après détection.
- [x] `BanRecommender.get_ban_recommendations()` (`src/analysis/ban_recommendations.py`) reçoit un
      paramètre `exclude_champions` (bans + picks, camp allié et ennemi) — l'invariant vit
      maintenant dans la classe qui produit la recommandation, relayé par
      `Assistant.get_ban_recommendations()` et alimenté par `BanAdvisor`
      (`handle_auto_ban_hover`, `show_adaptive_ban_recommendations`). Les bans précalculés en base
      (qui ne peuvent pas connaître l'état live) restent filtrés a posteriori côté `BanAdvisor`.

### Actions manuelles restantes

- [x] Migration appliquée : `predictions.game_id` (2026-09-05, une fois `lol_coach.py` fermé)
- [x] Scrape complet relancé au nouveau seuil de lane (@pj35, semaine du 2026-09-07) —
      `MIN_TOTAL_MATCHUPS` laissé tel quel, pas de besoin d'ajustement constaté

---

## 1. Dette de code — fichiers >500 lignes ✅ Soldé (2026-09-05)

Les 6 fichiers dépassant 500 lignes ont tous été démantelés, façon E9/E10 (façade mince +
modules/mixins par domaine, déplacement verbatim, tests de régression au besoin) :

| Fichier | Avant | Après | Approche |
|---|---|---|---|
| `src/db.py` | 1698 | 395 | `src/repositories/` — 7 modules, un par domaine de table (champions, matchups, matchups_draft, synergies, champion_scores, pool_bans, predictions, meta) |
| `src/parallel_parser.py` | 974 | 223 | Mixins par mode de scrape (`parallel_parser_legacy.py`, `parallel_parser_roles.py`) — état partagé (executor, verrous) trop dense pour une composition par domaine |
| `scripts/repair_data.py` | 650 | 363 | Moteur extrait vers `src/repair_engine.py` (même principe que `src/pipeline.py`/`scripts/update_all.py`) |
| `src/constants.py` | 593 | 465 | Normalisation de noms de champion (3 fonctions) extraite vers `src/champion_name_normalization.py` — le fichier reste surtout des listes de données statiques |
| `src/assistant.py` | 527 | 380 | Façade Team Builder (trio/holistic) extraite en mixin (`src/assistant_trio_facade.py`) |
| `src/parser.py` | 522 | 345 | Bandeau cookies (concern autonome) extrait en mixin (`src/parser_cookie_banner.py`) |

Plus gros fichier restant du projet : `src/lcu_client.py` (493 lignes) — sous le seuil.

## 2. Couverture — modules trio_*/ban_recommendations 🟠 → reclassé dans SPEC-10

**Diagnostic révisé le 2026-09-05 après mesure.** Ces modules sont en réalité bien couverts en
lignes (73,7 % à 88,4 % : `ban_recommendations` 73,7, `matchup_cache` 75,5, `trio_holistic` 77,9,
`trio_metrics` 81,0, `trio_weights` 86,3, `trio_counterpick` 88,4). Le problème n'est donc pas la
**quantité** de couverture mais sa **nature** : des tests de caractérisation qui figent le
comportement observé au lieu de spécifier le comportement attendu — ils passent tout aussi bien
quand le comportement est faux, et n'auraient pas détecté le bug lane.

Ajouter des tests de ligne ici n'apporterait rien. Ce qu'il faut, ce sont quelques tests
**d'intention** sur les invariants métier : c'est [SPEC-10](docs/specs/SPEC-10-couverture-chemin-critique.md) §3.5.
Les vrais trous de couverture sont ailleurs (`pool_selection_ui.py` 2,6 %, `lcu_client.py` 18,6 %,
`champion_utils.py` 33,3 %, `draft/phases.py` 40,0 %) — même spec, §3.1 à §3.4.

---

## Features candidates

*Sources : `docs/ROADMAP_2026.md` Horizon 3, `docs/TOURNAMENT_COACH_IMPROVEMENTS.md` (section
"Future Enhancements"), constats du 2026-09-04. Aucune n'est engagée — à trier par appétit,
et **après** le lot SPEC-08→10 : elles ajoutent de la surface à un moteur dont on ne sait pas
encore mesurer la qualité.*

1. ~~**UX de confiance**~~ → **engagée** : la fraîcheur est déjà affichée au démarrage
   (`src/data_freshness.py`, `lol_coach.py:111`) et le volume de games sur les recommandations du
   Live Coach. Le reste (volume sur les autres écrans) est SPEC-09 E5.
2. ~~**Calibration du modèle log-odds**~~ → **engagée** : SPEC-08 fournit le maillon manquant (le
   résultat réel des parties). L'exécution de `scripts/calibrate_model.py` et l'ajustement de
   `K_MATCHUP`/`K_SYNERGY`/`SAME_LANE_WEIGHT` deviendront possibles à ~30 parties labellisées,
   avec bump obligatoire de `MODEL_VERSION`. **C'est le prochain chantier naturel après SPEC-08.**
3. ~~**Évolution du modèle prédictif — lane restante**~~ → **engagée et mergée le 2026-09-06**
   (@pj35) — voir [SPEC-11](docs/specs/SPEC-11-lane-restante-et-recherche.md) 🟡. Décision
   explicite de @pj35 de ne pas attendre l'item 2 : les deux étages sont protégés par le même
   interrupteur automatique (≥30 prédictions labellisées) plutôt que par une attente manuelle.
   - **Étage a** (livré) : un candidat n'est plus pondéré que par les ennemis déjà pickés, mais
     aussi par la probabilité des lanes ennemies *encore ouvertes* (`champion_lanes.share`, sans
     nouveau scrape).
   - **Étage b** (livré, portée réduite "1 ply glouton" choisie parmi 3 options) : robustesse face
     au pire pick ennemi plausible restant, via un terme additif et strictement monotone —
     **pas** le vrai minimax multi-plis d'origine, qui reste hors périmètre (voir ci-dessous).
   - **Le vrai minimax multi-plis reste 🔵 non actionable** : ordre de pick/ban de la draft à
     modéliser, récursion, budget de calcul — tout reste à faire, et attend toujours une
     calibration réelle (item 2). Une recherche multi-plis compose l'erreur de son évaluation à
     chaque niveau, contrairement au terme additif de l'étage b qui ne compose rien.
4. **Intégration sites de draft externes** (DraftLol, etc.) — recherche disponible dans
   `docs/archive/DRAFT_SITES_INTEGRATION_RESEARCH.md` (restaurée le 2026-09-04, contenu d'octobre
   2025 à revalider). Dépend du reverse-engineering du WebSocket DraftLol — spike de 1-2 jours
   avant d'engager.
5. **Client local** (ex-« GUI légère », ex-Tâche #6) — élargi par @pj35 le 2026-10-04 en client de
   bureau complet (navigation, coaching, draft, motion design).
   **Engagée : [SPEC-21](docs/specs/SPEC-21-tableau-de-bord-local.md).** Repriorisée par @pj35 le 2026-09-26 : le suivi de progression de SPEC-19 (courbes par
   métrique, axes de travail) est son premier vrai besoin.
6. **Depuis `docs/TOURNAMENT_COACH_IMPROVEMENTS.md`** : chargement de draft depuis JSON,
   comparaison multi-drafts, templates de composition, simulation IA vs IA, base de drafts
   historiques, timer pick/ban, tracking explicite de phase ban/pick.
7. **Décision produit** : réactiver `TeamAnalyzer` (`src/analysis/team_analysis.py`, code testé
   mais appelé par aucun menu) sur un écran, ou le supprimer.

---

## Hors périmètre (tranché)

- ❌ Backend distant (Neon, API FastAPI, SaaS multi-utilisateurs)
- ❌ Migration Playwright — Cloudflare n'oppose plus de challenge
- ❌ Scraping en datacenter / GitHub Actions
- ❌ i18n, multi-plateforme
- ✅ GUI lourde : **rouverte par @pj35 le 2026-10-04**, devenue le client de SPEC-21 (fenêtre `pywebview`, pas de Qt ni d'Electron)
- ⏸️ Automatisation nocturne — **suspendue par choix**, mise à jour manuelle assumée

---

**Légende** : 🔴 = à traiter en priorité · 🟠 = important mais non bloquant
