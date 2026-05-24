# 🤖 CLAUDE.md - Instructions pour Assistant IA

**Projet**: LeagueStats Coach
**Version**: 1.1.0-dev (Sprint 2 in progress)
**Mainteneur**: @pj35
**Dernière mise à jour**: 2026-02-08

---

## 📋 Table des Matières

1. [🔴 Système d'Agents Custom - RÈGLE CRITIQUE](#-système-dagents-custom---règle-critique)
2. [🔵 claude-flow (RuFlo) - Orchestration & Mémoire](#-claude-flow-ruflo---orchestration--mémoire)
3. [Contexte du Projet](#contexte-du-projet)
4. [Workflow de Développement](#workflow-de-développement)
5. [Standards de Code](#standards-de-code)
6. [Conventions Git](#conventions-git)
7. [Process de Code Review](#process-de-code-review)
8. [Approche Dette Technique First](#approche-dette-technique-first)
9. [Fichiers Importants](#fichiers-importants)
10. [Commandes Utiles](#commandes-utiles)

---

## 🔴 Système d'Agents Custom - RÈGLE CRITIQUE

### ⚠️ WORKFLOW OBLIGATOIRE ⚠️

**AVANT toute action de développement, TOUJOURS utiliser les agents custom définis dans `.claude/agents/`**

Ce projet utilise un système d'agents spécialisés pour orchestrer TOUT le développement. L'assistant principal (toi) ne doit JAMAIS coder/tester/commiter directement.

### Principe Fondamental

```
❌ INTERDIT: Travailler directement (Read → Edit → Write → Bash pytest → git commit)
✅ OBLIGATOIRE: Spawner les agents appropriés via Task tool (ou claude-flow swarm pour le parallèle)
✅ OPTIONNEL: Utiliser claude-flow memory pour persistance cross-session
```

### Architecture des Agents

**Agents disponibles dans `.claude/agents/`**:

| Agent | Fichier | Rôle | Output | Spawné par |
|-------|---------|------|--------|------------|
| **Architecte** | `01-architecte.md` | Analyse besoins + 2-3 approches | Plan YAML (approaches) | Assistant (toi) |
| **Tech Lead** | `02-tech-lead.md` | **Décomposition en TODOs tracés** | Plan YAML (TODOs + agents recommandés) | Assistant (toi) |
| **Python Expert** | `03-python-expert.md` | Développement Python | YAML silencieux | Assistant (toi) |
| **Database Expert** | `04-database-expert.md` | Migrations Alembic + SQL | YAML silencieux | Assistant (toi) |
| **QA Expert** | `05-qa-expert.md` | Tests (unitaires + régression) | YAML silencieux | Assistant (toi) |
| **Scraping Expert** | `06-scraping-expert.md` | Selenium + XPath | YAML silencieux | Assistant (toi) |
| **Build Expert** | `07-build-expert.md` | PyInstaller + packaging | YAML silencieux | Assistant (toi) |
| **Git Expert** | `08-git-expert.md` | Commits Gitmoji + PR | YAML silencieux | Assistant (toi) |
| **Windows Expert** | `09-windows-expert.md` | Task Scheduler + services | YAML silencieux | Assistant (toi) |
| **LCU API Expert** | `10-lcu-api-expert.md` | League Client API | YAML silencieux | Assistant (toi) |
| **Performance Expert** | `11-performance-expert.md` | Profiling + optimisation | YAML silencieux | Assistant (toi) |

**Hiérarchie**:
```
Assistant (toi) → Spawne ARCHITECTE (si analyse requise)
                         ↓
                   Explore + Propose 2-3 approches
                         ↓
                   Utilisateur valide approche
                         ↓
Assistant (toi) → Spawne TECH LEAD (avec approche validée)
                         ↓
                   Analyse + Décompose en TODOs tracés
                         ↓
                   Crée TODOs via TaskCreate
                         ↓
                   Retourne plan YAML (TODOs + agents recommandés)
                         ↓
Assistant (toi) → Lit TaskList et spawne EXPERTS séquentiellement
                         ↓
                   EXPERT → Exécute TODO → Retourne YAML
                         ↓
Assistant (toi) → Valide output + Mark TODO completed + Next TODO
                         ↓
                   Tous TODOs complétés
                         ↓
Assistant (toi) → Résumé + Demande validation utilisateur
```

### Matrice de Décision (Quick Reference)

| Demande Utilisateur | Premier Agent | Justification |
|---------------------|---------------|---------------|
| **"Ajoute feature X"** | Architecte | Besoin d'analyse d'approches (2-3 options) |
| **"Implémente Tâche #N"** (complexe) | Architecte | Besoin d'exploration codebase + trade-offs |
| **"Implémente Tâche #N"** (plan clair) | Tech Lead | Plan déjà défini dans TODO.md |
| **"Corrige bug Y"** (simple) | Tech Lead | Bug connu, correction directe |
| **"Corrige bug Y"** (cause inconnue) | Architecte | Investigation requise (exploration) |
| **"Optimise performance Z"** | Architecte | Profiling + analyse approches |
| **"Ajoute migration BD"** | Tech Lead | Tâche technique directe |
| **"Ajoute tests pour X"** | Tech Lead | Tests après développement existant |
| **"Refactor module Y"** | Architecte | Analyse impact + approches |

### 🔴 RÈGLES CRITIQUES

#### 1. Délégation Obligatoire

```python
# ❌ INTERDIT (Assistant travaille directement)
User: "Ajoute colonne lane à la BD"
Assistant: [Read alembic/...]
Assistant: [Write alembic/versions/xxx.py]
Assistant: [Bash alembic upgrade head]

# ✅ OBLIGATOIRE (Spawner Tech Lead puis experts)
User: "Ajoute colonne lane à la BD"
Assistant: [Task tool: Tech Lead avec description tâche]
Tech Lead: [Crée TODOs T1-T4 avec agents recommandés, retourne plan YAML]
Assistant: [Lit TaskList, spawne Database Expert pour T1]
Database Expert: [Crée migration, teste, retourne YAML]
Assistant: [Valide, mark T1 completed, spawne Python Expert pour T2]
Python Expert: [Modifie code, retourne YAML]
Assistant: [Continue jusqu'à T4 complété, présente résumé]
```

#### 2. JAMAIS Coder/Tester/Commiter Directement

**L'assistant principal (toi) ne doit JAMAIS**:
- ❌ Edit/Write du code Python
- ❌ Créer migrations Alembic
- ❌ Écrire tests pytest
- ❌ Exécuter git commit
- ❌ Créer PR avec gh CLI

**L'assistant principal (toi) doit UNIQUEMENT**:
- ✅ Spawner ARCHITECTE (si analyse requise)
- ✅ Spawner TECH LEAD (décomposition en TODOs)
- ✅ Spawner EXPERTS séquentiellement (basé sur recommandations Tech Lead)
- ✅ Valider outputs YAML des experts
- ✅ Gérer TaskList (mark completed, next TODO)
- ✅ Lire documentation (.claude/agents/*.md)
- ✅ Communiquer avec utilisateur

#### 3. Tech Lead = Décomposeur de Tâches

Pour **99% des tâches de développement**, spawner **Tech Lead** en premier (sauf si analyse architecturale nécessaire → Architecte).

Le Tech Lead **décomposera** la tâche en TODOs tracés et **recommandera** les agents appropriés, mais **ne les spawnera pas**. C'est l'assistant principal (toi) qui spawnera ensuite chaque expert séquentiellement.

#### 4. Toujours Lire l'Agent Avant de Spawner

Avant de spawner un agent, **TOUJOURS lire son fichier .md** dans `.claude/agents/` pour comprendre :
- Son rôle exact
- Son OUTPUT FORMAT attendu
- Ses outils autorisés/interdits
- Ses règles critiques

### Exemples d'Utilisation

**📖 Voir `.claude/agents/EXAMPLES.md` pour des exemples détaillés de workflows complets**

---

## 🔵 claude-flow (RuFlo) - Orchestration & Mémoire

claude-flow est la couche d'infrastructure qui **complète** le système d'agents custom. Les agents métier (Architecte, Tech Lead, experts) restent inchangés — claude-flow leur apporte orchestration parallèle et mémoire persistante.

### Quand utiliser claude-flow ?

| Besoin | Outil claude-flow | Quand |
|--------|-------------------|-------|
| **Mémoire cross-session** | `mcp__claude-flow__memory_store/retrieve/search` | Après chaque décision architecturale, bug résolu, pattern appris |
| **Agents parallèles** | `mcp__claude-flow__swarm_init + agent_spawn + task_orchestrate` | Quand le Tech Lead identifie des `parallel_groups` |
| **Contexte projet** | `mcp__claude-flow__memory_search` | En début de session pour récupérer l'état du projet |
| **Patterns appris** | `mcp__claude-flow__neural_patterns` | Pour détecter des patterns récurrents dans le code |

### Workflow Mis à Jour avec claude-flow

```
Début de session
       ↓
[claude-flow memory_search] → Récupérer contexte projet (décisions, patterns, bugs)
       ↓
Assistant → Spawne ARCHITECTE (si analyse requise)
       ↓
[claude-flow memory_store] → Mémoriser l'approche validée
       ↓
Assistant → Spawne TECH LEAD → Retourne TODOs avec parallel_groups
       ↓
Si parallel_groups :
  [claude-flow swarm_init + agent_spawn] → Orchestrer experts en parallèle
Sinon :
  Assistant → Spawne experts séquentiellement via Task tool (comme avant)
       ↓
[claude-flow memory_store] → Mémoriser les patterns/solutions trouvés
       ↓
Résumé + validation utilisateur
```

### Mémoire Projet : Ce qu'on Stocke

```python
# Après validation d'une approche architecturale
mcp__claude-flow__memory_store(
    key="arch_decision_cloudflare_2026_05",
    value="Approche 1 choisie : patch Firefox dom.webdriver.enabled=False + CloudflareDetector",
    namespace="architecture"
)

# Après résolution d'un bug
mcp__claude-flow__memory_store(
    key="bug_executor_leak_fix",
    value="Réduire MAX_WORKERS à 5, ThreadPoolExecutor dans with block",
    namespace="bugs"
)
```

### Espaces Mémoire (Namespaces)

| Namespace | Contenu |
|-----------|---------|
| `architecture` | Décisions d'architecture validées |
| `bugs` | Bugs résolus et leurs causes |
| `patterns` | Patterns de code établis dans le projet |
| `sprint` | État courant du sprint (TODOs en cours, bloquants) |

### Règles d'Utilisation

1. ✅ **Stocker en mémoire** toute décision architecturale validée par l'utilisateur
2. ✅ **Rechercher en mémoire** en début de session avant de proposer des solutions
3. ✅ **Swarm pour le parallèle** : quand Tech Lead identifie `parallel_groups`, utiliser claude-flow swarm plutôt que Task tool séquentiel
4. ❌ **Ne pas remplacer les agents custom** par des agents génériques claude-flow — les agents `.claude/agents/` ont la connaissance projet

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
- Tâche #16: Support des Synergies 🔴 **EN COURS**

### Philosophie: Dette Technique First

**Principe**: Résoudre dette technique AVANT features = Vélocité élevée ensuite

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

**Framework**: pytest + pytest-cov + pytest-mock
**Couverture**: **89% du module analysis (objectif 70%+ largement dépassé)

**Structure**:
```
tests/
├── __init__.py
├── conftest.py              # Fixtures partagées
├── test_scoring.py          # 27 tests - 95% coverage
├── test_tier_list.py        # 18 tests - 100% coverage
└── test_team_analysis.py    # 13 tests - 97% coverage
```

### Tests de Régression (Bug Fix Tests)

**🔴 RÈGLE CRITIQUE**: Pour chaque bug remonté par l'utilisateur et corrigé, **TOUJOURS** créer un test automatisé qui vérifie que ce bug ne revient jamais.

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
git checkout inspiring-rhodes
git pull origin inspiring-rhodes
git branch -d feature/task-name
```

### Template de Pull Request

**📋 Voir `.github/PULL_REQUEST_TEMPLATE.md` pour le template complet**

### Validation GitHub

**L'assistant NE mergera JAMAIS sans**:
- ✅ Approbation explicite sur GitHub ("Approved")
- ✅ Aucun "Request changes" en attente
- ✅ Validation utilisateur claire

---

## 🔴 Approche Dette Technique First

### Principe

**Résoudre dette technique AVANT features** = Vélocité élevée ensuite

### Sprint 1 - Dette Technique (COMPLÉTÉ ✅)

**Objectif**: Fondations solides

**Tâches**:
1. ✅ **Tâche #1**: Refactoring fichiers monolithiques
2. ✅ **Tâche #3**: Framework Tests Automatisés (89% couverture)
3. ✅ **Tâche #9**: Migrations Base de Données (Alembic 1.17.2)

**Impact**: Code maintenable + tests auto (89%) + migrations = Base saine ✅

### Métriques Cibles Sprint 1

| Métrique | Avant | Après Sprint 1 | Statut |
|----------|-------|----------------|--------|
| Largest File | 2,381 lignes | **<500 lignes** | ✅ Atteint |
| Test Coverage | ~5% | **89%** (analysis module) | ✅ Dépassé |
| Migrations BD | Non | **Alembic 1.13+** | ✅ Opérationnel |
| Hardcoded Values | ~20 | **0** | ✅ Complété |

---

## 📂 Fichiers Importants

### Documentation

- `CLAUDE.md` - **CE FICHIER** - Instructions pour assistant IA
- `.claude/agents/EXAMPLES.md` - Exemples détaillés de workflows agents
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

**Autres modules**:
- `src/db.py` - Database layer
- `src/draft_monitor.py` - Real-time draft coach

### Tests (Sprint 1 ✅)

- `tests/` - Framework pytest avec 89% coverage

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

1. ✅ **Feature branch DEPUIS MASTER** (`git checkout -b feature/name origin/master`)
2. ✅ **Commits atomiques** et fréquents
3. ✅ **Tests pour nouvelles fonctionnalités**
4. ✅ **Test de régression** pour chaque bug corrigé (OBLIGATOIRE)
5. ✅ **Tous les tests passent** avant PR (`pytest tests/ -v`)
6. ✅ **Formatage Black appliqué** avant PR (`python -m black src/ tests/`)
7. ✅ **Code review** AVANT tout merge
8. ✅ **Validation utilisateur** explicite requise
9. ✅ **Requêtes SQL paramétrées** (sécurité)
10. ✅ **config_constants.py** pour valeurs hardcodées

### JAMAIS

1. ❌ Merger sans validation utilisateur
2. ❌ Commits directs sur branche principale
3. ❌ Valeurs hardcodées dans le code
4. ❌ Interpolation string dans SQL
5. ❌ Fichiers >500 lignes (après Sprint 1)
6. ❌ Code non testé en production
7. ❌ Breaking changes sans migration
8. ❌ Features AVANT dette technique (Sprint 1)

---

**Dernière mise à jour**: 2026-01-16
**Maintenu par**: Claude Code (Sonnet 4.5)
**Pour**: @pj35 - LeagueStats Coach v1.1.0-dev
