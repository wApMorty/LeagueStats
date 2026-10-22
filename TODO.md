# TODO — LeagueStats Coach

**Mis à jour** : 2026-10-22 (SPEC-42 rédigée : maîtrise selon le matchup, à mesurer sur crawl.db ; SPEC-41 livrée : maîtrise personnelle dans le moteur de draft, mesurée sur crawl.db puis adoptée, recette @pj35 à faire ; SPEC-40 livrée : victoire immédiate sur les cartes de draft, comme le grimoire, recette @pj35 à faire ; SPEC-39 livrée : diagnostic complet et « Appliquer » sur l'écran Calibration, recette @pj35 à faire ; SPEC-38 livrée : trois pages de runes OneTricks au choix pendant la draft, recette @pj35 à faire ; SPEC-37 livrée : écran « Données » pour actualiser la base depuis le client, recette @pj35 à faire ; SPEC-36 livrée : morts sans contrepartie, axe et revue, recette @pj35 à faire ; SPEC-35 livrée : étude « Moneyball » du début de partie, aucune action adoptée ; SPEC-33 livrée : éclaireur et pastilles de forme en partie, terme de forme mesuré et refusé, recette @pj35 à faire, recette @pj35 à faire ; SPEC-32 livrée : classement MVP / ACE en post-game, recette @pj35 à faire ; SPEC-31 rédigée : situationnels liés au core ; SPEC-30 livrée, recette @pj35 à faire)
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

### Lot livré — SPEC-25, suivi de phase et capture de fin de partie (✅ 2026-10-07, recette @pj35 à faire)

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
| 117 | **Conditionnelle** au spike : notification de LP lue dans l'événement `/lol-ranked` | 3 | 112, 115 | ⬜✅ 2026-10-07 : 9 tests ; spike favorable (SPEC-25 §4.0) : `PhaseTracker.subscribe_events` passe les événements `/lol-ranked/v1/current-lp-change-notification` à `GameCapture.on_lcu_event`, qui met la notification de côté dès qu'elle naît (même photo que le sondage sur la fixture réelle ; un écran quitté avant toute lecture donne quand même les LP) ; l'écran de fin n'est pas lu dans l'événement |
| 118 | Clôture : exe, docs, `CHANGELOG.md`, SPEC-23 et SPEC-24, statuts | 2 | 114, 115, 116 | ⬜✅ 2026-10-07 : `python build_app.py` (83,2 Mo) puis `check_exe_assets.py` : 52 fichiers du client et 13 modules (dont `phase_tracker` et `post_game_watcher`, ajoutés au script) présents ; `PROJECT_STRUCTURE.md`, README, `CHANGELOG.md`, SPEC-23 (`step(phase)` lit la phase du tracker) et SPEC-24 (pastille), écarts à la rédaction en SPEC-25 §4.7, statuts ; **recette @pj35** : lancer l'exe pendant une partie classée, regarder la pastille (En file, Champion select, En partie, Fin de partie, Hors partie), cliquer « Rejouer » dans les 3 s après l'écran de fin, puis `SELECT lp_delta, game_id FROM rank_snapshots ORDER BY id DESC LIMIT 1` (non nul) et `SELECT raw_eog IS NOT NULL FROM game_records ORDER BY game_creation_utc DESC LIMIT 1` (1) |

### Lot suivant — SPEC-26, partie trouvée persistante et bascule en partie (✅ livré le 2026-10-08, recette @pj35 à faire)

[SPEC-26](docs/specs/SPEC-26-file-trouvee-persistante-et-bascule-en-partie.md) : après « Accepter », l'overlay se
referme puis se rouvre en entier tant que les autres joueurs n'ont pas accepté (`apply` rappelle `show`, la
séquence se rejoue) ; il doit rester jusqu'à l'ouverture de la draft. À la fin de la draft (`ChampSelect` vers
`GameStart`), le client bascule tout seul sur « En partie » (rouvre SPEC-24 §2 / §7 et SPEC-25 §7). Garde-fou de
30 s, contenu de l'attente et absence de réglage « à valider » (SPEC-26 §2). Découpage en SPEC-26 §5 (tâches
119 à 121, 10 pts) :

| # | Tâche | Pts | Dépend de | État |
|---|---|---|---|---|
| 119 | Banc `support_found_js.py`, régression rouge puis table de décision de l'overlay (`asking` / `held` / `entering`), `hold_max` et `enter_wait` | 5 | — | ✅ 2026-10-08 : 19 tests ; régression `test_regression_found_overlay_reopens.py` rouge avant (6 overlays créés pour 1 attendu) puis verte, banc `node` `tests/support_found_js.py` (horloge virtuelle), table de décision dans `found.js` (`expectDraft` supprimé), `FOUND_HOLD_MAX_S` = 30 s et `FOUND_ENTER_WAIT_S` = 1,5 s dans `/found/state` ; **recette @pj35** : accepter une vraie partie, l'overlay reste sur « Acceptée » puis s'efface sur la draft, et relever `playerResponse` et `state` du ready-check après acceptation |
| 120 | Bascule vers « En partie » : `Transition.go` exposé, sujet `phase` dans `found.js` | 3 | 119 | ✅ 2026-10-08 : 13 tests ; `window.Transition = { go }`, `found.js` écoute le sujet `phase` et appelle `Transition.go("/en-partie")` au seul passage `draft` vers `game` (jamais au premier événement vu, ni si `/en-partie` est déjà ouverte), `en_partie.js` inchangé ; **recette @pj35** : verrouiller les 10 champions, le client bascule sur « En partie » depuis la draft puis depuis une autre page |
| 121 | Clôture : SPEC-24 et SPEC-25 rouvertes, `CHANGELOG.md`, statuts | 2 | 119, 120 | ✅ 2026-10-08 : entrées Fix et Feature sous `[Unreleased]`, statut de SPEC-26, SPEC-24 §2 et §7, SPEC-25 §7 et README des specs à jour ; recette réelle laissée à @pj35 (SPEC-26 §6) |

### Lot suivant — SPEC-27, vérification des postes en partie (✅ livrée le 2026-10-12, recette @pj35 à faire)

