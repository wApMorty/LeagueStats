# TODO — LeagueStats Coach

**Mis à jour** : 2026-09-24 (replanification après le spike OneTricks, puis ajout de SPEC-17 — voir §Priorités)
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

### Sprint 2 — Import OneTricks dans le client (~18 pts)

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
| 14 | Recette en partie réelle : vérifier les corps de requête LCU contre le client (non documentés par Riot) | SPEC-15 §3.3 | 1 | 12 | ⬜ |

### Sprint 3 — Recherche minimax plus pertinente et plus profonde (~12 pts)

**Objectif** ([SPEC-17](docs/specs/SPEC-17-recherche-plus-profonde.md), validée par @pj35 le
2026-09-24) : à budget constant (2 s, mono-thread), la recherche n'examine que des picks
réellement joués sur leur lane, atteint la fin de la draft dès B2 et une profondeur ≥ 5 en premier
pick (aujourd'hui 5 et 3). Indépendant du sprint 2 : peut démarrer sans attendre la tâche 14.

**Ordre** : le bench d'abord (il fournit la base de comparaison de chaque commit suivant), puis
les trois leviers, parallélisables entre eux, du moins risqué au plus structurant. Le calibrage de
`SEARCH_TOP_N` n'a de sens qu'une fois les trois leviers en place.

| # | Tâche | Spec | Pts | Dépend de | État |
|---|---|---|---|---|---|
| 21 | `scripts/bench_search.py` : scénarios B1/B2, copie temporaire de la base, `--budget`/`--top-n`, profondeur, nœuds/s, top 3, variante principale. Relever la base de référence avant tout changement | SPEC-17 §4.4 | 2 | — | ⬜ |
| 22 | Cache des paires dans `GameEvaluator` (`matchup_logit`/`synergy_logit`, `dict` d'instance, invariant de durée de vie documenté) + tests | SPEC-17 §4.3, §4.5.4 | 2 | 21 | ⬜ |
| 23 | Générateur par popularité : `MatchupsRepository.get_lane_popularity()` + délégué `db.py`, `CandidatePool._ranked()` basculé, docstrings et commentaire `SEARCH_TOP_N` + tests | SPEC-17 §4.1, §4.5.1 | 3 | 21 | ⬜ |
| 24 | Lane des alliés : `PickTurn.lane`, renseignée par `DraftStateParser` depuis `ally_positions`, `_moves()` restreint à cette lane si libre (repli sinon) + tests | SPEC-17 §4.2, §4.5.2-3 | 3 | 21 | ⬜ |
| 25 | Calibrer `SEARCH_TOP_N` (8 / 10 / 12) au bench, retenir le plus grand qui tient §2.2, consigner la couverture de games dans le commentaire | SPEC-17 §4.1 | 1 | 22, 23, 24 | ⬜ |
| 26 | Critères d'acceptation §6 (bench B2 7/7, B1 ≥ 5, aucune variante hors top-N), `CHANGELOG.md`, statut de la spec | SPEC-17 §6 | 1 | 25 | ⬜ |

### Reporté — non planifié

| Tâche | Spec | Rouvrir quand |
|---|---|---|
| Recherche parallèle à la racine (`multiprocessing`, phase 2) | SPEC-17 §5 | Après le sprint 3, si le bench montre une profondeur < 5 en premier pick, ou si le premier pick reste mal conseillé à l'usage |
| Recherche en tâche de fond pendant le chrono de pick (« pondering ») | SPEC-17 §7 | Après le sprint 3, si la profondeur reste le facteur limitant ; chantier d'UI (sortir `rank()` de la boucle du monitor) |
| Shrink de `avg_delta2` dans la tier list (Kassadin 1er en top sur un échantillon minuscule) | SPEC-17 §7 | Spec séparée à écrire ; le même bruit que SPEC-17 §1.1, dans un autre produit |
| Spike Coachless (endpoints, authentification, granularité du WPA, CGU) | SPEC-15 §2.1 | La build des one-tricks se révèle insuffisante à l'usage |
| Moteur d'optimisation, phase A (shrinkage mesuré du WPA) | SPEC-16 §2 | Après le spike Coachless, s'il confirme un WPA par composant avec échantillons |

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
5. **GUI légère locale** (FastAPI + HTMX/React servi en localhost) — ex-Tâche #6 re-scopée,
   réutilise les algorithmes en l'état.
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
- ❌ i18n, multi-plateforme, GUI lourde
- ⏸️ Automatisation nocturne — **suspendue par choix**, mise à jour manuelle assumée

---

**Légende** : 🔴 = à traiter en priorité · 🟠 = important mais non bloquant
