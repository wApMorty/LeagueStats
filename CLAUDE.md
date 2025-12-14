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
- **Web Scraping**: Selenium + Firefox
- **Distribution**: PyInstaller (standalone .exe)
- **Tests**: pytest + pytest-cov

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

**Couverture Minimale**: 70% (objectif Sprint 1)

```python
import pytest
from src.assistant import Assistant

@pytest.fixture
def assistant(tmp_path):
    """Fixture pour Assistant avec DB temporaire."""
    db_path = tmp_path / "test.db"
    return Assistant(db_path)

def test_calculate_score(assistant):
    """Test calcul score avec cas nominal."""
    # Arrange
    delta2 = 2.5

    # Act
    score = assistant.calculate_score(delta2)

    # Assert
    assert 0 <= score <= 100
    assert score > 50  # Champion favorable
```

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

### Commits

**Format**: `Type: Description courte`

**Types**:
- `Feature:` - Nouvelle fonctionnalité
- `Refactor:` - Refactoring sans changement de comportement
- `Fix:` - Correction de bug
- `Test:` - Ajout/modification de tests
- `Docs:` - Documentation
- `Perf:` - Amélioration performance
- `Chore:` - Maintenance (deps, config, etc.)

**Exemples**:
```bash
git commit -m "Refactor: Extract UI logic to src/ui/ modules"
git commit -m "Feature: Add database migrations with Alembic"
git commit -m "Fix: SQL injection in get_champion_id()"
git commit -m "Test: Add unit tests for scoring algorithms (70% coverage)"
git commit -m "Perf: Add database indexes for 50-80% speedup"
git commit -m "Docs: Update TODO.md with Dette Technique First approach"
```

### Messages de Commit Détaillés

Pour les commits complexes, utiliser description étendue:

```bash
git commit -m "Refactor: Decompose assistant.py into analysis/ modules

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

## ✅ Process de Code Review

### Template de Review Request

Utiliser ce template pour demander validation:

```markdown
# 🔍 Code Review Request - Tâche #X: [Nom Tâche]

## 📊 Résumé

**Branche**: `feature/task-name`
**Tâche**: #X - [Nom complet]
**Durée**: X jours
**Commits**: X commits

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
1. [hash] - Type: Description commit 1
2. [hash] - Type: Description commit 2
3. [hash] - Type: Description commit 3
```

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

Après validation:
1. Merger feature branch → inspiring-rhodes
2. Supprimer feature branch
3. Mettre à jour TODO.md (marquer tâche ✅)
4. Commencer Tâche #Y (si applicable)

## ❓ Questions

[Questions éventuelles pour l'utilisateur]

---

**Status**: ❌ **EN ATTENTE DE VALIDATION UTILISATEUR**

Pouvez-vous valider ces changements pour que je procède au merge ?
```

### Validation Utilisateur

**NE JAMAIS merger sans validation explicite**:
- ✅ "OK, tu peux merger"
- ✅ "Approuvé, go ahead"
- ✅ "Parfait, merge"
- ❌ Absence de réponse
- ❌ Question sur les changements

---

## 🔴 Approche Dette Technique First

### Principe

**Résoudre dette technique AVANT features** = Vélocité élevée ensuite

### Sprint 1 - Dette Technique (EN COURS)

**Objectif**: Fondations solides

**Tâches**:
1. 🔴🔴🔴 **Tâche #1**: Refactoring fichiers monolithiques (2-3j) - **NEXT**
   - `lol_coach.py` (2,160 lignes) → `src/ui/` modules
   - `assistant.py` (2,381 lignes) → `src/analysis/` modules
   - Objectif: <500 lignes/fichier

2. 🔴 **Tâche #9**: Migrations Base de Données (1j)
   - Setup Alembic
   - Migrations initiales
   - Protection perte données

3. 🔴🔴 **Tâche #3**: Framework Tests Automatisés (3-5j)
   - Setup pytest + pytest-cov
   - Tests scoring algorithms
   - Objectif: 70% couverture

**Impact**: Code maintenable + tests auto + migrations = Base saine pour TOUS futurs développements

### Métriques Cibles Sprint 1

| Métrique | Actuel | Objectif Sprint 1 |
|----------|--------|-------------------|
| Largest File | 2,381 lignes | **<500 lignes** 🔴🔴🔴 |
| Test Coverage | ~5% | **70%+** 🔴🔴 |
| Migrations BD | Non 🔴 | **Alembic** 🔴 |
| Hardcoded Values | ~20 | **0** ✅ (déjà fait) |

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
