# 🤖 CLAUDE.md - Instructions pour Assistant IA

**Projet**: LeagueStats Coach
**Version**: 1.1.0-dev (Sprint 2 in progress)
**Mainteneur**: @pj35
**Dernière mise à jour**: 2026-05-24

---

## 📋 Table des Matières

1. [🔵 Workflow claude-flow](#-workflow-claude-flow)
2. [Contexte du Projet](#contexte-du-projet)
3. [Workflow de Développement](#workflow-de-développement)
4. [Standards de Code](#standards-de-code)
5. [Conventions Git](#conventions-git)
6. [Process de Code Review](#process-de-code-review)
7. [Fichiers Importants](#fichiers-importants)
8. [Commandes Utiles](#commandes-utiles)

---

## 🔵 Workflow claude-flow

claude-flow est l'infrastructure d'orchestration et de mémoire persistante du projet. Tout le développement s'appuie sur ses outils MCP.

### Début de Session (Obligatoire)

**TOUJOURS** commencer par récupérer le contexte mémorisé :

```python
mcp__claude-flow__memory_search(query="projet leaguestats état sprint", smart=True)
mcp__claude-flow__memory_search(query="décisions architecture récentes", namespace="architecture")
```

### Mémoire Persistante : Ce qu'on Stocke

Après chaque décision importante ou bug résolu, stocker en mémoire pour les futures sessions :

```python
# Décision architecturale validée
mcp__claude-flow__memory_store(
    key="arch_decision_cloudflare_2026_05",
    value="Approche choisie : wait-for-redirect dans detect_cloudflare()",
    namespace="architecture"
)

# Bug résolu
mcp__claude-flow__memory_store(
    key="bug_executor_leak_fix",
    value="Réduire MAX_WORKERS à 5, ThreadPoolExecutor dans with block",
    namespace="bugs"
)

# Pattern établi
mcp__claude-flow__memory_store(
    key="pattern_retry_decorator",
    value="@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10), reraise=True)",
    namespace="patterns"
)
```

### Espaces Mémoire (Namespaces)

| Namespace | Contenu |
|-----------|---------|
| `architecture` | Décisions d'architecture validées |
| `bugs` | Bugs résolus et leurs causes |
| `patterns` | Patterns de code établis dans le projet |
| `sprint` | État courant du sprint (bloquants, en cours) |

### Travail Direct

L'assistant travaille directement avec les outils disponibles (Read, Edit, Write, Bash, Grep, Glob). Pas de workflow d'agents intermédiaires obligatoire.

Pour les tâches complexes nécessitant plusieurs angles en parallèle, utiliser claude-flow swarm :

```python
# Tâches parallèles
mcp__claude-flow__swarm_init(topology="hierarchical", maxAgents=4)
mcp__claude-flow__agent_spawn(type="researcher", task="Explorer l'approche A")
mcp__claude-flow__agent_spawn(type="researcher", task="Explorer l'approche B")
```

### Proposer des Approches

Pour toute décision architecturale non triviale, **toujours proposer 2-3 approches** avec trade-offs avant d'implémenter, et **attendre la validation** de l'utilisateur.

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

### État Actuel (Version 1.1.0-dev)

**✅ Sprint 1 - Dette Technique (COMPLÉTÉ 2025-12-16)**:
- Tâche #1: Refactoring fichiers monolithiques (<500 lignes/fichier)
- Tâche #3: Framework Tests Automatisés (89% coverage)
- Tâche #9: Database Migrations (Alembic 1.17.2)

**🔴 Sprint 2 - Performance & Features (EN COURS)**:
- Tâche #4: Web Scraping Parallèle ✅ **FAIT** (2025-12-20)
- Tâche #11: Auto-Update BD (Service Windows) ✅ **FAIT** (2025-12-22)
- Tâche #16: Support des Synergies ✅ **FAIT** (2026-01-16)

---

## 🔀 Workflow de Développement

### 1. Avant de Commencer une Tâche

```bash
# TOUJOURS créer feature branch DEPUIS MASTER
git checkout -b feature/task-name origin/master

# ❌ MAUVAIS - Créer depuis autre branche
git checkout feature/old-task
git checkout -b feature/new-task  # ❌ Contient commits de old-task!

# ✅ BON - Toujours depuis master
git checkout -b feature/new-task origin/master  # ✅ Propre!
```

### 2. Pendant le Développement

**Commits fréquents et atomiques**:
- ✅ Commit après chaque modification logique cohérente
- ✅ Messages de commit descriptifs et explicites
- ✅ Ne jamais regrouper plusieurs changements non liés

### 3. Avant de Créer la PR (Checklist Obligatoire)

**A. Tests pour les nouvelles fonctionnalités**:
```bash
# 1. Écrire tests pour TOUTE nouvelle fonctionnalité
# 2. Lancer TOUS les tests du projet
pytest tests/ -v

# 3. Compiler tous les fichiers Python
python -m py_compile src/**/*.py scripts/**/*.py
```

**B. Formatage du code avec Black**:
```bash
# 1. Appliquer le formatage Black à TOUS les fichiers modifiés
python -m black src/ tests/ scripts/

# 2. Vérifier que le formatage est conforme
python -m black --check --diff src/ tests/ scripts/
```

**C. Mise à jour documentation**:
- Mettre à jour CHANGELOG.md
- Mettre à jour README.md si nécessaire
- Mettre à jour docs/ si nécessaire

### 4. Code Review Process

**IMPORTANT**: Toujours demander validation avant de merge

**Étapes**:
1. ✅ **Checklist "Avant de Créer la PR" complétée**
2. ✅ Créer un résumé des changements pour l'utilisateur
3. ✅ **ATTENDRE VALIDATION** de l'utilisateur
4. ✅ Merger uniquement après approbation

---

## 📝 Standards de Code

### Style Python

**Général**:
- PEP 8 compliance
- **Black formatting**: Appliquer `python -m black` sur TOUT code modifié avant commit
- Type hints sur toutes les fonctions publiques
- Docstrings pour classes et méthodes publiques
- Maximum 500 lignes par fichier

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

**Framework**: pytest + pytest-cov + pytest-mock
**Couverture**: 89% du module analysis (objectif 70%+ largement dépassé)

**Structure**:
```
tests/
├── __init__.py
├── conftest.py
├── regression/              # Tests de régression (bugs fixes)
└── test_*.py
```

### Tests de Régression (Bug Fix Tests)

**RÈGLE CRITIQUE**: Pour chaque bug remonté par l'utilisateur et corrigé, **TOUJOURS** créer un test automatisé qui vérifie que ce bug ne revient jamais.

**Workflow**:
1. ✅ L'utilisateur remonte un bug avec message d'erreur/logs
2. ✅ Analyser et corriger le bug
3. ✅ **OBLIGATOIRE**: Créer un test de régression qui reproduit le bug
4. ✅ Vérifier que le test échoue AVANT le fix
5. ✅ Vérifier que le test passe APRÈS le fix
6. ✅ Committer le fix ET le test ensemble

---

## 🔀 Conventions Git

### Branches

**Format**: `feature/descriptive-name` ou `fix/bug-description`

**Exemples**:
- `feature/refactor-monolithic-files`
- `feature/database-migrations`
- `feature/parallel-scraping`
- `fix/sql-injection-vulnerabilities`

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
git commit -m "✅ Test: Add unit tests for scoring algorithms"
git commit -m "🗃️ Database: Add Alembic migration for role column"
```

---

## ✅ Process de Code Review (Pull Request GitHub)

### Workflow Pull Request

**IMPORTANT**: Utiliser les Pull Requests GitHub pour toutes les code reviews

**Commandes**:
```bash
# 1. Push feature branch
git push -u origin feature/task-name

# 2. Créer Pull Request avec gh CLI
gh pr create --title "🎯 Tâche #X: Titre de la tâche" \
             --body-file .github/PULL_REQUEST_TEMPLATE.md \
             --assignee @pj35 \
             --label "enhancement"

# 3. Après validation GitHub
gh pr merge --squash

# 4. Pull changes
git checkout master
git pull origin master
git branch -d feature/task-name
```

### Template de Pull Request

**📋 Voir `.github/PULL_REQUEST_TEMPLATE.md` pour le template complet**

### Validation GitHub

**L'assistant NE mergera JAMAIS sans**:
- ✅ Approbation explicite de l'utilisateur
- ✅ Aucun "Request changes" en attente
- ✅ Validation utilisateur claire

---

## 📂 Fichiers Importants

### Documentation

- `CLAUDE.md` - **CE FICHIER** - Instructions pour assistant IA
- `docs/alembic_guide.md` - Guide complet commandes Alembic
- `.github/PULL_REQUEST_TEMPLATE.md` - Template PR
- `TODO.md` - Backlog Agile avec scores Fibonacci
- `CHANGELOG.md` - Historique versions

### Configuration

- `src/config.py` - Configuration principale
- `src/config_constants.py` - Constantes centralisées

### Code Principal

**Modules refactorisés (Sprint 1 ✅)**:
- `src/analysis/` - Algorithmes d'analyse (220 lignes max/fichier)
- `src/ui/` - Interface utilisateur modulaire

**Web Scraping (Sprint 2 ✅)**:
- `src/parallel_parser.py` - Scraping parallèle (87% plus rapide)
- `src/cloudflare_detector.py` - Détection pages Cloudflare

**Autres modules**:
- `src/db.py` - Database layer
- `src/draft_monitor.py` - Real-time draft coach

### Tests

- `tests/` - Framework pytest avec 89% coverage
- `tests/regression/` - Tests de régression bugs

---

## 🛠️ Commandes Utiles

### Development

```bash
# Installation dépendances
pip install -r requirements.txt          # Production
pip install -r requirements-dev.txt      # Development

# Tests
pytest tests/ -v                         # Tous tests
pytest tests/ --cov=src --cov-report=html  # Avec couverture

# Compilation check
python -m py_compile src/*.py

# Code formatting (Black) - OBLIGATOIRE avant chaque commit
python -m black src/ tests/
python -m black --check --diff src/ tests/

# Linting
pylint src/ --fail-under=8.0
mypy src/ --ignore-missing-imports
```

### Git Workflow

```bash
# Créer feature branch
git checkout -b feature/task-name origin/master

# Commits fréquents
git add src/file.py
git commit -m "Type: Description"

# Vérifier statut
git status
git log --oneline -5
```

### Database Migrations (Alembic)

**📖 Voir `docs/alembic_guide.md` pour le guide complet des commandes Alembic**

**Commandes essentielles**:
```bash
# Check current version
python -m alembic current

# Upgrade to latest
python -m alembic upgrade head

# Create new migration
python -m alembic revision -m "Description"
```

---

## 🚨 Règles Critiques

### TOUJOURS

1. ✅ **Rechercher mémoire claude-flow** en début de session
2. ✅ **Stocker en mémoire** toute décision architecturale validée
3. ✅ **Feature branch DEPUIS MASTER** (`git checkout -b feature/name origin/master`)
4. ✅ **Commits atomiques** et fréquents
5. ✅ **Tests pour nouvelles fonctionnalités**
6. ✅ **Test de régression** pour chaque bug corrigé (OBLIGATOIRE)
7. ✅ **Tous les tests passent** avant PR (`pytest tests/ -v`)
8. ✅ **Formatage Black appliqué** avant PR (`python -m black src/ tests/`)
9. ✅ **Code review** AVANT tout merge
10. ✅ **Validation utilisateur** explicite requise avant merge
11. ✅ **Requêtes SQL paramétrées** (sécurité)
12. ✅ **config_constants.py** pour valeurs hardcodées
13. ✅ **Proposer 2-3 approches** pour toute décision architecturale non triviale

### JAMAIS

1. ❌ Merger sans validation utilisateur
2. ❌ Commits directs sur branche principale
3. ❌ Valeurs hardcodées dans le code
4. ❌ Interpolation string dans SQL
5. ❌ Fichiers >500 lignes
6. ❌ Code non testé en production
7. ❌ Breaking changes sans migration

---

**Dernière mise à jour**: 2026-05-24
**Maintenu par**: Claude Code (Sonnet 4.6)
**Pour**: @pj35 - LeagueStats Coach v1.1.0-dev
