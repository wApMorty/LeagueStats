# Structure du Projet — LeagueStats Coach

**Dernière mise à jour** : 2026-09-04 (réécrit, la version précédente décrivait une
arborescence pré-refactor et des scripts de build qui n'existent plus).

## Racine

```
LeagueStats/
├── lol_coach.py           # Point d'entrée principal (menu unifié) — pas de main.py
├── build_app.py            # Build de l'exécutable (PyInstaller)
├── create_package.py       # Empaquetage de la distribution (ZIP)
├── alembic.ini              # Config Alembic
├── pyproject.toml           # Config black/pylint/mypy/pytest/coverage/bandit
├── requirements.txt, requirements-dev.txt
├── CLAUDE.md, README.md, CHANGELOG.md, TODO.md
└── LeagueStatsCoach.spec    # Config PyInstaller
```

## `src/` — Code applicatif

```
src/
├── assistant.py             # Coordinateur : délègue à analysis/*, draft/scoring.py
├── db.py                    # Couche base de données SQLite (requêtes paramétrées)
├── db_backup.py             # Sauvegarde/restauration avant les étapes destructives du pipeline
├── pipeline.py               # Orchestrateur unique : scrape → contrôle complétude → recalcul → notif
├── draft_monitor.py          # Façade du Live Coach (intégration LCU), délègue à draft/
├── lcu_client.py              # Client API League Client Update (127.0.0.1:2999)
├── parser.py, parallel_parser.py, multilane.py, lane_discovery.py  # Scraping LoLalytics
├── cloudflare_detector.py     # Détection de challenge Cloudflare (conservé, plus déclenché)
├── data_freshness.py          # Fraîcheur des données (db_meta)
├── data_quality.py            # Contrôle de complétude post-scrape
├── notifications.py            # Notifications Discord/toast Windows
├── pool_manager.py             # Pools de champions (système + personnalisées)
├── role_inference.py            # Inférence des rôles des 10 joueurs (SPEC-04 B4)
├── user_prefs.py                 # Préférences persistées du draft coach
├── models.py, config.py, config_constants.py, constants.py
│
├── analysis/                # Algorithmes d'analyse et de scoring
│   ├── scoring.py            # ChampionScorer : score_against_team, modèle log-odds
│   ├── aggregation.py         # Agrégation multi-lane centralisée
│   ├── tier_list.py            # Génération de tier lists S/A/B/C, lane-scoped
│   ├── champion_scores.py       # GlobalScoreCalculator (table champion_scores)
│   ├── ban_recommendations.py    # BanRecommender (menaces de ban, par pool)
│   ├── recommendations.py         # RecommendationEngine (Tournament Coach)
│   ├── matchup_cache.py            # Cache mémoire pour les lookups en draft
│   ├── probability.py               # logit/sigmoid (modèle log-odds, SPEC-05 B7)
│   ├── pool_statistics.py            # Statistiques de pool
│   ├── team_analysis.py               # TeamAnalyzer (code non appelé par un menu)
│   └── trio_holistic.py, trio_counterpick.py, trio_metrics.py,
│       trio_tactics.py, trio_weights.py  # Team Builder (menu 5)
│
├── draft/                   # Logique du Live Coach (extrait de draft_monitor.py, SPEC-07 E10)
│   ├── state.py, state_parser.py     # DraftState, parsing des snapshots LCU
│   ├── scoring.py                     # DraftScorer (blend matchup + synergie)
│   ├── recommendations.py              # Recommandations de pick en direct
│   ├── final_analysis.py                # Écran de fin de draft
│   ├── ban_advice.py                     # 3 écrans de bans (auto-hover, draft, adaptatif)
│   ├── pool_selection.py                  # Sélection de la pool de la session
│   ├── lifecycle.py, phases.py, commands.py, onetricks.py,
│       automation.py, display.py, memory_diagnostics.py
│
├── ui/                       # Un module par menu/domaine
│   ├── menu_system.py          # Boucle de menu principale
│   ├── draft_coach_ui.py        # Menu 1 (Live Coach)
│   ├── data_update_ui.py         # Menu 3 (mise à jour des données → src/pipeline.py)
│   ├── champion_data_ui.py        # Recalcul manuel des scores
│   ├── tournament_coach_ui.py,
│       tournament_display_ui.py    # Menu 4 (coach de tournoi manuel)
│   ├── team_builder_ui.py           # Menu 5 (constructeur d'équipe)
│   ├── pools_menu_ui.py, pools_crud_ui.py, pool_selection_ui.py  # Menu 6 (gestion des pools)
│   ├── tier_list_ui.py               # Génération/affichage de tier list
│   └── checks.py                      # Vérifications au démarrage
│
└── utils/
    ├── champion_utils.py       # Validation de pool/champion (validate_champion_data/pool)
    ├── console.py, display.py   # Sorties console (safe_print, ASCII)
```

## `scripts/` — Outils en ligne de commande

```
scripts/
├── update_all.py            # Pipeline de référence (voir README.md)
├── auto_update_db.py          # Ancien orchestrateur, superseded par update_all.py — pas utilisé
├── repair_data.py               # Réparation ciblée de données incomplètes
├── calibrate_model.py            # Calibration des coefficients du modèle log-odds (SPEC-05 B7)
├── setup_auto_update.ps1, test_auto_update.py  # Config Task Scheduler (automatisation suspendue par choix)
├── rotate_logs.ps1, setup_log_rotation.ps1       # Rotation de logs/update_all.log
└── cleanup_claude_temp.py         # Nettoyage de fichiers temporaires Claude Code
```

## `alembic/versions/` — Migrations de schéma

Voir `docs/alembic_guide.md`. Les tables dérivées/cache (`champion_scores`,
`pool_ban_recommendations`) sont entièrement recalculées par le pipeline plutôt
que migrées en place : leurs migrations font un `DROP` + `CREATE` (mêmes
principe qu'un recalcul de cache).

## `data/`, `logs/`, `tests/`, `docs/`

```
data/db.db                  # Base SQLite (173 champions, ~25 000 matchups/rôle)
logs/update_all.log          # Log actif du pipeline (voir aussi runbook_scraping.md)
tests/                        # Suite pytest (couverture sur tout src/, seuil 45 %)
tests/regression/              # Tests de régression par bug corrigé
docs/specs/                     # Spécifications d'implémentation par chantier
docs/archive/                    # Documents de travail entièrement exécutés
```

## Artefacts de build (générés, non trackés par git sauf indication contraire)

```
LeagueStatsCoach_Release/    # Dossier de release (db.db, exe, docs) — build_app.py/create_package.py
build/, dist/                 # Sorties PyInstaller intermédiaires
htmlcov/, .pytest_cache/, coverage.xml, .benchmarks/
```

## Utilisation

### Développement
```bash
python lol_coach.py                    # Lancer l'application
pytest tests/ -v                        # Lancer la suite de tests
```

### Mise à jour des données
```bash
python scripts/update_all.py           # ~45 min, pipeline complet
```

### Build & Distribution
```bash
python build_app.py                    # Créer l'exécutable
python create_package.py               # Créer le ZIP de distribution
```

## Fonctionnalités principales

1. **Draft Coach en temps réel** — recommandations pick/ban pendant le champion select (LCU), lane-aware pour les 10 joueurs (rôles inférés, SPEC-04)
2. **Team Builder** — trios/duos optimaux (blind pick + counterpick, ou évaluation holistique)
3. **Coach de tournoi** — même logique de coaching, saisie manuelle hors client League
4. **Pipeline de données** — scrape multi-lane, contrôle de complétude gradué, sauvegarde avant réécriture
5. **Pools de champions** — pools système (dérivées des lanes en base) et personnalisées

## Distribution

`build_app.py` puis `create_package.py` génèrent un exécutable Windows portable
(aucun Python requis sur le PC cible), publié dans `LeagueStatsCoach_Release/`.

**Prérequis sur le PC de destination** :
- Windows 10/11
- League of Legends installé (pour le Draft Coach en temps réel)
- Firefox installé (pour les mises à jour de données)