[SPEC-27](docs/specs/SPEC-27-verification-des-postes-en-partie.md) : les postes adverses sont devinés pendant la draft
(85 % d'équipes adverses entièrement justes sur 69 parties, mesure rejouée) et plus jamais vérifiés ; l'écran « En
partie » garde le face-à-face et la build calculés dessus. Une fois la partie lancée, la Live Client API donne le poste
des dix joueurs : le Live Coach le confronte au poste prédit et, si besoin, recalcule face-à-face, duel, probabilité et
plan de build (approche A, validée le 2026-10-08). Déclencheur (source du poste, délai de stabilité) à fixer par le
spike de la tâche 122. Découpage en SPEC-27 §5 (tâches 122 à 128, 23 pts) :

| # | Tâche | Pts | Dépend de | État |
|---|---|---|---|---|
| 122 | Spike : `scripts/spike_live_positions.py`, relevé de 3 parties par @pj35 (champ `position` vs `detectedTeamPosition`), constantes | 3 | — | ✅ 2026-10-12 : relevé d'une partie classée (28 min) : `position` rempli pour les 10 joueurs dès le chargement, jamais modifié, 100 % conforme à l'écran de fin ; `REALITY_STABLE_S` = 10 s conservé ; SPEC-27 §4.1 ; deux parties de plus (dont une blind) à relever en recette |
| 123 | `roster_of` dans `LiveGame` et le sujet `ingame`, tests | 2 | — | ✅ 2026-10-12 : 3 tests ; `roster_of` dans `src/client/ingame.py`, clé `roster` dans les états `live` et `ended`, aucune identité |
| 124 | `reality_check.py` : `resolve_champions`, `real_lanes`, `compare`, tests | 5 | — | ✅ 2026-10-12 : 13 tests ; `resolve_champions`, `real_lanes` (équipe retenue si 5 postes valides et distincts), `compare` ; formes de noms Wukong, Nunu, Renata à confirmer par le relevé 122 |
| 125 | `LoadoutImporter.retarget` (calcul sans écriture dans le client LoL), `_import` inchangé, tests | 3 | — | ✅ 2026-10-12 : 3 tests ; `_import` scindé en `_compute` + application, `retarget` sans écriture dans le client LoL, tests existants inchangés |
| 126 | `RealityCheck.step` : stabilité, recalcul de l'analyse et de la build, republication du sujet `game`, console, remise à zéro, appel dans `monitor_loop` | 5 | 122, 123, 124, 125 | ✅ 2026-10-12 : 18 tests ; `RealityCheck.step` (stabilité 10 s de jeu, recalcul de `game` et de la build, `REALITY_MAX_CORRECTIONS` = 3, remise à zéro), appel dans `monitor_loop` en `InProgress` ; page choisie à la main : analyse recalculée, build conservée |
| 127 | Écran « En partie » (gabarit SPEC-30) : ligne d'état entre `.panel-head` et `table.ig-table` de `section.ig-draft`, marquage des lignes corrigées du tableau à 5 colonnes, `FinalAnalysis.reality` ; `scripts/measure_en_partie.py` reste `[OK]` avec la ligne réelle | 3 | 126 | ✅ 2026-10-12 : 12 tests ; ligne `.ig-reality` (quatre états), lignes `is-corrected` + « poste corrigé », `FinalAnalysis.reality` ; `measure_en_partie.py` `[OK]` : marge **30 px** (seuil 30, sans marge de sécurité : 33 px sans modèle, 30 px avec) |
| 128 | Clôture : `CHANGELOG.md`, statut, `docs/specs/README.md`, `PROJECT_STRUCTURE.md`, recette @pj35 | 2 | 127 | ✅ 2026-10-12 : `CHANGELOG.md`, statut de SPEC-27, README des specs et `PROJECT_STRUCTURE.md` à jour ; recette réelle laissée à @pj35 (SPEC-27 §6) |

### Lot suivant — SPEC-28, la draft suivante ne doit plus rester muette (✅ livrée le 2026-10-09, recette @pj35 à faire)

[SPEC-28](docs/specs/SPEC-28-draft-muette-apres-une-partie.md) : à l'enchaînement « Rejouer » puis file, le client dit
« Champion select » mais la console reste muette et l'écran Draft vide, tantôt en retard, tantôt jusqu'à la fin du
champ select (@pj35, 2026-10-09). Deux mécanismes : la boucle monofil est occupée par le travail d'après-partie et la
collecte (durée non mesurée, aucun chronomètre), et l'état de la partie précédente n'est ré-armé que si la boucle voit
`Lobby` ou `Matchmaking` (reproduit : sinon `_handle_draft_change` n'est jamais appelé). Approche B validée : épisode de
draft numéroté par le tracker, travail d'arrière-plan qui cède la main au champ select, chronométrage des tours.
Seuils et journal validés (SPEC-28 §2). Découpage en SPEC-28 §5 (tâches 129 à 132, 15 pts) :

| # | Tâche | Pts | Dépend de | État |
|---|---|---|---|---|
| 129 | `TickTimer`, étapes chronométrées de `monitor_loop` et de `GameCapture`, journal rotatif `logs/draft_monitor_ticks.log`, alerte console, délai de la draft | 3 | — | ✅ |
| 130 | Épisode de draft : `PhaseTracker.draft_episode`, réarmement dans la branche champ select, régression | 5 | — | ✅ |
| 131 | Céder la main : `LCUClient.yield_if`, `draft_pending()`, pose et remise dans `monitor_loop`, régression | 5 | 129 | ✅ |
| 132 | Clôture : `CHANGELOG.md`, statuts, README des specs, SPEC-25 §2 renvoyé ici, recette @pj35 | 2 | 130, 131 | ✅ |

### Lot suivant — SPEC-29, constats sur dix parties et axes par objectif (✅ livrée le 2026-10-11, recette @pj35 à faire)

[SPEC-29](docs/specs/SPEC-29-constats-sur-dix-parties-et-axes-par-objectif.md) : « Derniers constats » ne montre que la
dernière partie, et les axes de travail ne se proposent jamais (@pj35, 2026-10-10). Mesuré : sur 90 parties top, aucun
schéma négatif face à la norme (z moyen positif sur les 8 métriques), un seul axe jamais jugé en base. Validé : constats
sur 10 parties en une ligne par métrique avec bande de 10 points, axes choisis par l'écart à l'objectif OneTricks,
fixés seuls si le schéma est net, d'un clic sinon. Arbitrages de SPEC-29 §2 validés par @pj35 le 2026-10-11 (ordre des deux règles,
proposition au-dessus de l'objectif, verdict contre l'objectif de la partie, écran de référence). Découpage en
SPEC-29 §5 (tâches 133 à 137, 17 pts) :

| # | Tâche | Pts | Dépend de | État |
|---|---|---|---|---|
| 133 | Migration `coaching_goals.reference`, dépôt `goals()` / `insert_goal` | 2 | — | ✅ |
| 134 | Choix par l'objectif : `objective_gaps`, `Proposal`, `next_proposal` à deux étages, `set_goal(reference)`, `judge` contre l'objectif de la partie, régression | 5 | 133 | ✅ |
| 135 | Constats sur 10 parties : `window_gaps`, `home._findings`, gabarit et bande de points, route `reference` | 5 | 134 | ✅ |
| 136 | Tenir sur un écran : mesure en vraie fenêtre Chrome 1920×986 sur copie de la base, `scrollHeight` 1351 → 950 = `clientHeight` avec `notice` (cause : l'anneau décoratif, passé en `fixed`) ; cartes et lignes non compactées, 57 px de marge | 3 | 135 | ✅ |
| 137 | Clôture : CHANGELOG, statuts, README des specs, `latest_findings` supprimée, recette @pj35 (`alembic upgrade head`, accueil sur la vraie base, un clic sur « Fixer cet axe » puis la partie suivante) | 2 | 136 | ✅ |

### Lot suivant — SPEC-30, écran « En partie » sur un seul écran (✅ livrée le 2026-10-12, recette @pj35 à faire)

[SPEC-30](docs/specs/SPEC-30-ecran-en-partie-sur-un-ecran.md) : l'écran « En partie » empile quatre panneaux sur
~1 600 px pour 890 utiles à 1 920 × 950 (estimation arithmétique), dont ~600 pour la seule courbe. Validé par @pj35 le
2026-10-12 : deux colonnes (ma partie à gauche, win chance et face-à-face à droite) sous un bandeau d'une ligne, courbe
recalibrée, face-à-face sans Mat/Syn (en infobulle) et avec portraits, même écran de référence que l'accueil, mesure en
Firefox headless. Passe **avant** la tâche 127 de SPEC-27, réécrite pour ce gabarit. Découpage en SPEC-30 §5 (tâches
138 à 141, 13 pts) :

| # | Tâche | Pts | Dépend de | État |
|---|---|---|---|---|
| 138 | Vue : `Champions.by_name`, portrait, nom Data Dragon et infobulle Mat/Syn dans `_score`, tests | 3 | — | ✅ |
| 139 | Gabarit et CSS : bandeau, grille à deux colonnes, tableau à 5 colonnes, place de la ligne SPEC-27, `GAME_CURVE_SIZE`, tests | 5 | 138 | ✅ |
| 140 | Mesure : `scripts/measure_en_partie.py` (Firefox headless, cas le plus lourd, 1 920 × 986, ≥ 30 px de marge), ajustements. Mesuré : ancien gabarit `scrollHeight` 1 698 pour `clientHeight` 950 ; nouveau, 950 = 950, contenu 913 / 916 px (sans / avec modèle), marge 37 / **34 px**, `scrollWidth` 1 700 = 1 700 ; 1 400 × 900 : une colonne. Aucun ajustement de CSS (le script mesurait la marge sur `scrollHeight`, plafonné à `clientHeight` : mesure corrigée sur le bas du contenu) | 3 | 139 | ✅ |
| 141 | Clôture : SPEC-27 §4.6 et tâche 127 réécrites, `CHANGELOG.md`, statuts, README des specs, recette @pj35 | 2 | 140 | ✅ 2026-10-12 : SPEC-27 §4.6, §5 et critère 6 visent `section.ig-draft` ; entrée `[Unreleased]`, statut de SPEC-30 et README des specs à jour ; recette réelle laissée à @pj35 (SPEC-30 §6) |

### Lot suivant — SPEC-31, situationnels liés au core (✅ livrée le 2026-10-12, recette @pj35 à faire)

[SPEC-31](docs/specs/SPEC-31-situationnels-suivent-le-core.md) : « Situationnels » est rempli avec `popularItems`, sans
rapport avec le core choisi (mesuré le 2026-10-12 : 4 à 6 items sur 8 hors du chemin du core à Ambessa et Yorick) ;
`popPath`, que la page OneTricks publie par core, n'est jamais lu. Validé par @pj35 le 2026-10-12 : situationnels = suites
du core, autres seconds items de core dans un bloc « Autres cores », items du duel admis seulement dans le chemin, seuil de
bruit (liste plus courte). Restent à valider : valeur des deux seuils et volume du banc (12 pages). Découpage en SPEC-31 §5
(tâches 142 à 146, 15 pts) :

| # | Tâche | Pts | Dépend de | État |
|---|---|---|---|---|
| 142 | `_core_path`, `_item_blocks` (Situationnels par le chemin, bloc « Autres cores », repli), `Build.path_games`, constantes, fixture Ambessa, tests | 5 | — | ✅ 2026-10-12 : Ambessa = Death's Dance, Maw, Mortal Reminder / Autres cores Shojin, Voltaic, Profane Hydra (147 parties) ; Jinx 5 situationnels + 2 autres cores |
| 143 | Duel : chemin lu sur les deux pages, items du duel dans le chemin ou « Autres cores », `blocks[-1]` corrigé, tests réécrits | 3 | 142 | ✅ 2026-10-12 : core substitué par le duel (5 parties) = Situationnels vide, ancien core en tête d'« Autres cores » (seuils de §4.2, à relire) |
| 144 | Banc `scripts/bench_loadout_paths.py` (12 pages espacées de 20 s), réglage des deux seuils | 3 | 143 | ✅ 2026-10-12 : hors chemin 53 → 0, repli 0 / 12, médiane 8 → 4 situationnels ; seuils 5 % / 3 parties inchangés ; supports non mesurables (404, rôle `supp`) |
| 145 | Ligne console, bloc « Autres cores » dans l'écran « En partie », remesure `measure_en_partie.py` | 2 | 143 | ✅ 2026-10-12 : remesuré à 1 920 × 986, marge 33 / **30 px** (sans / avec modèle, était 37 / 34), une colonne à 1 400 × 900 |
| 146 | Clôture : `CHANGELOG.md`, notes SPEC-15, statuts, README des specs, recette @pj35 | 2 | 144, 145 | ✅ 2026-10-12 (recette réelle laissée à @pj35, SPEC-31 §6) |

### Lot SPEC-32, classement des joueurs en post-game (✅ livré le 2026-10-12, recette @pj35 à faire)

[SPEC-32](docs/specs/SPEC-32-classement-des-joueurs-post-game.md) : la revue de partie ne montre que l'impact du joueur ;
elle classe maintenant les dix joueurs par ΔP cumulé de SPEC-20 (portraits Data Dragon, déjà servis par `assets.py`), en deux
listes de cinq, avec la couronne MVP sur le meilleur de l'équipe gagnante et ACE sur le meilleur de la perdante. Validé par
@pj35 le 2026-10-12 : score = ΔP seul (pas de composite), deux listes, ACE attribué même à impact négatif (17 parties sur 98).
Emplacement du panneau (entre la courbe et les cartes) validé le 2026-10-12. Découpage en SPEC-32 §5 (tâches 147 à 150, 12 pts) :

| # | Tâche | Pts | Dépend de | État |
|---|---|---|---|---|
| 147 | `src/client/classement.py` : `ranking` (ΔP par participant, équipes, MVP / ACE, ex æquo, remake) et tests purs | 3 | — | ✅ 2026-10-12 : 12 tests purs |
| 148 | `game_page` : clé `ranking`, formatage et barres sur les dix joueurs, absence sans impact, tests de page | 2 | 147 | ✅ 2026-10-12 : 4 tests de page, review.py 471 lignes |
| 149 | Gabarit et CSS : deux listes, portraits, barres, badges MVP et ACE, rupture à 1 500 px, tests de rendu | 5 | 148 | ✅ 2026-10-12 : 4 tests de rendu (rendu à l'œil laissé à @pj35) |
| 150 | Clôture : vérification sur les 98 parties de la base, module ajouté aux listes, `CHANGELOG.md`, statuts, recette @pj35 | 2 | 149 | ✅ 2026-10-12 : 98 / 98 parties, 17 ACE négatifs ; recette à l'œil laissée à @pj35 |

### Lot SPEC-33, éclaireur des joueurs en partie (✅ livrée le 2026-10-21, recette @pj35 à faire)

[SPEC-33](docs/specs/SPEC-33-eclaireur-des-joueurs-en-partie.md) : dès l'écran de chargement, une pastille de niveau à côté
de chacun des dix champions du face-à-face (ΔP moyen sur 10 parties classées, taux de victoire en attendant), détail 5 / 10 / 20
en infobulle. Pool de threads dédié (« éclaireur ») avec son propre client LCU, parties rangées dans `crawl.db`, collecte en
pause pendant ce temps. Le terme de forme n'entre dans la win chance que s'il bat le modèle en place ; `crawl.db` ne couvre les dix joueurs que de 0,9 % des parties, d'où une table `crawl_histories` alimentée par la collecte.
Tous les arbitrages validés par @pj35 le 2026-10-13 (suite en partie à 2 threads, seuils de couleur au banc, adoption à
−0,002 de Brier sur les 10 premières minutes). Absorbe la tâche 62 de SPEC-23. Découpage en SPEC-33 §5 (tâches 151
à 161, 34 pts) :

| # | Tâche | Pts | Dépend de | État |
|---|---|---|---|---|
| 151 | `LCUClient` : statut thread-local, `pooled_session`, `get_player_history` (absorbe la tâche 62) | 2 | — | ✅ 2026-10-13 : 3 tests (statut par thread, pool, historique brut) |
| 152 | `src/winprob/form.py` (forme brute et impact par fenêtre) et tests | 2 | 151 | ✅ 2026-10-13 : 5 tests (dont `player_impact` sur la fixture 7998195590) |
| 153 | `src/winprob/scout.py` : pool, coordinateur, ordre par rang, cache et rangement dans `crawl.db`, 429, publication | 5 | 151, 152 | ✅ 2026-10-13 : 13 tests (dont la garde SQLite sur un vrai pool) |
| 154 | `scripts/bench_scout.py` (copie temporaire, paliers de workers, critères d'arrêt, quartiles) | 3 | 153 | ✅ 2026-10-13 : `--help` et refus en partie vérifiés ; `--dry-run` réel à faire avec la tâche 155 |
| 155 | Banc réel par @pj35 (lobby, Live Coach fermé) : `SCOUT_WORKERS` ; quartiles par `scripts/measure_scout_quartiles.py` (amendé le 2026-10-14) | 1 | 154 | ✅ 2026-10-15 : `SCOUT_WORKERS` = 4 (10 impacts en 21,6 s), parties après les dix historiques ; seuils (−3,8 ; +4,0) sur 21 177 joueurs |
| 156 | Branchement : lancement en `InProgress`, arrêt, pause de la collecte, sujet `players` | 3 | 153 | ✅ 2026-10-13 : 5 tests ; forme de la session gameflow journalisée à la première partie réelle |
| 157 | Écran « En partie » : pastilles et infobulle dans le face-à-face, remesure de la marge | 5 | 155, 156 | ✅ 2026-10-15 : 16 tests ; pastille dans la cellule Tot (§4.4), marge 30 px à 1 920 × 986 |
| 158 | `crawl_histories` : forme brute rangée à chaque visite d'historique (aucune requête de plus) | 3 | 152, 153 | ✅ 2026-10-13 : 2 tests (visite de la collecte, éclaireur) |
| 159 | `scripts/measure_form_term.py` : seuil figé, mesure du terme de forme une fois `crawl_histories` fournie | 5 | 158 | ✅ 2026-10-15 : script livré, 6 tests, essai `--force --limit 3000` en 113 s ; mesure faite le 2026-10-21 (92 689 parties) : `form_wr`, `form_kda` et `form_impact` refusés (meilleur gain +0,0013 < 0,002, SPEC-33 §7) |
| 160 | Clôture : `CHANGELOG.md`, statuts, README des specs, structure, exe, recette @pj35 | 2 | 157, 159 | ✅ 2026-10-21 ; exe : éclaireur et pastilles livrés depuis la 5.4.0 ; recette (pastilles en partie, forme de la session gameflow) laissée à @pj35 |
| 161 | *Conditionnelle* : terme de forme dans le modèle si la tâche 159 l'adopte | 3 | 159 | ➖ sans objet : la tâche 159 refuse les trois variables (2026-10-21) |
| 162 | Visites de couverture : après chaque partie lue, historique de ses joueurs non couverts (amendement du 2026-10-15) | 2 | 158 | ✅ 2026-10-15 : 2 tests ; couverture à suivre par `scripts/monitor_crawl.py` |

### Lot SPEC-34, vitrine : mode démo, captures, README et teaser (✅ livrée le 2026-10-16, recette @pj35 à faire)

[SPEC-34](docs/specs/SPEC-34-vitrine-readme-et-teaser.md) prépare la présentation pro. Un mode démo,
`scripts/demo_client.py`, rejoue un scénario (profil, file, draft, partie, revue) sans client LoL, avec des pseudos
fictifs et sur une copie de `db.db`. Des captures Firefox headless en 1 920 × 1 080 en sont tirées. Le README est
réécrit, centré sur le produit et illustré (boucle GIF, captures). Un teaser Remotion muet de 30 s est rangé dans
`docs/presentation/video/`. Tous les arbitrages ont été validés par @pj35 le 2026-10-15, dont le moteur du mode démo :
pile réelle sur faux LCU (§3). Découpage en SPEC-34 §5 (tâches 163 à 170, 29 pts) :

| # | Tâche | Pts | Dépend de | État |
|---|---|---|---|---|
| 163 | `DemoConfig`, `scripts/demo/lcu/`, `scripts/demo_client.py` (copie de la base, faux LCU des écrans Client, CLI) ; 2 tests | 3 | — | ✅ 2026-10-15 : 4 tests ; faux LCU servi en HTTP local (spec §4.3 amendée) ; `db.db` et `crawl.db` inchangés après une démo réelle |
| 164 | Scénario de draft : `scenario.json`, sessions construites, écritures acceptées, `DraftMonitor` réel ; 2 tests | 5 | 163 | ✅ 2026-10-16 : 3 tests ; démo réelle : recommandations Dr. Mundo 55,96 %, Ornn, Shen contre Darius, build OneTricks importée, analyse finale à 54,62 % ; `db.db` inchangée |
| 165 | Partie simulée : trames générées, `LiveGame(fetch=…)`, revue et coaching ; 1 test | 3 | 164 | ✅ 2026-10-16 : 6 tests ; démo réelle : courbe de 24 points sur 25 min, 10 pastilles de l'éclaireur, build et face-à-face (les scènes de partie repassent par la draft verrouillée), revue avec MVP/ACE ; modèle de win chance copié avec la base |
| 166 | `scripts/_firefox.py`, `scripts/capture_screens.py`, captures, `manifest.json`, images du README | 3 | 165 | ✅ 2026-10-16 : 13 captures en 1 920 × 1 080 relues à l'œil, courbe de 26 points, images du README de 181 à 357 Ko ; `db.db` inchangée ; `measure_en_partie.py` repasse (marge 30 px) |
| 167 | `README.md` réécrit avec captures et avertissement Riot ; `.gitignore` de `docs/presentation/` | 2 | 166 | ✅ 2026-10-16 : 9 captures, chiffres du manifeste (173 champions, 57 612 matchups), section démo ; image de tête provisoire (`draft-pick.png`) jusqu'au GIF de la tâche 169 |
| 168 | Projet Remotion : versions exactes, config, polices, scènes « Accroche », « Draft », « Verrouillage » et « Clôture » | 5 | 166 | ✅ 2026-10-16 : Remotion 4.0.531 (licence gratuite pour un particulier, vérifiée sur LICENSE.md), polices du client, chiffres de draft relevés dans le manifeste par `capture_screens.py` (n° 1 Dr. Mundo 55,96 %, fin de draft 54,6 %) |
| 169 | Scènes « En partie » (courbe SVG), « Revue et coaching » et « Mosaïque » ; `hero.gif` dans le README | 5 | 167, 168 | ✅ 2026-10-16 : teaser de 30,0 s en 1 920 × 1 080 sans audio (12,2 Mo) ; `hero.gif` 960 × 540 à 10 i/s, 4,1 Mo, encodé par ffmpeg (palette optimisée ; l'encodeur GIF de Remotion donnait 10,3 Mo), fond figé dans la boucle |
| 170 | Clôture : `CHANGELOG.md`, statuts, README des specs, structure ; recette à l'œil de @pj35 | 3 | 169 | ✅ 2026-10-16 ; recette à l'œil (captures, GIF, `docs/presentation/video/out/teaser.mp4`) laissée à @pj35 |

### Lot SPEC-42, maîtrise selon le matchup (🟡 rédigée le 2026-10-22)

[SPEC-42](docs/specs/SPEC-42-maitrise-selon-le-matchup.md) mesure si la maîtrise de SPEC-41 doit dépendre du
vis-à-vis de lane. Constat : Olaf (+5,4 pts de maîtrise) passe devant tout le pool, car le duel de lane du moteur
reste dans ±1,2 pt (Kennen contre Darius +1,2, Olaf 0,0) ; ses 30 parties n'ont pas eu de drafts plus favorables,
mais Olaf contre Gangplank donne 2 défaites à ΔP −14 et −11. Trois variantes ajoutées à l'étude : e, interaction
maîtrise × duel de lane ; f, maîtrise par vis-à-vis rétrécie vers celle du champion ; g, les deux. Même seuil et
même règle de choix que SPEC-41. Arbitrages validés le 2026-10-22. Découpage en SPEC-42 §5 (tâches 204 à 208,
13 pts, dont 206 et 207 conditionnelles) :

| # | Tâche | Pts | Dépend de | État |
|---|---|---|---|---|
| 204 | `src/analysis/mastery.py` : `matchup_shrink_k`, `leave_one_out_matchup_deviation`, `matchup_deviations` + tests | 2 | — || ✅ 2026-10-22 : 4 tests ; K₂ synthétique retrouvé à 12,97 pour 16 (graine fixe), leave-one-out identique au recalcul sur 200 tirages |
| 205 | `scripts/measure_mastery_term.py` : variantes e, f, g, `decide` à plusieurs coefficients, mesure, résultat en §8 | 5 | 204 | |
| 206 | *Conditionnelle (205)* : `MasteryTerm` avec vis-à-vis et duel, recherche, grimoire, analyse finale + tests | 3 | 205 | |
| 207 | *Conditionnelle (205)* : sous-ligne « dont toi sur X contre Y » (snapshot, cartes, console) + tests | 2 | 206 | |
| 208 | Clôture : critères, `CHANGELOG.md`, statuts, README des specs | 1 | 205 (207 si adoptée) | |

### Lot SPEC-41, maîtrise personnelle dans le moteur de draft (✅ livrée le 2026-10-21, recette @pj35 à faire)

[SPEC-41](docs/specs/SPEC-41-maitrise-personnelle-dans-le-moteur.md) ajoute au moteur un terme de maîtrise par
champion, tiré de l'impact ΔP de SPEC-20 (et non du winrate). Sur 5 parties, Gnar fait 3 victoires mais un impact de
−10,5 pts par partie, soit −2,8 pts une fois rétréci (K ≈ 13,5). Sur 141 parties de @pj35, le gain ne se mesure pas
(Brier 0,2496 → 0,2502). D'où une étude sur `crawl.db` d'abord : on adopte si le coefficient et le gain de Brier ont
un IC95 qui exclut 0. Si c'est le cas, le terme est additif sur mon pick (recherche, grimoire, analyse finale
affichée, blind pick), avec « dont toi sur Gnar » sur les cartes. Tous les arbitrages validés le 2026-10-21, dont
le rattrapage dans `game_records` et la prédiction journalisée sans le terme. Découpage en SPEC-41 §5 (tâches 196
à 203, 21 pts, dont 200 à 202 conditionnelles) :

| # | Tâche | Pts | Dépend de | État |
|---|---|---|---|---|
| 196 | `src/analysis/mastery.py` : `Mastery`, `shrink_k`, `masteries` (variantes a et b) + tests | 3 | — | ✅ 2026-10-21 : 6 tests ; K synthétique retrouvé à 15,56 pour 16 (n0, groupes déséquilibrés) |
| 197 | Spike `scripts/spike_lcu_history_pages.py` : pagination `begIndex` ≥ 20, détail et timeline de la plus ancienne | 1 | — | ✅ 2026-10-21 : `begIndex=20` renvoie les mêmes 20 parties, le LCU ignore la pagination |
| 198 | *Conditionnelle (197)* : `scripts/backfill_own_games.py` par le chemin de la capture, test sur faux LCU | 3 | 197 | ❌ Abandonnée le 2026-10-21 : pas de pagination (197) |
| 199 | `scripts/measure_mastery_term.py` : étude sur `crawl.db`, seuil figé, résultat et décision en §8 | 5 | 196 | ✅ 2026-10-21 : **adopté** (variante a), 81 969 parties, 24 438 joueurs focaux ; b = 0,0717 logit/pt [0,060 ; 0,084], gain de Brier +0,00008 [+0,00005 ; +0,00011], K = 42,4 ; Gnar −2,0 pts de victoire |
| 200 | *Conditionnelle (199)* : `MasteryTerm`, terme à la racine de la recherche, `SearchResult.personal_points`, console + tests | 3 | 199 | ✅ 2026-10-21 : terme chargé au démarrage et à chaque nouvelle draft ; sur la vraie base Gnar −2,0 pts, Olaf +5,7, Ambessa −3,2 |
| 201 | *Conditionnelle (199)* : grimoire, analyse finale (affichée seulement), blind pick + tests | 3 | 200 | ✅ 2026-10-21 : grimoire et analyse finale affichée avec ma maîtrise, prédiction journalisée sur la draft seule, blind pick en points de victoire |
| 202 | *Conditionnelle (199)* : snapshot et sous-ligne « dont toi sur X » des cartes + tests | 2 | 200 | ✅ 2026-10-21 : sous-ligne « dont toi sur X : ±n pts (k parties) » ou « aucune partie sur X » ; 302 tests du client et des régressions verts |
| 203 | Clôture : critères, `CHANGELOG.md`, statuts, README des specs | 1 | 199 (202 si adoptée) | ✅ 2026-10-21 ; recette @pj35 à faire (une draft réelle avec Gnar dans la pool : sous-ligne « dont toi sur Gnar », classement) |

### Lot SPEC-40, victoire immédiate sur les cartes de draft (✅ livrée le 2026-10-20, recette @pj35 à faire)

[SPEC-40](docs/specs/SPEC-40-victoire-immediate-sur-les-cartes-de-draft.md) aligne les cartes de recommandation et la
jauge sur le grimoire. Aujourd'hui la carte montre la fin de draft attendue de la recherche (adversaires qui contrent
au mieux), toujours sous la position actuelle, et le grimoire la victoire si je verrouille maintenant : en B2, cartes
48,22 / 48,16 / 48,10 % (−1,2 pt) contre 49,48 / 50,27 / 49,95 % au grimoire. Le gros chiffre devient l'immédiat,
la fin de draft passe en sous-ligne et garde l'ordre, l'écart vaut immédiat − position, la jauge suit tout champion
survolé. Arbitrages validés le 2026-10-20. Découpage en SPEC-40 §5 (tâches 194 et 195, 4 pts) :

| # | Tâche | Pts | Dépend de | État |
|---|---|---|---|---|
| 194 | `_immediate`, cartes (gros chiffre, écart, sous-ligne) et `state.win` / `state.names` dans `draft_view.py` ; test de régression rouge puis vert ; tests de la jauge et du repli | 3 | — | ✅ 2026-10-20 : régression rouge puis verte (carte Aatrox 54,82 % → 50,27 %, comme sa tuile) ; `state.win` couvre tout champion libre |
| 195 | Barre du grimoire (`_info`) avec les deux chiffres et son test ; `CHANGELOG.md`, statuts, README des specs ; recette @pj35 | 1 | 194 | ✅ 2026-10-20 : barre à deux chiffres, `test_meta_des_tuiles_en_pick` mis au nouveau texte ; suite complète 2 847 tests verte ; recette @pj35 à faire (cartes = tuiles du grimoire en draft réelle) |

### Lot SPEC-39, écran Calibration : diagnostic complet et « Appliquer » (✅ livrée le 2026-10-20, recette @pj35 à faire)

[SPEC-39](docs/specs/SPEC-39-calibration-appliquee-depuis-le-client.md) complète l'écran Calibration avec la fin de
`calibrate_model.py` : facteur d'échelle, intervalle à 90 % et K suggérés, affichés d'office (66 ms de calcul). Un
bouton « Appliquer » reprend la règle du Live Coach (≥ 100 issues, intervalle qui exclut 1,0) : il écrit
`calibration.json` et vaut tout de suite pour le Live Coach du client, qui ne pouvait pas répondre au « o/n »
console. Grisé en draft, en partie, sur une ancienne version, et aujourd'hui (`spec13-v1` : facteur 0,613,
intervalle de −1,17 à 2,25, refus « l'intervalle atteint 0 »). Arbitrages validés le 2026-10-20. Découpage en SPEC-39 §5 (tâches 191 à 193, 7 pts) :

| # | Tâche | Pts | Dépend de | État |
|---|---|---|---|---|
| 191 | `Diagnostic` et `diagnose()` dans `calibration_notice.py`, `build_proposal` qui s'appuie dessus ; `phase_reason` dans `data.py` ; champs de `calibration_view` ; tests | 3 | — | ✅ 2026-10-20 : 13 tests ; `phase_reason` dans `data.py` (cycle d'import avec `donnees.py`) ; sur `db.db` : facteur 0,613, intervalle [−1,17 ; 2,25], refus « l'intervalle atteint 0 » |
| 192 | Route `POST /calibration/appliquer`, phase dans `GET /calibration`, gabarit et CSS ; tests de route | 3 | 191 | ✅ 2026-10-20 : 9 tests (409 en draft, en partie et sur refus du diagnostic, 403 sans jeton, écriture de `calibration.json` en `+cal1`, 500 sans changement) ; garde htmx des 409/500 sur `#calib`, la cible de `htmx:beforeSwap` ; échange réel à voir à la recette |
| 193 | Clôture : `CHANGELOG.md`, statuts, README des specs, recette @pj35 | 1 | 192 | ✅ 2026-10-20 (docs) ; recette @pj35 à faire (bouton grisé avec la raison sur l'écran réel) |

### Lot SPEC-38, trois pages de runes OneTricks au choix (✅ livrée le 2026-10-20, recette @pj35 à faire)

[SPEC-38](docs/specs/SPEC-38-trois-pages-de-runes-onetricks.md) ajoute à la colonne « Runes & sorts » de la draft un
écran superposé avec les trois pages de runes les plus recommandées par OneTricks : la page de l'import du lock-in
(affinée au duel), puis les deux pages publiées les plus jouées ensuite, chacune avec sa part (et sa part contre
l'adversaire de lane, informative). « Choisir » écrit la page dans le client et prime sur l'import. Aucune requête
OneTricks de plus (pages en cache). Arbitrages validés le 2026-10-20. Découpage en SPEC-38 §5 (tâches 187 à 190,
11 pts) :

| # | Tâche | Pts | Dépend de | État |
|---|---|---|---|---|
| 187 | `RunePage`, `loadout.rune_pages()`, `LOADOUT_RUNE_PAGES` + 5 tests sur fixtures | 3 | — | ✅ 2026-10-20 : 7 tests (Ambessa 8,2 / 7,6 / 6,9 %, parts du duel Jinx contre Draven, page adaptée en tête, sans doublon, une page, `popRunes` absent, `count`) |
| 188 | `draft_loadout.pages()` et route `GET /draft/loadout/pages` + tests | 2 | 187 | ✅ 2026-10-20 : 6 tests (trois pages Jinx, page 1 = plan, parts du duel contre Draven sur 40 parties, pages après verrouillage depuis OneTricks, champion inconnu et page indisponible, sans champ select) |
| 189 | Écran « Pages OneTricks » : bouton, écran superposé, `pageCard` paramétré, `is-diff`, « Choisir » qui écrit, CSS + test du script | 5 | 188 | ✅ 2026-10-20 : `node --check` propre, test du script ; rendu à juger à la recette |
| 190 | Clôture : `CHANGELOG.md`, statuts, README des specs, recette @pj35 en draft réelle | 1 | 189 | ✅ 2026-10-20 (docs) ; recette @pj35 à faire |

### Lot SPEC-37, écran « Données » : actualiser la base depuis le client (✅ livrée le 2026-10-20, recette @pj35 à faire)

[SPEC-37](docs/specs/SPEC-37-ecran-donnees-et-actualisation.md) ajoute au groupe Coaching un écran « Données » : un
bouton « Actualiser » lance `run_pipeline` dans un fil du client, et la page (relue toutes les 2 s par htmx) suit
l'étape, une jauge par lane (`43/67`, échecs), les champions en cours, le temps écoulé et restant, puis le bilan du
dernier passage. Le scrape dure 1 h 40 et vide la base en cours de route (mesuré le 2026-10-20 : 0 ligne dans
`champion_scores`) : bouton grisé en draft et en partie, verrou PID contre un run console simultané, fermeture de la
fenêtre confirmée puis arrêt propre et restauration de la sauvegarde. Arbitrages validés le 2026-10-20. Découpage en
SPEC-37 §5 (tâches 181 à 186, 18 pts) :

| # | Tâche | Pts | Dépend de | État |
|---|---|---|---|---|
| 181 | Progression et arrêt : `progress`/`stop` dans `parse_page_by_role`, `scrape_all_multilane`, `run_pipeline` ; `PipelineCancelled` restaure ; `db_meta.last_scrape_lanes` | 5 | — | ✅ 2026-10-20 : 7 tests (événements start/done, arrêt sans écriture après, rappel en panne ignoré, plan avant la 1re lane, arrêt entre lanes, restauration, bilan par lane) ; `Progress` et `PipelineCancelled` dans `src/progress.py` (cycle d'imports) |
| 182 | Verrou `data/update.lock` (PID, `psutil`) dans `run_pipeline`, `UPDATE_LOCK_FILE` | 2 | — | ✅ 2026-10-20 : 4 tests (PID vivant refusé sans sauvegarde ni scrape, PID mort et fichier illisible repris, verrou levé après succès et échec) |
| 183 | `src/client/donnees.py` : `UpdateJob` (fil, état, ETA, logging restauré, `cancel`) et `donnees_view` ; constantes `DONNEES_*` | 3 | 181 | ✅ 2026-10-20 : 9 tests (lanes et champions en cours, échecs, ETA à 5 pages, double lancement, logging restauré, run qui lève, arrêt, `db_meta` tolérant, vue) |
| 184 | Écran Données : routes, `NAV`, gabarits, CSS, refus en `draft`/`game`, bandeau de l'écran Draft | 5 | 182, 183 | ✅ 2026-10-20 : 7 tests (page et lien actif, sondage seulement pendant un run, 409 en draft et en partie, 403 sans jeton, bandeau du Draft) ; bandeau à clé `updating` pour la synchro par clé de `draft.js` |
| 185 | Fermeture gardée : `window.run(should_close)`, dialogue de confirmation, `cancel` dans `launch.py` | 2 | 183 | ✅ 2026-10-20 : 4 tests (fermeture libre à l'arrêt, « non » garde la fenêtre, « oui » arrête avec le délai, câblage sur faux `webview` et garde en échec) ; dialogue réel à voir à la recette |
| 186 | Clôture : `CHANGELOG.md`, statuts, README des specs, `docs/PROJECT_STRUCTURE.md`, recette @pj35 | 1 | 184, 185 | ✅ 2026-10-20 (docs) ; recette @pj35 à faire |

### Lot SPEC-36, morts sans contrepartie : axe et revue (✅ livrée le 2026-10-20, recette @pj35 à faire)

[SPEC-36](docs/specs/SPEC-36-morts-sans-contrepartie.md) traduit SPEC-35 en jeu : au top, une mort sans contrepartie
avant 14 min coûte −6,6 pts de win chance, et tes parties à 2 ou plus se gagnent à 27 % (64 % à 0). La règle passe
dans `metrics.death_trades` et devient la métrique « Morts sans contrepartie avant 14 min » (grille des cinq rôles,
poids 2). Un axe à cible fixe ≤ 1 (référence `fixed`) se fixe d'un clic dans l'accueil, à la place de « Morts / 10 min ».
La revue de partie liste tes morts avant 14 min, échangées ou non, avec leur ΔP. @pj35 lève le seuil de SPEC-35 à sa
décision ; arbitrages validés le 2026-10-20. Découpage en SPEC-36 §5 (tâches 177 à 180, 9 pts) :

| # | Tâche | Pts | Dépend de | État |
|---|---|---|---|---|
| 177 | `metrics.death_trades` (règle déplacée de `moneyball.py`), métrique `untraded_deaths_14`, grille des cinq rôles, `GRID_VERSION` 2 | 3 | — | ✅ 2026-10-20 : 8 tests (échange le plus proche, fenêtre, métrique égale à l'étude, grille) ; tests Moneyball inchangés |
| 178 | Référence `fixed` : `GOAL_FIXED_TARGETS`, `set_goal` | 2 | 177 | ✅ 2026-10-20 : 4 tests (axe fixe sans historique, verdict à ≤ 1, route de l'accueil, choix sur une place libre) |
| 179 | Revue : panneau « Tes morts avant 14 min », `MONEYBALL_DEATH_PTS` | 3 | 177 | ✅ 2026-10-20 : 3 tests (morts échangées et ΔP stocké, mort sans contrepartie dans la page, pas de panneau sans timeline) ; un objectif inconnu d'`event_kind` (Atakhan) se dit « Objectif » |
| 180 | Clôture : `CHANGELOG.md`, statuts, README des specs, structure, recette @pj35 | 1 | 178, 179 | ✅ 2026-10-20 (docs) ; recette @pj35 à faire |

### Lot SPEC-35, étude « Moneyball » du début de partie (✅ livrée le 2026-10-20, rien d'adopté)

[SPEC-35](docs/specs/SPEC-35-etude-moneyball-du-debut-de-partie.md) classe les actions des 14 premières minutes (CS,
morts, morts solo, morts sans contrepartie, présence aux objectifs) par les points de win chance que @pj35 y laisse par
partie. Chaque action est valorisée par une logistique par rôle sur `crawl.db`, en écart à l'adversaire de lane. L'écart
de @pj35 se lit contre ses adversaires de lane de `game_records`. Le ΔP de SPEC-20 sert de recoupement ; la vision reste
hors classement, faute de ward dans la timeline. Adoption à ≥ 1 pt de win chance par partie, effet et écart significatifs,
seuil figé avant la mesure (arbitrages validés par @pj35 le 2026-10-20). Découpage en SPEC-35 §5 (tâches 171 à 176,
21 pts) :

| # | Tâche | Pts | Dépend de | État |
|---|---|---|---|---|
| 171 | `src/coaching/moneyball.py` : actions à 14 min par joueur, lignes par rôle, écarts de @pj35 ; `impact.present` public | 3 | — | ✅ 2026-10-20 : 12 tests (CS, morts, mort solo, sans contrepartie à 15 / 25 s, présence, exclusions) |
| 172 | `value_actions` : trois variantes, effet marginal, IC95 de Wald, signes sur 5 blocs, Brier contre la constante | 5 | 171 | ✅ 2026-10-20 : 1 test (synthétique : CS retrouvé à 1,92 pt / unité, IC [1,73 ; 2,11], présence nulle, Brier sous la constante) |
| 173 | `player_gap` (bootstrap à graine fixe) et `decide` (seuil du §2) | 3 | 172 | ✅ 2026-10-20 : 6 tests (moyenne et IC, graine, IC d'effet qui contient 0, gain 0,99, premier au gain seul adopté, Brier à la constante) |
| 174 | `scripts/measure_moneyball.py` : tableau par rôle, tableau Moneyball, recoupement SPEC-20, vision hors classement | 3 | 173 | ✅ 2026-10-20 : 2 tests (sorties et lecture seule, exclusion des parties de @pj35) ; essai `--limit 5000` en 104 s, 4 815 parties retenues |
| 175 | Mesure réelle, résultat en §8, `TODO.md`, `CHANGELOG.md`, statuts | 2 | 174 | ✅ 2026-10-20 : 78 347 parties ; aucune action adoptée (@pj35 : +10 CS à 14 min, morts non significatives) |
| 176 | *Conditionnelle* : axe Moneyball proposé dans l'accueil du coaching | 5 | 175 | ❌ Abandonnée : rien d'adopté |

### Lot suivant — SPEC-22, attribution complète de l'impact (🟡 rédigée le 2026-10-04)

[SPEC-22](docs/specs/SPEC-22-attribution-complete-impact.md) : le « −20 pts non attribué » du rapport
d'impact vient à −23 pts des objectifs perdus, que personne ne porte (mesuré sur 45 parties) ;
l'impact cumulé du joueur est biaisé vers le haut d'autant. Objectifs perdus débités aux absents,
niveaux face à l'adversaire de lane, récupération après respawn ; le modèle de SPEC-20 reste
unique. Vision, placement et vague hors périmètre (@pj35, 2026-10-04). Conventions du §2 à valider.
Découpage en SPEC-22 §5 (tâches 57 à 61, 16 pts) :

| # | Tâche | Pts | Dépend de | État |
|---|---|---|---|---|
| 57 | `scripts/bench_impact_residual.py` : base de référence du résidu (−20,3 / 25,1 pts) | 2 | — | ✅ 2026-10-13 : base à 108 parties (45 en spec) : −21,4 / 24,0, objectifs adverses −24,0, dérive +2,5 ; maximum 144,7 |
| 58 | Objectifs perdus : lignes `lost_*` aux coéquipiers absents | 3 | 57 | ✅ 2026-10-13 : 4 tests (symétrie, cinq présents, absents seuls, kill) + 1 test du rapport |
| 59 | `WinModel.logit_parts`, segments par joueur, lignes `levels` et `respawn` | 5 | 58 | ✅ 2026-10-13 : résidu de 109 parties : +0,8 / 10,1 pts (max 39,6), 7 tests |
| 60 | Convention versionnée dans `model_version`, `raw_eog`, recalcul des 45 parties | 3 | 59 | ✅ 2026-10-13 : rattrapage joué sur une copie de la base (107 parties, 0 hors `+c2`) ; recalcul de la base réelle ⬜ @pj35 |
| 61 | Rapport, bilan, libellés, mesure finale, `CHANGELOG.md` | 3 | 60 | ✅ 2026-10-13 : résidu +0,8 / 10,1 pts sur 109 parties (avant −21,4 / 24,0) |

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
| 62 | `LCUClient.last_status_code` thread-local, session de collecte à pool dimensionné | 2 | — | ✅ 2026-10-13, absorbée par SPEC-33 tâche 151 |
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
- ❌ A priori de la draft dans la win chance en partie — **mesuré et écarté par @pj35 le 2026-10-19**. Logit de draft
  (`GameEvaluator.team_logit`, postes par `participant_roles`) en variable du modèle de partie, avec son produit par le
  temps, sur les 9 821 parties les plus récentes de `crawl.db` (validation croisée poolée à 5 blocs) : Brier ≤ 10 min
  0,2336 → 0,2331 (**gain 0,0005**, seuil de SPEC-33 : 0,002), AUC 0,801 → 0,802. La draft seule : Brier 0,2494 contre
  0,2500 pour une constante ; bien calibrée (quintile extrême : 55,4 % prédits, 54,0 % observés) mais faible (p10-p90
  de 45 à 55 %). La courbe qui part de ~50 % est donc juste à ±5 pts près.
- ❌ Draft au seul matchup 2v2 (Top/Mid contre leur lane et le jungle adverse, bot contre bot) — **mesuré le
  2026-10-20**, le poids actuel 2/1 reste. Spike hors `src/` sur 78 163 parties de `crawl.db` (solo/duo, 10 rôles
  connus), validation croisée poolée à 5 blocs, régression logistique sur le logit de `GameEvaluator` (paires sans
  poids de lane). Brier : constante 0,2500, actuel 2/1 + synergies 0,2492, masque 2v2 0,2494 (**−0,0002 contre
  l'actuel, IC95 bootstrap −0,0003 à −0,0001**, synergies ou non), matrice 5×5 symétrique ajustée (15 paires +
  synergies) 0,2493 (−0,00003, IC95 −0,0001 à +0,00004). Poids ajustés : même lane 1,6 à 2,2, bot-support 1,1,
  jungle contre top/mid/bot/support 0,5 à 0,8, paires éloignées 0,2 à 0,4 (± ~0,5 chacun). Le jungle ne ressort
  donc pas, et couper les paires éloignées retire du signal. Couverture des paires inter-rôles : 93 à 97 %.
- ❌ Axe de travail « Moneyball » du début de partie — **mesuré le 2026-10-20** ([SPEC-35](docs/specs/SPEC-35-etude-moneyball-du-debut-de-partie.md)
  §8), rien d'adopté. Logistique par rôle sur 78 347 parties de `crawl.db` (écarts à l'adversaire de lane à 14 min) :
  au top, une mort vaut −3,3 pts de win chance, une mort sans contrepartie −6,6, 10 CS +1,2, la présence aux
  objectifs rien. @pj35 (135 parties au top) n'est en retard sur aucune action : +10 CS à 14 min (IC95 +5 à +15),
  morts non significatives. Seuil figé d'avance : effet et écart significatifs, gain ≥ 1 pt par partie.

---

**Légende** : 🔴 = à traiter en priorité · 🟠 = important mais non bloquant
