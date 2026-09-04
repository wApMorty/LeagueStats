# TODO — LeagueStats Coach

**Mis à jour** : 2026-09-04
**Source** : audit de suivi du 2026-09-04 (vérification sur pièces post-SPEC-01→07), non publié comme
document séparé — synthèse directement intégrée ici. Historique complet : `docs/archive/`
(`AUDIT_2026_06.md`, `AUDIT_2026_08.md`, `BACKLOG_2026_08.md`, `specs/SPEC-01` à `SPEC-07`).

> **Le backlog SPEC-01 à SPEC-07 (coché soldé le 2026-09-01) avait un angle mort** : les items
> B2 ("lecture filtrée par lane") et D3 ("langue unifiée") étaient cochés faits alors que 4 zones
> du produit blendaient encore toutes les lanes (Live Coach fin de draft, bans, Team Builder,
> Tournament Coach) — corrigé le 2026-09-04, avec la CI (cassée par la migration lane du jour même)
> et l'hygiène du dépôt. Détail dans `CHANGELOG.md [Unreleased]`.

---

## Priorités actuelles

| Rang | Chantier | Pourquoi maintenant |
|---|---|---|
| 1 | **Dette de code — fichiers >500 lignes** | Règle critique `CLAUDE.md` violée sur 6 fichiers ; aucune urgence fonctionnelle mais ralentit tout le reste |
| 2 | **Couverture des modules trio_*/ban_recommendations** | Ne sont testés que par des tests de caractérisation qui figent le comportement actuel — n'auraient pas détecté le bug lane de septembre |
| — | Features candidates | À piocher par appétit, aucune n'est bloquante |

---

## 1. Dette de code — fichiers >500 lignes 🔴

Refactor lourd façon E9/E10 (démantèlement `lol_coach_legacy.py`/`assistant.py` en 2026-09) : extraire
par domaine, tests de caractérisation avant tout déplacement de code.

| Fichier | Lignes | Note |
|---|---|---|
| `src/db.py` | 1698 | Le plus gros — déjà lane-aware partout, découpage par domaine de table (matchups/synergies/champion_scores/pools/predictions) |
| `src/parallel_parser.py` | 974 | Scraping parallèle |
| `scripts/repair_data.py` | 650 | Réparation ciblée |
| `src/constants.py` | 593 | Essentiellement des listes de champions par rôle — vérifier si un découpage a de la valeur ou si c'est un faux positif de la règle |
| `src/assistant.py` | 527 | Juste au-dessus, déjà largement une façade mince après SPEC-07 E10 |
| `src/parser.py` | 522 | Parsing des pages LoLalytics |

## 2. Couverture — modules trio_*/ban_recommendations 🟠

`trio_holistic.py`, `trio_counterpick.py`, `trio_metrics.py`, `trio_weights.py`, `matchup_cache.py`,
`champion_scores.py`, `ban_recommendations.py` ne sont exercés qu'indirectement via `Assistant`, par
des tests de caractérisation qui pinnent le comportement actuel plutôt que de le spécifier — ils
n'auraient pas empêché le bug lane de septembre. Des tests directs sur ces modules (voir
`tests/test_trio_lane_aware.py`, `tests/test_ban_recommendations.py` pour un point de départ)
combleraient l'angle mort.

---

## Features candidates

*Sources : `docs/ROADMAP_2026.md` Horizon 3, `docs/TOURNAMENT_COACH_IMPROVEMENTS.md` (section
"Future Enhancements"), constats du 2026-09-04. Aucune n'est engagée — à trier par appétit.*

1. **UX de confiance** — afficher systématiquement la fraîcheur des données et le nombre de games
   derrière chaque recommandation (l'infra existe déjà : `db_meta`, `confidence(games)`).
2. **Calibration du modèle log-odds** — l'infra de journalisation existe déjà
   (`Database.insert_prediction`/`update_prediction_outcome`, appelée en fin de draft et via la
   commande `outcome win|loss`). `scripts/calibrate_model.py` existe déjà comme point de départ —
   reste à l'exécuter/l'affiner une fois assez de parties en base.
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
