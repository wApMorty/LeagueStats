# TODO — LeagueStats Coach

**Mis à jour** : 2026-09-23 (planning du lot SPEC-14 → SPEC-16 — voir §Priorités)
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

## Priorités actuelles — lot SPEC-14 → SPEC-16 (planifié le 2026-09-23)

Besoin affiné avec @pj35 le 2026-09-23 : [SPEC-14](docs/specs/SPEC-14-draft-finale-head-to-head.md),
[SPEC-15](docs/specs/SPEC-15-import-runes-items.md), [SPEC-16](docs/specs/SPEC-16-moteur-optimisation-builds.md),
décisions dans [ADR-001](docs/adr/ADR-001-source-builds-coachless.md) et
[ADR-002](docs/adr/ADR-002-moteur-optimisation-builds.md).

**Estimation** en points Fibonacci (1 ≈ une heure, 3 ≈ une demi-journée, 5 ≈ une journée, 8 ou
plus = à redécouper avant de démarrer).

### Logique de priorisation

1. **Le spike d'abord.** Il débloque toute la chaîne des builds, et c'est la seule tâche qui
   peut invalider une décision (ADR-001). Il demande @pj35, avec son compte Coachless connecté
   dans le navigateur.
2. **La collecte des photographies juste après.** C'est la seule valeur **irrattrapable** du lot :
   chaque patch non photographié est perdu pour SPEC-16 A+, qui a besoin de ~8 transitions. Elle
   passe donc **avant** l'import LCU, pourtant plus visible.
3. **SPEC-14 en quick win**, indépendante : elle peut s'intercaler à tout moment, par exemple
   pendant qu'on attend @pj35 pour le spike.
4. **L'import LCU** (valeur visible) ensuite, puis le **moteur A** qui le remplace.
5. **A+** attend l'historique : pas avant ~4 mois de collecte, sauf si le spike révèle un
   historique consultable.

### Sprint 1 — Débloquer et lancer l'horloge (~19 pts)

**Objectif** : spike conclu, collecte par patch en production, draft finale en face-à-face.

| # | Tâche | Spec | Pts | Dépend de | État |
|---|---|---|---|---|---|
| 1 | Spike Coachless : endpoints, authentification et durée de vie du jeton, granularité du WPA (par composant ? erreur-type ?), historique, CGU sur l'accès scripté | SPEC-15 §2.1 | 3 | @pj35 | ⬜ |
| 2 | Spike OneTricks : débit toléré (429), filtre par adversaire, historique ; décider OneTricks ou repli LoLalytics | SPEC-15 §2.2 | 2 | — | ⬜ |
| 3 | Consigner les résultats du spike dans SPEC-15 et **ajuster SPEC-15 et SPEC-16** (colonnes de `build_snapshots`, faisabilité de A) | SPEC-15 §2.3 | 1 | 1, 2 | ⬜ |
| 4 | Migration Alembic `build_snapshots`, testée en upgrade et en downgrade | SPEC-15 §3.6 | 2 | 3 | ⬜ |
| 5 | `src/build_snapshots.py` : collecte par source, idempotente, débit limité, et étape best-effort dans `pipeline.py` | SPEC-15 §3.6 | 5 | 4 | ⬜ |
| 6 | `[ALERTE]` dans `data_freshness.py` si le patch courant n'a aucune photographie | SPEC-15 §3.6 | 1 | 5 | ⬜ |
| 7 | `GameEvaluator.has_matchup_data()` + tests | SPEC-14 §2.2 | 1 | — | ⬜ |
| 8 | Tableau miroir ordonné par lane, colonne DUEL (flèche + valeur), seuils dans `config_constants.py`, critères §5 | SPEC-14 | 3 | 7 | ⬜ |
| 9 | Première collecte réelle lancée sur le patch courant (action manuelle, menu 3) | SPEC-15 §3.6 | 1 | 5 | ⬜ |

**Point de sortie** : si le spike Coachless échoue (tâche 1), on arrête les tâches 4 à 6 et on
rouvre ADR-001 avec LoLalytics comme repli, avant de replanifier.

### Sprint 2 — Import dans le client (~15 pts)

**Objectif** : au lock-in, les runes, les items et les sorts de la build Coachless sont dans le
client, sans jamais toucher aux pages ni aux sets du joueur.

| # | Tâche | Spec | Pts | Dépend de | État |
|---|---|---|---|---|---|
| 10 | `loadout.fetch_build()` : client Coachless, jeton en variable d'environnement, timeout, cache (champion, lane, patch) | SPEC-15 §3.1 | 3 | 3 | ⬜ |
| 11 | `loadout.apply_build()` : page de runes `LS`, set d'items préservant ceux du joueur, sorts avec Flash sur sa touche habituelle | SPEC-15 §3.3 | 5 | 10 | ⬜ |
| 12 | Déclenchement sur `completed: True` (et non sur `player_champion`), une fois par (champion, lane), relance sur trade, flag `AUTO_IMPORT_LOADOUT` | SPEC-15 §3.2 | 3 | 11 | ⬜ |
| 13 | Tests §3.5 (8 critères) | SPEC-15 §3.5 | 3 | 12 | ⬜ |
| 14 | Recette en partie réelle : vérifier les corps de requête LCU contre le client (non documentés par Riot) | SPEC-15 §3.3 | 1 | 12 | ⬜ |

### Sprint 3 — Moteur d'optimisation, phase A (~15 pts)

**Démarrable après le sprint 2, et seulement si** la tâche 3 a confirmé un WPA par composant avec
échantillons. Sinon, SPEC-16 est réorientée avant d'engager quoi que ce soit.

| # | Tâche | Spec | Pts | Dépend de | État |
|---|---|---|---|---|---|
| 15 | Mesurer le `C` du WPA (erreur-type publiée, ou régression de `mean(d²)` sur `1/n`) et les `K_wpa` et `K_diff` ; extension de `shrink.py`, K stockés dans `db_meta` | SPEC-16 §2.3 | 5 | 5, 3 | ⬜ |
| 16 | `src/analysis/build_engine.py` : candidats populaires, note `wpa_shrunk + diff_shrunk`, classement ; additivité signalée `ponytail:` | SPEC-16 §2.1-2.2 | 5 | 15 | ⬜ |
| 17 | `scripts/validate_build_engine.py` : stabilité sur les témoins et cohérence de signe | SPEC-16 §2.4 | 3 | 16 | ⬜ |
| 18 | Brancher `loadout` sur le moteur à la place de la build Coachless brute | SPEC-16 §5 | 2 | 16, 12 | ⬜ |

### Plus tard — Phase A+ (🔵 bloquée)

**Débloquée à** ~8 transitions de patch dans `build_snapshots`, soit environ 4 mois après la
tâche 9 (horizon indicatif : début 2027), sauf si le spike révèle un historique consultable.

| # | Tâche | Spec | Pts | État |
|---|---|---|---|---|
| 19 | `src/analysis/patch_diff.py` : diff Data Dragon (items, runes, champions), classement modifié ou inchangé | SPEC-16 §3.1 | 3 | 🔵 |
| 20 | Les trois mesures (bruit des témoins, différence de différences, biais de sélection) et la repondération des sources : **à redécouper** au déblocage | SPEC-16 §3.2 | 13 | 🔵 |

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
