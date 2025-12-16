# 🤖 CLAUDE.md - Instructions pour Assistant IA

**Projet**: LeagueStats Coach
**Version**: 1.0.2
**Mainteneur**: @pj35
**Dernière mise à jour**: 2025-11-27

---

## 📋 Table des Matières

1. [Contexte du Projet](#contexte-du-projet)
2. [Workflow de Développement](#workflow-de-développement)
3. [Standards de Code](#standards-de-code)
4. [Conventions Git](#conventions-git)
5. [Process de Code Review](#process-de-code-review)
6. [Approche Dette Technique First](#approche-dette-technique-first)
7. [Fichiers Importants](#fichiers-importants)
8. [Commandes Utiles](#commandes-utiles)

---

## 🎯 Contexte du Projet

### Vue d'Ensemble

LeagueStats Coach est un outil d'analyse et de coaching pour League of Legends qui aide les joueurs à optimiser leurs choix de champions en draft. Le projet analyse 171 champions et 36,000+ matchups pour générer des tier lists et recommandations.

**Stack Technique**:
- **Langage**: Python 3.13+
- **Base de données**: SQLite (data/db.db)
- **Migrations BD**: Alembic 1.13+
- **Web Scraping**: Selenium + Firefox
- **Distribution**: PyInstaller (standalone .exe)
- **Tests**: pytest + pytest-cov + pytest-mock

### État Actuel (Version 1.0.2)

**✅ Complété**:
- SQL injection fixes (v1.0.1)
- Database indexes pour performance (v1.0.1)
- Extraction valeurs hardcodées → config_constants.py (v1.0.2)
- Bug #2 fix: SyntaxWarning parser.py (v1.0.2)

**🔴 Prochaine Tâche**: Tâche #1 - Refactoring fichiers monolithiques (Sprint 1)

### Philosophie: Dette Technique First

**Principe**: Résoudre la dette technique AVANT d'ajouter des features pour :
- ✅ Éviter refactoring complexe plus tard
- ✅ Faciliter TOUTES les futures tâches
- ✅ Base saine = vélocité élevée

**Ordre Sprint**:
1. ✅ Sprint 0: Configuration (Tâche #2 - FAIT)
2. 🔴 Sprint 1: Dette Technique (Refactoring + Tests + Migrations)
3. 🟡 Sprint 2: Performance & Features
4. 🟢 Sprint 3+: Features Avancées

---

## 🔀 Workflow de Développement

### 1. Avant de Commencer une Tâche

```bash
# 1. Vérifier l'état du worktree
git status

# 2. Créer une feature branch depuis la branche actuelle
git checkout -b feature/task-name

# Exemples:
# git checkout -b feature/refactor-monolithic-files
# git checkout -b feature/database-migrations
# git checkout -b feature/parallel-scraping
```

### 2. Pendant le Développement

**Commits fréquents et atomiques**:
- ✅ Commit après chaque modification logique cohérente
- ✅ Messages de commit descriptifs et explicites
- ✅ Ne jamais regrouper plusieurs changements non liés

**Exemple de workflow**:
```bash
# Étape 1: Modifier fichier A
# Commit A
git add src/file_a.py
git commit -m "Refactor: Extract UI logic to ui/menu_system.py"

# Étape 2: Modifier fichier B
# Commit B
git add src/file_b.py
git commit -m "Refactor: Extract scoring algorithms to analysis/scoring.py"

# Étape 3: Tests
# Commit C
git add tests/test_scoring.py
git commit -m "Test: Add unit tests for scoring algorithms"
```

### 3. Code Review Process

**IMPORTANT**: Toujours demander validation avant de merge

**Étapes**:
1. ✅ Terminer la tâche sur feature branch
2. ✅ S'assurer que tous les tests passent
3. ✅ Créer un résumé des changements pour l'utilisateur
4. ✅ **ATTENDRE VALIDATION** de l'utilisateur
5. ✅ Merger uniquement après approbation

**Template de Code Review**:
```markdown
## 📋 Code Review - [Nom de la Tâche]

### Résumé
[Description courte de ce qui a été fait]

### Fichiers Modifiés
- `src/file1.py` - [Description changements]
- `src/file2.py` - [Description changements]

### Fichiers Créés
- `src/new_file.py` - [Description]

### Tests
- [x] Tous les tests existants passent
- [x] Nouveaux tests ajoutés
- [x] Couverture: X%

### Commits
1. [hash] - Description commit 1
2. [hash] - Description commit 2

### Points d'Attention
- [Points spécifiques à valider]

### Prêt pour Merge?
❌ **EN ATTENTE DE VALIDATION UTILISATEUR**
```

### 4. Après Validation

```bash
# Une fois validation reçue de l'utilisateur:
git checkout inspiring-rhodes  # Retour branche principale
git merge --no-ff feature/task-name  # Merge avec commit de merge
git branch -d feature/task-name  # Supprimer feature branch
```

---

## 📝 Standards de Code

### Style Python

**Général**:
- PEP 8 compliance
- Type hints sur toutes les fonctions publiques
- Docstrings pour classes et méthodes publiques
- Maximum 500 lignes par fichier (objectif Dette Technique First)

**Imports**:
```python
# Standard library
import os
import sys
from typing import List, Optional

# Third-party
import sqlite3
from selenium import webdriver

# Local imports
from .config import config
from .config_constants import analysis_config
```

### Configuration

**IMPORTANT**: Toujours utiliser `config_constants.py` pour les valeurs hardcodées

```python
# ❌ MAUVAIS - Hardcodé
if games >= 100:
    ...

# ✅ BON - Config centralisée
from .config_constants import analysis_config
if games >= analysis_config.MIN_GAMES_THRESHOLD:
    ...
```

### Sécurité

**CRITIQUE**: Toujours utiliser des requêtes paramétrées

```python
# ❌ MAUVAIS - SQL Injection
cursor.execute(f"SELECT * FROM champions WHERE name = '{name}'")

# ✅ BON - Requête paramétrée
cursor.execute("SELECT * FROM champions WHERE name = ?", (name,))
```

### Tests

**Framework**: pytest + pytest-cov + pytest-mock (Sprint 1 ✅)
**Couverture**: **89% du module analysis (objectif 70%+ largement dépassé)

**Structure**:
```
tests/
├── __init__.py
├── conftest.py              # Fixtures partagées (DB, scorer, insert_matchup)
├── test_scoring.py          # 27 tests - 95% coverage
├── test_tier_list.py        # 18 tests - 100% coverage
└── test_team_analysis.py    # 13 tests - 97% coverage
```

**Commandes**:
```bash
# Lancer tous les tests
pytest tests/ -v

# Tests avec couverture
pytest tests/ --cov=src --cov-report=term
pytest tests/ --cov=src --cov-report=html  # Rapport HTML

# Tests d'un module spécifique
pytest tests/test_scoring.py -v
```

**Fixtures disponibles** (tests/conftest.py):
- `temp_db`: Base de données SQLite temporaire
- `db`: Instance Database connectée
- `scorer`: Instance ChampionScorer
- `insert_matchup`: Helper pour insérer matchups facilement
- `sample_matchups`: Données de matchups d'exemple
- `sample_champions`: Liste de champions d'exemple

**Exemple de test**:
```python
import pytest
from src.analysis.scoring import ChampionScorer

def test_weighted_average_calculation(scorer, insert_matchup):
    """Test calcul moyenne pondérée par pickrate."""
    # Arrange - Setup test data
    insert_matchup('Champ1', 'Enemy1', 50.0, 100.0, 0, 10.0, 1000)
    insert_matchup('Champ1', 'Enemy2', 50.0, 200.0, 0, 20.0, 1000)

    # Expected: (100*10 + 200*20) / (10+20) = 166.67
    matchups = [...]  # Retrieve matchups

    # Act
    result = scorer.avg_delta1(matchups)

    # Assert
    assert abs(result - 166.67) < 0.01
```

**Couverture par module**:
- `src/analysis/scoring.py`: **95%** (82 statements, 4 missed)
- `src/analysis/tier_list.py`: **100%** (45 statements, 0 missed)
- `src/analysis/team_analysis.py`: **97%** (69 statements, 2 missed)
- `src/analysis/recommendations.py`: **65%** (60 statements, 21 missed - draft_simple legacy)

**Documentation**: [tests/README.md](tests/README.md) (à créer si besoin)

---

## 🔀 Conventions Git

### Branches

**Format**: `feature/descriptive-name` ou `fix/bug-description`

**Exemples**:
- `feature/refactor-monolithic-files`
- `feature/database-migrations`
- `feature/parallel-scraping`
- `fix/sql-injection-vulnerabilities`
- `fix/cookie-click-coordinates`

### Commits avec Gitmoji

**Format**: `<gitmoji> Type: Description courte`

**Types et Gitmojis**:
- ✨ `Feature:` - Nouvelle fonctionnalité
- ♻️ `Refactor:` - Refactoring sans changement de comportement
- 🐛 `Fix:` - Correction de bug
- ✅ `Test:` - Ajout/modification de tests
- 📝 `Docs:` - Documentation
- ⚡ `Perf:` - Amélioration performance
- 🔧 `Chore:` - Maintenance (deps, config, etc.)
- 🔒 `Security:` - Corrections sécurité
- 🎨 `Style:` - Formatage, style code
- 🚀 `Deploy:` - Déploiement, build
- 🗃️ `Database:` - Migrations, schéma BD

**Exemples**:
```bash
git commit -m "♻️ Refactor: Extract UI logic to src/ui/ modules"
git commit -m "✨ Feature: Add database migrations with Alembic"
git commit -m "🐛 Fix: SQL injection in get_champion_id()"
git commit -m "✅ Test: Add unit tests for scoring algorithms (70% coverage)"
git commit -m "⚡ Perf: Add database indexes for 50-80% speedup"
git commit -m "📝 Docs: Update TODO.md with Dette Technique First approach"
git commit -m "🔒 Security: Parameterize all SQL queries"
git commit -m "🗃️ Database: Add Alembic migration for role column"
```

**Référence Gitmoji**: [gitmoji.dev](https://gitmoji.dev)

### Messages de Commit Détaillés

Pour les commits complexes, utiliser description étendue:

```bash
git commit -m "♻️ Refactor: Decompose assistant.py into analysis/ modules

- Extract scoring algorithms to analysis/scoring.py
- Extract tier list generation to analysis/tierlist.py
- Extract optimizer to analysis/optimizer.py
- Update imports in lol_coach.py and tests
- All tests pass (pytest -v)

Addresses: Tâche #1 (Refactoring fichiers monolithiques)
Impact: assistant.py reduced from 2,381 → 450 lines
"
```

---

## ✅ Process de Code Review (Pull Request GitHub)

### Workflow Pull Request

**IMPORTANT**: Utiliser les Pull Requests GitHub pour toutes les code reviews

**Étapes**:
1. ✅ Créer feature branch et développer
2. ✅ Push feature branch vers GitHub
3. ✅ Créer Pull Request via `gh pr create`
4. ✅ **ATTENDRE VALIDATION** de l'utilisateur sur GitHub
5. ✅ Merger via GitHub après approbation
6. ✅ Pull des changements en local

**Commandes**:
```bash
# 1. Push feature branch
git push -u origin feature/task-name

# 2. Créer Pull Request avec gh CLI
gh pr create --title "🎯 Tâche #X: Titre de la tâche" \
             --body-file .github/PR_TEMPLATE.md \
             --assignee @pj35 \
             --label "enhancement"

# 3. Après validation GitHub
gh pr merge --squash  # Préférence: squash (combine tous commits en 1)

# 4. Pull changes
git checkout inspiring-rhodes
git pull origin inspiring-rhodes
git branch -d feature/task-name
```

### Template de Pull Request

Utiliser ce template dans la description PR:

```markdown
## 📊 Résumé

**Tâche**: #X - [Nom complet de la tâche]
**Branche**: `feature/task-name`
**Durée estimée**: X jours
**Commits**: X commits
**Gitmoji**: [Emoji principal de la PR]

## 📝 Changements

### Fichiers Modifiés (X)
1. `src/file1.py` (X lignes modifiées)
   - [Description changement 1]
   - [Description changement 2]
2. `src/file2.py` (X lignes modifiées)
   - [Description]

### Fichiers Créés (X)
1. `src/new_file1.py` (X lignes)
   - [Description rôle]
2. `src/new_file2.py` (X lignes)
   - [Description rôle]

### Fichiers Supprimés (X)
1. `old_file.py` - [Raison suppression]

## 🧪 Tests

- [x] Compilation Python: ✅ Tous fichiers compilent
- [x] Imports fonctionnels: ✅ Pas d'erreur import
- [x] Tests unitaires: ✅ XX/XX tests passent
- [x] Tests manuels: ✅ [Scénarios testés]

**Couverture**: XX% (objectif: 70%+)

## 📦 Commits

```
1. [hash] - 🎨 Type: Description commit 1
2. [hash] - ♻️ Type: Description commit 2
3. [hash] - ✅ Type: Description commit 3
```

*(Liste complète visible dans l'onglet "Commits" de la PR)*

## ⚠️ Points d'Attention

1. [Point spécifique nécessitant validation]
2. [Choix architectural à confirmer]
3. [Breaking changes éventuels]

## 📊 Métriques

| Métrique | Avant | Après | Amélioration |
|----------|-------|-------|--------------|
| Largest File | 2,381 lignes | XXX lignes | -XX% |
| Test Coverage | X% | XX% | +XX% |
| [Autre métrique] | X | XX | +XX% |

## 🚀 Prochaines Étapes

Après validation et merge de cette PR:
1. ✅ Mettre à jour TODO.md (marquer tâche ✅)
2. ✅ Mettre à jour CHANGELOG.md si nécessaire
3. ✅ Pull changes en local
4. ✅ Commencer Tâche #Y (si applicable)

## ❓ Questions

[Questions éventuelles pour review]

---

**Checklist Review**:
- [ ] Code compilable
- [ ] Tests passent
- [ ] Documentation à jour
- [ ] Pas de valeurs hardcodées
- [ ] Requêtes SQL paramétrées
- [ ] Backward compatibility

---

📋 **Merci de review cette PR sur GitHub et d'approuver/commenter directement sur l'interface !**
```

### Validation GitHub

**Process de validation**:
1. ✅ Review code sur GitHub (interface web)
2. ✅ Commenter les lignes spécifiques si besoin
3. ✅ Approuver la PR via "Approve" ou demander changements
4. ✅ Merger via interface GitHub ou `gh pr merge`

**L'assistant NE mergera JAMAIS sans**:
- ✅ Approbation explicite sur GitHub ("Approved")
- ✅ Aucun "Request changes" en attente
- ✅ Validation utilisateur claire

---

## 🔴 Approche Dette Technique First

### Principe

**Résoudre dette technique AVANT features** = Vélocité élevée ensuite

### Sprint 1 - Dette Technique (PRESQUE TERMINÉ ✅)

**Objectif**: Fondations solides

**Tâches**:
1. ✅ **Tâche #1**: Refactoring fichiers monolithiques (COMPLÉTÉ)
   - `lol_coach.py` (2,160 lignes) → `src/ui/` modules
   - `assistant.py` (2,381 lignes) → `src/analysis/` modules
   - Résultat: <500 lignes/fichier atteint

2. ✅ **Tâche #3**: Framework Tests Automatisés (COMPLÉTÉ)
   - Setup pytest + pytest-cov + pytest-mock
   - Tests scoring algorithms (74 tests)
   - Résultat: **89% couverture** (objectif 70%+ largement dépassé)

3. 🔴 **Tâche #9**: Migrations Base de Données (EN COURS)
   - ✅ Setup Alembic 1.13+
   - ✅ Migration initiale (schema complet)
   - ✅ Tests up/down validés
   - ⏳ Documentation mise à jour
   - ⏳ Code review à finaliser

**Impact**: Code maintenable + tests auto (89%) + migrations = Base saine pour TOUS futurs développements ✅

### Métriques Cibles Sprint 1

| Métrique | Avant | Après Sprint 1 | Statut |
|----------|-------|----------------|--------|
| Largest File | 2,381 lignes | **<500 lignes** | ✅ Atteint |
| Test Coverage | ~5% | **89%** (analysis module) | ✅ Dépassé (objectif: 70%) |
| Migrations BD | Non | **Alembic 1.13+** configuré | ✅ Opérationnel |
| Hardcoded Values | ~20 | **0** (config_constants.py) | ✅ Complété |

---

## 📂 Fichiers Importants

### Documentation

- `CLAUDE.md` - **CE FICHIER** - Instructions pour assistant IA
- `TODO.md` - Backlog Agile avec scores Fibonacci
- `AUDIT_REPORT.md` - Audit qualité code (note A- 18/20)
- `CHANGELOG.md` - Historique versions
- `SECURITY_FIXES.md` - Détails corrections sécurité v1.0.1
- `README.md` - Documentation utilisateur

### Configuration

- `src/config.py` - Configuration principale + backward compatibility
- `src/config_constants.py` - **NOUVEAU** - Constantes centralisées (v1.0.2)
  - `ScrapingConfig` - Web scraping
  - `AnalysisConfig` - Analyse et tier lists
  - `DraftConfig` - Draft monitoring
  - `UIConfig` - Interface utilisateur
  - `XPathConfig` - XPath selectors

### Code Principal

- `src/assistant.py` - **2,381 lignes** 🔴 - Algorithmes scoring (À REFACTORER)
- `src/lol_coach.py` - **2,160 lignes** 🔴 - UI CLI (À REFACTORER)
- `src/db.py` - Database layer (sécurisé v1.0.1)
- `src/parser.py` - Web scraping LoLalytics
- `src/draft_monitor.py` - Real-time draft coach
- `src/pool_manager.py` - Champion pools CRUD
- `src/lcu_client.py` - League Client API

### Tests

- `test_db_fixes.py` - Tests sécurité + indexes (v1.0.1)
- `tests/` - **À CRÉER** - Framework pytest (Sprint 1)

### Build

- `build_app.py` - PyInstaller build script
- `create_package.py` - Package portable
- `requirements.txt` - Production dependencies
- `requirements-dev.txt` - Development dependencies

---

## 🛠️ Commandes Utiles

### Development

```bash
# Installation dépendances
pip install -r requirements.txt          # Production
pip install -r requirements-dev.txt      # Development + PyInstaller

# Tests
python test_db_fixes.py                  # Tests v1.0.1 (SQL injection + indexes)
pytest tests/ -v                         # Tous tests (après Sprint 1)
pytest tests/ --cov=src --cov-report=html  # Avec couverture

# Compilation check
python -m py_compile src/*.py            # Vérifier syntaxe Python

# Linting (à configurer Sprint 1)
pylint src/ --fail-under=8.0
black src/ --check
mypy src/
```

### Git Workflow

```bash
# Créer feature branch
git checkout -b feature/task-name

# Commits fréquents
git add src/file.py
git commit -m "Type: Description"

# Vérifier statut
git status
git log --oneline -5

# Code Review (après validation)
git checkout inspiring-rhodes
git merge --no-ff feature/task-name
git branch -d feature/task-name
```

### Build & Distribution

```bash
# Build executable
python build_app.py                      # Créer LeagueStatsCoach.exe

# Package portable
python create_package.py                 # Créer .zip distribution

# Database maintenance
python cleanup_db.py                     # Backup et nettoyage
```

### Database Migrations (Alembic)

```bash
# Check current migration version
python -m alembic current

# View migration history
python -m alembic history

# Upgrade to latest version (head)
python -m alembic upgrade head

# Downgrade to previous version
python -m alembic downgrade -1

# Downgrade to specific version
python -m alembic downgrade <revision_id>

# Downgrade to base (empty database)
python -m alembic downgrade base

# Create new migration (manual)
python -m alembic revision -m "Description of changes"

# Create new migration with autogenerate (requires SQLAlchemy models)
python -m alembic revision --autogenerate -m "Description"

# Show SQL without executing (dry-run)
python -m alembic upgrade head --sql
```

**Important Notes**:
- ✅ Always backup database before running migrations in production
- ✅ Test migrations locally before deploying
- ✅ Database path configured in `alembic.ini`: `sqlite:///data/db.db`
- ✅ Schema defined in `alembic/env.py` for migration tracking
- ✅ Migration files stored in `alembic/versions/`
- ⚠️ Downgrading may result in data loss - use with caution

**Migration Workflow**:
1. Create migration: `alembic revision -m "Add new column"`
2. Edit migration file in `alembic/versions/` (implement upgrade/downgrade)
3. Test locally: `alembic upgrade head` then `alembic downgrade -1`
4. Commit migration file with code changes
5. Deploy: Run `alembic upgrade head` in production

---

## 🚨 Règles Critiques

### TOUJOURS

1. ✅ **Feature branch** pour chaque tâche
2. ✅ **Commits atomiques** et fréquents
3. ✅ **Code review** AVANT tout merge
4. ✅ **Validation utilisateur** explicite requise
5. ✅ **Tests** avant de demander validation
6. ✅ **Requêtes SQL paramétrées** (sécurité)
7. ✅ **config_constants.py** pour valeurs hardcodées
8. ✅ **Type hints** sur fonctions publiques
9. ✅ **Docstrings** sur classes et méthodes
10. ✅ **Backward compatibility** lors refactoring

### JAMAIS

1. ❌ Merger sans validation utilisateur
2. ❌ Commits directs sur branche principale
3. ❌ Valeurs hardcodées dans le code
4. ❌ Interpolation string dans SQL (`f"SELECT * FROM {table}"`)
5. ❌ Fichiers >500 lignes (après Sprint 1)
6. ❌ Code non testé en production
7. ❌ Breaking changes sans migration
8. ❌ Commits groupant changements non liés
9. ❌ Supprimer code sans tests de régression
10. ❌ Features AVANT dette technique (Sprint 1)

---

## 📋 Checklist Avant Code Review

Avant de soumettre code review, vérifier:

- [ ] Feature branch créée et nommée correctement
- [ ] Tous les fichiers modifiés sont committed
- [ ] Messages de commit suivent conventions (Type: Description)
- [ ] Compilation Python réussie (`python -m py_compile`)
- [ ] Imports fonctionnels (tests manuels)
- [ ] Tests unitaires passent (si applicable)
- [ ] Pas de valeurs hardcodées (utilise config_constants.py)
- [ ] Pas de SQL injection (requêtes paramétrées)
- [ ] Backward compatibility maintenue
- [ ] Documentation mise à jour (README, TODO, etc.)
- [ ] Code review template rempli complètement

---

## 🎯 Objectifs Long Terme

### Sprint 1 (Dette Technique) - EN COURS
- [ ] Tâche #1: Refactoring (<500 lignes/fichier)
- [ ] Tâche #9: Database migrations (Alembic)
- [ ] Tâche #3: Tests automatisés (70%+ couverture)

### Sprint 2 (Performance & Features)
- [ ] Tâche #4: Web scraping parallèle (30-60min → 6-8min)
- [ ] Tâche #11: Auto-update BD (Service Windows)
- [ ] Tâche #5: Pool statistics viewer
- [ ] Tâche #10: CI/CD Pipeline (GitHub Actions)

### Sprint 3+ (Features Avancées)
- [ ] Tâche #6: GUI Desktop (tkinter/PyQt6)
- [ ] Tâche #7: Multi-plateformes (Linux/macOS)
- [ ] Tâche #8: Internationalisation (i18n)
- [ ] Tâche #12: Web App (optionnel)

---

## 📞 Support & Ressources

**Références Rapides**:
- [TODO.md](TODO.md) - Backlog Agile complet avec justifications
- [AUDIT_REPORT.md](AUDIT_REPORT.md) - État qualité projet
- [SECURITY_FIXES.md](SECURITY_FIXES.md) - Corrections v1.0.1

**Méthode Agile**:
- Scores Fibonacci: 1, 2, 3, 5, 8, 13, 21, 34
- ROI = Plus-value / Difficulté
- Dette Technique First = Qualité AVANT features

---

**Dernière mise à jour**: 2025-11-27
**Maintenu par**: Claude Code (Sonnet 4.5)
**Pour**: @pj35 - LeagueStats Coach v1.0.2

**Approche**: Dette Technique First → Refactoring + Tests + Migrations AVANT features 🔴🔴🔴
