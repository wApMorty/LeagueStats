# TODO — LeagueStats Coach

**Mis à jour** : 2026-09-06 (SPEC-08 et SPEC-09 mergées ; reste SPEC-10 — voir §Priorités)
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

## Priorités actuelles — lot SPEC-08 → SPEC-10

**Validées par @pj35 le 2026-09-05.** Specs autoportantes dans [`docs/specs/`](docs/specs/README.md).

| Rang | Chantier | Spec | État |
|---|---|---|---|
| 1 | **Fermer la boucle de mesure** (résultat de partie automatique via LCU) | [SPEC-08](docs/specs/SPEC-08-boucle-de-mesure.md) | ✅ **Mergée le 2026-09-06** |
| 2 | **Rendre l'ignorance visible** (champions écartés affichés, seuil de lane 10 % → 5 %) | [SPEC-09](docs/specs/SPEC-09-ignorance-visible.md) | ✅ **Mergée le 2026-09-06** |
| 3 | **Couverture du chemin critique temps réel** | [SPEC-10](docs/specs/SPEC-10-couverture-chemin-critique.md) | 🔴 **À faire** — `pool_selection_ui.py` à 2,6 % et `lcu_client.py` à 18,6 %, le chemin exact des bugs lane de septembre |
| 4 | **Calibration du modèle** | — | ⏳ **Débloquée par SPEC-08, en attente de données** : lancer `python scripts/calibrate_model.py` une fois ~30 parties labellisées (le compteur `[OUTCOME]` affiche la progression à chaque résolution). Tout ajustement de `K_MATCHUP`/`K_SYNERGY`/`SAME_LANE_WEIGHT` exige un bump de `MODEL_VERSION` |
| — | Features candidates | — | À rouvrir après la calibration, aucune n'est bloquante |

### Actions manuelles restantes après le merge du 2026-09-06

- [ ] Appliquer la migration : `python -m alembic upgrade head` (ajoute `predictions.game_id`)
- [ ] Relancer un scrape complet au nouveau seuil de lane : `python scripts/update_all.py`
      (~55 min désormais, ~343 combos (champion, lane) attendus contre 283)
- [ ] Après ce scrape, envisager de relever `MIN_TOTAL_MATCHUPS` (`src/data_quality.py`, laissé à
      20 000 : plancher toujours valide mais désormais large sous un volume attendu de ~30 k)

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
3. **Intégration sites de draft externes** (DraftLol, etc.) — recherche disponible dans
   `docs/archive/DRAFT_SITES_INTEGRATION_RESEARCH.md` (restaurée le 2026-09-04, contenu d'octobre
   2025 à revalider). Dépend du reverse-engineering du WebSocket DraftLol — spike de 1-2 jours
   avant d'engager.
4. **GUI légère locale** (FastAPI + HTMX/React servi en localhost) — ex-Tâche #6 re-scopée,
   réutilise les algorithmes en l'état.
5. **Depuis `docs/TOURNAMENT_COACH_IMPROVEMENTS.md`** : chargement de draft depuis JSON,
   comparaison multi-drafts, templates de composition, simulation IA vs IA, base de drafts
   historiques, timer pick/ban, tracking explicite de phase ban/pick.
6. **Décision produit** : réactiver `TeamAnalyzer` (`src/analysis/team_analysis.py`, code testé
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
