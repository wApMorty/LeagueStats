# 🤖 CLAUDE.md - Instructions pour Assistant IA

**Projet**: LeagueStats Coach
**Version**: 1.1.0-dev (Sprint 2 in progress)
**Mainteneur**: @pj35
**Dernière mise à jour**: 2026-01-05

---

## 📋 Table des Matières

1. [🔴 Système d'Agents Custom - RÈGLE CRITIQUE](#-système-dagents-custom---règle-critique)
2. [Contexte du Projet](#contexte-du-projet)
3. [Workflow de Développement](#workflow-de-développement)
4. [Standards de Code](#standards-de-code)
5. [Conventions Git](#conventions-git)
6. [Process de Code Review](#process-de-code-review)
7. [Approche Dette Technique First](#approche-dette-technique-first)
8. [Fichiers Importants](#fichiers-importants)
9. [Commandes Utiles](#commandes-utiles)

---

## 🔴 Système d'Agents Custom - RÈGLE CRITIQUE

### ⚠️ WORKFLOW OBLIGATOIRE - À LIRE EN PREMIER ⚠️

**AVANT toute action de développement, TOUJOURS utiliser les agents custom définis dans `.claude/agents/`**

Ce projet utilise un système d'agents spécialisés pour orchestrer TOUT le développement. L'assistant principal (toi) ne doit JAMAIS coder/tester/commiter directement.

### Principe Fondamental

```
❌ INTERDIT: Travailler directement (Read → Edit → Write → Bash pytest → git commit)
✅ OBLIGATOIRE: Spawner les agents appropriés via Task tool
```

### Architecture des Agents

**Agents disponibles dans `.claude/agents/`**:

| Agent | Fichier | Rôle | Output | Spawné par |
|-------|---------|------|--------|------------|
| **Orchestrateur** | `00-orchestrateur.md` | Routage automatique des tâches | Plan YAML (phases) | Tech Lead |
| **Architecte** | `01-architecte.md` | Analyse besoins + 2-3 approches | Plan YAML (approaches) | Assistant (toi) |
| **Tech Lead** | `02-tech-lead.md` | **Coordination workflow complet** | Verbeux (notifications) | Assistant (toi) |
| **Python Expert** | `03-python-expert.md` | Développement Python | YAML silencieux | Tech Lead |
| **Database Expert** | `04-database-expert.md` | Migrations Alembic + SQL | YAML silencieux | Tech Lead |
| **QA Expert** | `05-qa-expert.md` | Tests (unitaires + régression) | YAML silencieux | Tech Lead |
| **Scraping Expert** | `06-scraping-expert.md` | Selenium + XPath | YAML silencieux | Tech Lead |
| **Build Expert** | `07-build-expert.md` | PyInstaller + packaging | YAML silencieux | Tech Lead |
| **Git Expert** | `08-git-expert.md` | Commits Gitmoji + PR | YAML silencieux | Tech Lead |
| **Windows Expert** | `09-windows-expert.md` | Task Scheduler + services | YAML silencieux | Tech Lead |
| **LCU API Expert** | `10-lcu-api-expert.md` | League Client API | YAML silencieux | Tech Lead |
| **Performance Expert** | `11-performance-expert.md` | Profiling + optimisation | YAML silencieux | Tech Lead |

**Hiérarchie**:
```
Assistant (toi) → Spawne ARCHITECTE ou TECH LEAD
                         ↓
                   TECH LEAD → Spawne ORCHESTRATEUR
                         ↓
                   ORCHESTRATEUR → Plan d'exécution
                         ↓
                   TECH LEAD → Spawne EXPERTS (Python, DB, QA, Git, etc.)
                         ↓
                   TECH LEAD → Valide + Notifie client
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

### Workflow Standard

#### Scénario 1: Feature Nouvelle / Besoin d'Analyse

```
USER: "Ajoute support des lanes"
  ↓
ASSISTANT (toi): Spawne ARCHITECTE
  ↓
ARCHITECTE:
  - Explore codebase (.claude/agents/01-architecte.md)
  - Analyse besoins techniques
  - Propose 2-3 approches (A, B, C) avec pros/cons
  - Retourne plan YAML structuré
  ↓
USER: "Je choisis approche A"
  ↓
ASSISTANT (toi): Spawne TECH LEAD avec plan Architecte (approche A)
  ↓
TECH LEAD (.claude/agents/02-tech-lead.md):
  1. Crée feature branch (git checkout -b feature/xxx origin/master)
  2. Découpe en tâches atomiques (TodoWrite)
  3. Spawne ORCHESTRATEUR → Plan d'exécution optimisé
  4. Exécute phases séquentielles:
     - Phase 1: Database Expert (migration BD) [BLOQUANT]
     - Phase 2: Python Expert + Scraping Expert [PARALLÈLE]
     - Phase 3: QA Expert (tests) [BLOQUANT]
     - Phase 4: Git Expert (commits + PR)
  5. Valide chaque livrable (compilation, imports, standards)
  6. Notifie client: "✅ PR #42 créée et prête pour review"
```

#### Scénario 2: Bug Fix Simple

```
USER: "Corrige division by zero dans scoring.py"
  ↓
ASSISTANT (toi): Spawne TECH LEAD directement
  ↓
TECH LEAD:
  1. Crée fix branch (git checkout -b fix/division-by-zero origin/master)
  2. TodoWrite (T1: Fix code, T2: Test régression, T3: Commit)
  3. Spawne ORCHESTRATEUR → Plan
  4. Exécute phases:
     - Phase 1: Python Expert (fix code)
     - Phase 2: QA Expert (test régression OBLIGATOIRE)
     - Phase 3: Git Expert (commit + PR)
  5. Valide + Notifie client
```

#### Scénario 3: Optimisation Performance

```
USER: "Optimise la génération de tier lists (trop lente)"
  ↓
ASSISTANT (toi): Spawne ARCHITECTE (besoin profiling + analyse)
  ↓
ARCHITECTE:
  - Profile code existant (identifie bottlenecks)
  - Propose 2-3 approches (ex: caching, indexes DB, algorithme optimisé)
  - Trade-offs détaillés
  ↓
USER: "Approche B (caching)"
  ↓
ASSISTANT (toi): Spawne TECH LEAD
  ↓
TECH LEAD → [Workflow standard avec Performance Expert en phase 1]
```

### 🔴 RÈGLES CRITIQUES - À RESPECTER ABSOLUMENT

#### 1. Délégation Obligatoire

```python
# ❌ INTERDIT (Assistant travaille directement)
User: "Ajoute colonne lane à la BD"
Assistant: [Read alembic/...]
Assistant: [Write alembic/versions/xxx.py]
Assistant: [Bash alembic upgrade head]

# ✅ OBLIGATOIRE (Spawner Tech Lead)
User: "Ajoute colonne lane à la BD"
Assistant: [Task tool: Tech Lead avec description tâche]
Tech Lead: [Spawne Database Expert]
Database Expert: [Crée migration, teste, retourne YAML]
Tech Lead: [Valide + continue workflow]
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
- ✅ Spawner TECH LEAD (coordination)
- ✅ Lire documentation (.claude/agents/*.md)
- ✅ Communiquer avec utilisateur

#### 3. Tech Lead = Point d'Entrée Principal

Pour **99% des tâches de développement**, spawner **Tech Lead** en premier (sauf si analyse architecturale nécessaire → Architecte).

Le Tech Lead orchestrera **automatiquement** tous les autres agents.

#### 4. Experts = Output YAML Silencieux

Tous les agents experts (Python, Database, QA, Git, etc.) retournent **UNIQUEMENT du YAML structuré**, pas de prose.

**Exemple output Python Expert**:
```yaml
status: "✅ DONE"
task_id: "T2"
files_modified:
  - path: "src/analysis/scoring.py"
    lines_changed: "+45 -12"
commit_message: "✨ Feature: Add lane priority weighting"
notes: "Backward compatible (null lane = 1.0x multiplier)"
issues: []
```

Seuls **Tech Lead** et **Architecte** sont verbeux (explications pour client).

#### 5. Toujours Lire l'Agent Avant de Spawner

Avant de spawner un agent, **TOUJOURS lire son fichier .md** dans `.claude/agents/` pour comprendre :
- Son rôle exact
- Son OUTPUT FORMAT attendu
- Ses outils autorisés/interdits
- Ses règles critiques

### Exemples Concrets d'Utilisation

#### ✅ Exemple 1: Feature Complète (Tâche #15 - Support Lanes)

```
User: "Implémente la Tâche #15 (Support des Lanes) du TODO.md"

Assistant (toi):
  "Je vais spawner l'Architecte pour analyser cette feature et proposer des approches."
  [Task: Architecte, description: Tâche #15 Support Lanes]

Architecte retourne:
  - Approche A: Lane nullable (backward compat) - Complexité 5, 3-4j, low risk
  - Approche B: Lane obligatoire (breaking) - Complexité 8, 2j+rescrape, high risk
  - Approche C: Table séparée - Complexité 8, 4-5j, medium risk
  - Recommandation: Approche A (meilleur ratio valeur/risque)

User: "OK, approche A"

Assistant (toi):
  "Je spawne maintenant le Tech Lead pour coordonner l'implémentation."
  [Task: Tech Lead, description: Tâche #15 avec approche A validée]

Tech Lead:
  1. Crée feature branch: git checkout -b feature/lane-support origin/master
  2. TodoWrite: [T1: Migration BD, T2: Code Python, T3: Scraping, T4: Tests, T5: Git]
  3. Spawne Orchestrateur → Plan: Phase1=[T1], Phase2=[T2,T3], Phase3=[T4], Phase4=[T5]
  4. Phase 1 (bloquante):
     - Spawne Database Expert
     - Database Expert retourne YAML: migration créée, testée up/down
     - Tech Lead valide: alembic current, compilation OK
  5. Phase 2 (parallèle):
     - Spawne Python Expert (scoring logic)
     - Spawne Scraping Expert (parse lane data)
     - Attends complétion des DEUX
     - Tech Lead valide: py_compile OK, imports OK
  6. Phase 3 (bloquante):
     - Spawne QA Expert avec TOUS fichiers modifiés
     - QA Expert retourne: 18 tests, 18 passed, 95% coverage
     - Tech Lead valide: pytest OK
  7. Phase 4:
     - Spawne Git Expert avec liste commits
     - Git Expert: 3 commits + PR #42 créée
  8. Tech Lead notifie:
     "✅ Feature terminée - PR #42 prête pour review"
```

#### ✅ Exemple 2: Bug Fix Simple

```
User: "Corrige le bug: division by zero dans scoring.calculate_weighted_avg()"

Assistant (toi):
  "Je spawne le Tech Lead pour orchestrer la correction."
  [Task: Tech Lead, description: Bug division by zero]

Tech Lead:
  1. Crée fix branch: git checkout -b fix/division-by-zero origin/master
  2. TodoWrite: [T1: Fix code, T2: Test régression, T3: Commit]
  3. Spawne Orchestrateur → Plan simple
  4. Phase 1: Spawne Python Expert
     - Python Expert: Ajoute check if total_games == 0: return 0.0
     - Retourne YAML
  5. Phase 2: Spawne QA Expert
     - QA Expert: Crée test_regression_division_by_zero.py
     - Test échoue AVANT fix, passe APRÈS fix ✅
     - Retourne YAML
  6. Phase 3: Spawne Git Expert
     - Commit 1: "🐛 Fix: Division by zero in calculate_weighted_avg()"
     - Commit 2: "✅ Test: Add regression test for division by zero"
     - PR #43 créée
  7. Tech Lead notifie client
```

#### ❌ Exemple 3: Ce qu'il NE FAUT JAMAIS FAIRE

```
User: "Ajoute colonne lane à la BD"

❌ MAUVAIS - Assistant travaille directement:
Assistant: "Je vais créer la migration Alembic..."
[Read alembic/env.py]
[Write alembic/versions/abc123_add_lane.py]
[Bash: alembic upgrade head]
[Edit src/db.py]
"✅ Migration créée"

✅ BON - Assistant spawne Tech Lead:
Assistant: "Je spawne le Tech Lead pour coordonner cette modification BD."
[Task: Tech Lead, description: Ajouter colonne lane]
Tech Lead → Database Expert → Migration créée + testée
Tech Lead → Valide → Notifie
```

### Localisation et Documentation

- **Tous les agents**: `.claude/agents/*.md` (12 agents)
- **TOUJOURS lire l'agent** avant de le spawner pour comprendre:
  - Son workflow exact
  - Son OUTPUT FORMAT (YAML structure)
  - Ses outils autorisés/interdits
  - Ses règles critiques spécifiques

### Checklist Avant Toute Action

Avant de faire QUOI QUE CE SOIT sur une demande utilisateur :

- [ ] Ai-je lu la demande utilisateur attentivement ?
- [ ] Est-ce une tâche de développement (code/BD/tests/git) ?
- [ ] Si OUI → Dois-je spawner Architecte (analyse) ou Tech Lead (direct) ?
- [ ] Ai-je lu le fichier .md de l'agent que je vais spawner ?
- [ ] Ai-je préparé une description claire pour l'agent ?
- [ ] Suis-je certain de NE PAS coder/tester/commiter moi-même ?

### En Cas de Doute

**Si tu hésites sur quel agent spawner**:
1. Lire `.claude/agents/00-orchestrateur.md` (matrice de routage)
2. Lire `.claude/agents/02-tech-lead.md` (coordination générale)
3. **Par défaut**: Spawner **Tech Lead** (il déléguera automatiquement)

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
  - ✅ Bug #1 fix: Cookie click dynamic detection
  - ✅ ParallelParser avec ThreadPoolExecutor (10 workers)
  - ✅ Retry mechanism avec exponential backoff
  - ✅ **87% performance improvement** (12min vs 90-120min)
  - ✅ Thread-safe database operations
  - ✅ Real-time progress tracking
- Tâche #11: Auto-Update BD (Service Windows) ✅ **FAIT** (2025-12-22)
  - ✅ Script auto-update avec ParallelParser (12min execution)
  - ✅ Task Scheduler setup wizard (PowerShell)
  - ✅ Background execution (BELOW_NORMAL priority)
  - ✅ Windows toast notifications (win10toast)
  - ✅ Detailed logging system
  - ✅ **Zero maintenance** - Daily automated updates (3 AM)
- Restauration méthodes Assistant ✅ **FAIT** (2025-12-20)
  - ✅ 24 méthodes manquantes restaurées (+902 lignes)
  - ✅ Live podium display pour optimisation
  - ✅ 54 méthodes total (vs 30 avant)

**Version précédente (v1.0.2)**:
- SQL injection fixes (v1.0.1)
- Database indexes pour performance (v1.0.1)
- Extraction valeurs hardcodées → config_constants.py (v1.0.2)
- Bug #2 fix: SyntaxWarning parser.py (v1.0.2)

### Philosophie: Dette Technique First

**Principe**: Résoudre la dette technique AVANT d'ajouter des features pour :
- ✅ Éviter refactoring complexe plus tard
- ✅ Faciliter TOUTES les futures tâches
- ✅ Base saine = vélocité élevée

**Ordre Sprint**:
1. ✅ Sprint 0: Configuration (Tâche #2 - FAIT)
2. ✅ Sprint 1: Dette Technique (Refactoring + Tests + Migrations - COMPLÉTÉ)
3. 🔴 Sprint 2: Performance & Features (EN COURS)
4. 🟡 Sprint 3+: Features Avancées

---

## 🔀 Workflow de Développement

### 1. Avant de Commencer une Tâche

```bash
# 1. S'assurer d'être sur master/main à jour
git fetch origin
git checkout clean-workspace  # ou master selon worktree
git pull origin master

# 2. TOUJOURS créer feature branch DEPUIS MASTER
git checkout -b feature/task-name origin/master

# ❌ MAUVAIS - Créer depuis autre branche
git checkout feature/old-task
git checkout -b feature/new-task  # ❌ Contient commits de old-task!

# ✅ BON - Toujours depuis master
git checkout -b feature/new-task origin/master  # ✅ Propre!

# Exemples:
# git checkout -b feature/refactor-monolithic-files origin/master
# git checkout -b feature/database-migrations origin/master
# git checkout -b feature/parallel-scraping origin/master
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

### 3. Avant de Créer la PR (Checklist Obligatoire)

**🔴 ÉTAPES CRITIQUES - À FAIRE SYSTÉMATIQUEMENT**:

**A. Tests pour les nouvelles fonctionnalités**:
```bash
# 1. Écrire tests pour TOUTE nouvelle fonctionnalité
# - Tests unitaires pour fonctions/méthodes
# - Tests d'intégration si nécessaire
# - Tests de régression si correction de bug

# 2. Ajouter les tests
git add tests/test_nouvelle_feature.py
git commit -m "✅ Test: Add tests for nouvelle_feature (X tests, Y% coverage)"
```

**B. Validation des tests**:
```bash
# 1. Lancer TOUS les tests du projet
pytest tests/ -v

# 2. Vérifier couverture (optionnel mais recommandé)
pytest tests/ --cov=src --cov-report=term

# 3. Compiler tous les fichiers Python
python -m py_compile src/**/*.py scripts/**/*.py

# ❌ Si un test échoue → CORRIGER avant PR
# ✅ Tous les tests doivent passer avant de continuer
```

**C. Formatage du code avec Black**:
```bash
# 1. Appliquer le formatage Black à TOUS les fichiers modifiés
python -m black src/ tests/ scripts/

# 2. Vérifier que le formatage est conforme
python -m black --check --diff src/ tests/ scripts/

# 3. Commiter les changements de formatage si nécessaire
git add -u
git commit -m "🎨 Style: Apply Black formatting"

# ❌ Si Black détecte des problèmes → CORRIGER avant PR
# ✅ Le pipeline CI/CD vérifie automatiquement le formatage Black
# ✅ TOUJOURS formater AVANT de push pour éviter échec pipeline
```

**D. Mise à jour documentation**:
```bash
# 1. Mettre à jour CHANGELOG.md
# - Ajouter nouvelle feature dans section appropriée
# - Documenter changements breaking si applicable

# 2. Mettre à jour README.md si nécessaire
# - Nouvelles features visibles utilisateur
# - Nouvelles dépendances
# - Changements d'usage

# 3. Mettre à jour docs/ si nécessaire
# - Guides d'utilisation
# - Documentation technique

# 4. Commiter documentation
git add CHANGELOG.md README.md docs/
git commit -m "📝 Docs: Update documentation for nouvelle_feature"
```

**E. Vérification finale**:
```bash
# 1. Relire tous les commits
git log --oneline origin/master..HEAD

# 2. Vérifier qu'aucun fichier n'est oublié
git status

# 3. S'assurer que la branche est à jour
git fetch origin
git rebase origin/master  # Si conflits, les résoudre

# 4. Push de la feature branch
git push -u origin feature/task-name
```

### 4. Code Review Process

**IMPORTANT**: Toujours demander validation avant de merge

**Étapes**:
1. ✅ **Checklist "Avant de Créer la PR" complétée** (section 3)
2. ✅ Créer un résumé des changements pour l'utilisateur
3. ✅ **ATTENDRE VALIDATION** de l'utilisateur
4. ✅ Merger uniquement après approbation

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

### Tests de Régression (Bug Fix Tests)

**🔴 RÈGLE CRITIQUE**: Pour chaque bug remonté par l'utilisateur et corrigé, **TOUJOURS** créer un test automatisé qui vérifie que ce bug ne revient jamais.

**Workflow**:
1. ✅ L'utilisateur remonte un bug avec message d'erreur/logs
2. ✅ Analyser et corriger le bug
3. ✅ **OBLIGATOIRE**: Créer un test de régression qui reproduit le bug
4. ✅ Vérifier que le test échoue AVANT le fix (prouve qu'il détecte le bug)
5. ✅ Vérifier que le test passe APRÈS le fix
6. ✅ Committer le fix ET le test ensemble

**Exemple de test de régression**:
```python
def test_parse_all_champions_stats_dict_keys():
    """Regression test: stats dict must use 'success' key, not 'successful'.

    Bug: auto_update_db.py used stats.get('successful') but ParallelParser
    returned 'success', causing "0/172 succeeded" false reporting.

    Fixed in: PR #14 commit 980048d
    """
    db = Database(":memory:")
    db.connect()
    parser = ParallelParser(max_workers=1)

    # Mock minimal scraping
    stats = parser.parse_all_champions(db, normalize_champion_name_for_url)

    # Assert correct keys exist
    assert 'success' in stats, "stats dict must contain 'success' key"
    assert 'failed' in stats, "stats dict must contain 'failed' key"
    assert 'total' in stats, "stats dict must contain 'total' key"
    assert 'duration' in stats, "stats dict must contain 'duration' key"

    # Assert old incorrect key doesn't exist
    assert 'successful' not in stats, "stats dict must NOT contain 'successful' key (typo)"
```

**Bénéfices**:
- ✅ **Prévention**: Empêche régression du même bug
- ✅ **Documentation**: Le test documente le bug et sa correction
- ✅ **Confiance**: Garantit que les corrections restent valides
- ✅ **Refactoring safe**: Permet refactoring sans crainte de casser anciens fixes

**Localisation des tests**:
- Tests de régression → `tests/regression/` (nouveau dossier)
- Nommer fichiers: `test_regression_<issue_number>_<description>.py`
- Exemple: `test_regression_pr14_stats_dict_keys.py`

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

**Modules refactorisés (Sprint 1 ✅)**:
- `src/analysis/` - Algorithmes d'analyse (220 lignes max/fichier)
  - `scoring.py` - Calculs de scores et métriques
  - `tier_list.py` - Génération de tier lists
  - `team_analysis.py` - Analyse de composition d'équipe
  - `recommendations.py` - Système de recommandations
- `src/ui/` - Interface utilisateur modulaire
  - `menu_system.py` - Système de menus interactifs
  - `draft_coach_ui.py` - Interface draft coach
  - `lol_coach_legacy.py` - Legacy UI (backward compatibility)

**Web Scraping (Sprint 2 ✅)**:
- `src/parser.py` - Web scraping LoLalytics séquentiel (legacy)
- `src/parallel_parser.py` - **NOUVEAU** - Scraping parallèle (87% plus rapide) ✅
  - ThreadPoolExecutor avec 10 workers (optimisé i5-14600KF)
  - Retry automatique avec exponential backoff (tenacity)
  - Progress tracking avec tqdm
  - Thread-safe database writes avec locking
  - **Performance**: 90-120min → 12min (87% amélioration)

**Autres modules**:
- `src/db.py` - Database layer (sécurisé v1.0.1)
- `src/draft_monitor.py` - Real-time draft coach
- `src/pool_manager.py` - Champion pools CRUD
- `src/lcu_client.py` - League Client API

### Tests (Sprint 1 ✅)

- `tests/` - Framework pytest avec 89% coverage
  - `conftest.py` - Fixtures partagées (166 lignes)
  - `test_scoring.py` - 27 tests - 95% coverage
  - `test_tier_list.py` - 18 tests - 100% coverage
  - `test_team_analysis.py` - 13 tests - 97% coverage
  - `test_recommendations.py` - 16 tests - 65% coverage
- `test_db_fixes.py` - Tests sécurité + indexes (v1.0.1)

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

# Code formatting (Black) - OBLIGATOIRE avant chaque commit
python -m black src/ tests/              # Appliquer formatage automatique
python -m black --check --diff src/ tests/  # Vérifier formatage sans modifier

# Linting
pylint src/ --fail-under=8.0             # Quality score minimum 8.0/10
mypy src/ --ignore-missing-imports       # Type checking
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

1. ✅ **Feature branch DEPUIS MASTER** (`git checkout -b feature/name origin/master`)
2. ✅ **Commits atomiques** et fréquents
3. ✅ **Tests pour nouvelles fonctionnalités** (unitaires + intégration si besoin)
4. ✅ **Test de régression** pour chaque bug corrigé (OBLIGATOIRE)
5. ✅ **Tous les tests passent** avant PR (`pytest tests/ -v`)
6. ✅ **Formatage Black appliqué** avant PR (`python -m black src/ tests/`)
7. ✅ **Documentation mise à jour** (CHANGELOG.md, README.md, docs/)
8. ✅ **Code review** AVANT tout merge
9. ✅ **Validation utilisateur** explicite requise
10. ✅ **Requêtes SQL paramétrées** (sécurité)
11. ✅ **config_constants.py** pour valeurs hardcodées
12. ✅ **Type hints** sur fonctions publiques
13. ✅ **Docstrings** sur classes et méthodes
14. ✅ **Backward compatibility** lors refactoring

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
- [ ] Formatage Black appliqué (`python -m black src/ tests/`)
- [ ] Pas de valeurs hardcodées (utilise config_constants.py)
- [ ] Pas de SQL injection (requêtes paramétrées)
- [ ] Backward compatibility maintenue
- [ ] Documentation mise à jour (README, TODO, etc.)
- [ ] Code review template rempli complètement

---

## 🎯 Objectifs Long Terme

### ✅ Sprint 1 (Dette Technique) - COMPLÉTÉ (2025-12-16)
- [x] Tâche #1: Refactoring (<500 lignes/fichier) ✅
- [x] Tâche #3: Tests automatisés (89% couverture) ✅
- [x] Tâche #9: Database migrations (Alembic 1.17.2) ✅

### 🔴 Sprint 2 (Performance & Features) - EN COURS
- [x] Tâche #4: Web scraping parallèle ✅ **FAIT** (2025-12-20)
  - [x] Bug #1 fix: Cookie click dynamic detection
  - [x] ParallelParser implementation (10 workers)
  - [x] Retry mechanism avec tenacity
  - [x] **Performance**: 87% amélioration (12min vs 90-120min)
  - [x] Thread-safe database operations
  - [x] Real-time progress tracking
- [x] Tâche #11: Auto-Update BD (Service Windows) ✅ **FAIT** (2025-12-22)
  - [x] Script auto-update avec ParallelParser (12min)
  - [x] Task Scheduler setup wizard (PowerShell)
  - [x] Background execution (BELOW_NORMAL priority)
  - [x] Windows toast notifications
  - [x] Detailed logging system
  - [x] **Zero maintenance** - Daily automated updates (3 AM)
- [x] Restauration méthodes Assistant ✅ **FAIT** (2025-12-20)
  - [x] 24 méthodes manquantes restaurées
  - [x] Live podium display
  - [x] 54 méthodes total
- [ ] Tâche #5: Pool statistics viewer
- [ ] Tâche #14: Migration SQLAlchemy ORM (optionnel)
- [ ] Tâche #10: CI/CD Pipeline (GitHub Actions)

### Sprint 3+ (Features Avancées)
- [ ] Tâche #15: Support des Lanes (lane-specific matchups)
- [ ] Tâche #16: Support des Synergies (champion synergies)
- [ ] Tâche #6: GUI Desktop (tkinter/PyQt6)
- [ ] Tâche #7: Multi-plateformes (Linux/macOS)
- [ ] Tâche #8: Internationalisation (i18n)
- [ ] Tâche #12: Web App (optionnel)

---

## 🎮 Nouvelles Features Planifiées (Sprint 3+)

### Tâche #15: Support des Lanes (Lane-Specific Matchups)

**Objectif**: Améliorer la précision des recommandations en tenant compte de la lane du joueur.

**Problème actuel**: Les recommandations ignorent la lane, alors que les matchups varient fortement.
- Yasuo Mid vs Zed: Hard matchup
- Yasuo Top vs Malphite: Favorable matchup
- **Actuellement**: Même score → Imprécis ❌

**Solution**:
1. **Migration BDD**: Ajouter colonne `lane TEXT` nullable à table `matchups`
2. **Parsing multi-lanes**: Parser lanes avec pickrate > 10% (configurable)
3. **Détection lane**: Auto-détection via LCU API (`get_assigned_position()`)
4. **Lane priority**: Matchups même lane ont poids × 1.5 dans scoring
5. **Backward compat**: Données existantes (lane = NULL) restent utilisables

**Fichiers impactés** (10 fichiers):
- Parsing: `parser.py`, `parallel_parser.py`, `config_constants.py`
- Database: `db.py`, migration Alembic
- Scoring: `scoring.py`, `draft_monitor.py`, `lcu_client.py`
- Models: `models.py`
- Tests: `test_scoring.py`, `test_regression_lanes.py`

**Effort**: 3-4 jours | **ROI**: 1.00 (investissement structurant)

---

### Tâche #16: Support des Synergies (Champion Synergies)

**Objectif**: Intégrer bonus synergies avec alliés dans les recommandations.

**Problème actuel**: Recommandations ignorent team comp alliée.
- Malphite allié pick → Yasuo a bonus synergie (combo R)
- **Actuellement**: Ignoré → Sous-optimal ❌

**Solution**:
1. **Nouvelle table BDD**: `synergies` (structure identique `matchups`)
2. **Parsing synergies**: Cliquer bouton "Synergies" sur LoLalytics, même scrolling
3. **Intégration scoring**: `final_score = matchup_score + synergy_bonus`
4. **Backward compat**: Si pas de synergies → bonus = 0 (comportement actuel)

**Fichiers impactés** (10 fichiers):
- Parsing: `parser.py`, `parallel_parser.py`, `config_constants.py`
- Database: `db.py`, migration Alembic
- Scoring: `scoring.py`, `draft_monitor.py`
- Models: `models.py` (nouvelle dataclass `Synergy`)
- Tests: `test_scoring.py`, `test_regression_synergies.py`

**Effort**: 2 jours | **ROI**: 1.60 ⭐ (haute valeur)

---

### Ordre d'Implémentation Recommandé

**Séquentiel (recommandé)**:
1. ✅ Tâche #15 (Lanes) → Base pour synergies lane-specific
2. ✅ Tâche #16 (Synergies) → Peut bénéficier infrastructure lanes

**Justification**:
- Moins de conflits sur `scoring.py` et `db.py`
- Synergies peuvent être lane-specific si #15 déjà implémenté
- Tests plus simples (features isolées)

**Durée totale**: 5-6 jours (séquentiel)

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
