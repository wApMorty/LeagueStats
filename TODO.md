# TODO - League Stats Coach

## 🎯 Backlog Priorisé (Méthode Agile)

**Légende Scores Fibonacci**:
- **Plus-value**: 1 (minime) → 21 (critique pour le business)
- **Difficulté**: 1 (trivial) → 21 (très complexe)
- **ROI**: Plus-value / Difficulté (ratio bénéfice/effort)

---

## 📊 Vue d'Ensemble des Tâches

**⚠️ APPROCHE: Dette Technique First** - Prioriser qualité et maintenabilité

| # | Tâche | Plus-value | Difficulté | ROI | Priorité | Statut |
|---|-------|------------|------------|-----|----------|--------|
| **2** | **Extraction valeurs hardcodées** | **8** | **3** | **2.67** | 🔴 | ✅ **FAIT** |
| **4** | **Web Scraping parallèle** | **13** | **8** | **1.63** | 🟡 | ✅ **FAIT** |
| **11** | **Auto-Update BD (Service Windows)** | **13** | **8** | **1.63** | 🟡 | ✅ **FAIT** |
| **5** | **Pool Statistics Viewer** | **5** | **3** | **1.67** | 🟡 | ✅ **FAIT** |
| **10** | **CI/CD Pipeline** | **8** | **5** | **1.60** | 🟢 | ✅ **FAIT** |
| **1** | **Refactoring fichiers monolithiques** | **13** ⬆️ | **13** | **1.00** | 🔴🔴🔴 | ✅ **FAIT** |
| **3** | **Framework Tests Automatisés** | **13** | **13** | **1.00** | 🔴🔴 | ✅ **FAIT** |
| **9** | **Migrations Base de Données (Alembic)** | **8** ⬆️ | **5** | **1.60** | 🔴 | ✅ **FAIT** |
| **14** | **Migration Dataclass Immutables** | **5** | **5** | **1.00** | 🟡 | ✅ **FAIT** |
| **12** | **Architecture Client-Serveur + Web App** | **21** | **34** | **0.62** | 🟢 | ❌ |
| ~~**7**~~ | ~~**Support Multi-Plateformes**~~ | ~~**5**~~ | ~~**8**~~ | ~~**0.63**~~ | ~~🟢~~ | ❌ **ANNULÉE** |
| **6** | **Interface Graphique (GUI)** | **13** | **21** | **0.62** | 🟢 | ❌ |
| **8** | **Internationalisation (i18n)** | **3** | **5** | **0.60** | 🟢 | ❌ |

**⬆️ Changements scores (Dette Technique):**
- **Tâche #1**: Plus-value 8→**13** (base saine pour TOUTES futures tâches)
- **Tâche #9**: Plus-value 5→**8** (infrastructure BD critique, évite pertes données)

**Recommandation Sprint**: **Dette Technique First** → Refactoring + Tests + Migrations AVANT features

---

## 🔴 SPRINT 1 - Dette Technique ✅ COMPLÉTÉ (2025-12-16)

### ⭐ Tâche #2: Extraction des Valeurs Hardcodées
**Status**: ✅ **FAIT** (2025-11-27)
**Effort**: 1 jour (8h)

**Scores Fibonacci**:
- 📈 **Plus-value**: **8** (impact élevé sur maintenabilité)
- 🔧 **Difficulté**: **3** (facile - simple refactoring)
- 🎯 **ROI**: **2.67** ⭐ **QUICK WIN**

**Pourquoi ce score**:
- **Plus-value = 8**: Permet configuration user-editable, facilite debug, évite bugs hardcoded
- **Difficulté = 3**: Copier-coller de valeurs, pas de logique complexe

**Fichiers concernés**: `parser.py`, `assistant.py`, `draft_monitor.py`

**Valeurs à extraire**:

```python
# Créer: src/config_constants.py
from dataclasses import dataclass, field

@dataclass
class ScrapingConfig:
    COOKIE_BUTTON_DELAY: float = 0.3
    PAGE_LOAD_DELAY: int = 2
    SCRAPING_DELAY_BETWEEN_CHAMPIONS: int = 1
    RETRY_ATTEMPTS: int = 3
    TIMEOUT: int = 30

@dataclass
class AnalysisConfig:
    MIN_GAMES_THRESHOLD: int = 100
    MIN_PICKRATE_THRESHOLD: float = 0.5
    TIER_THRESHOLDS: dict = field(default_factory=lambda: {
        'S': 52, 'A': 50, 'B': 48, 'C': 46
    })

@dataclass
class DraftConfig:
    POLL_INTERVAL: float = 1.0
    AUTO_HOVER_DELAY: float = 0.5
    AUTO_BAN_ENABLED: bool = True

# Instances globales
scraping_config = ScrapingConfig()
analysis_config = AnalysisConfig()
draft_config = DraftConfig()
```

**Action**: Déplacer toutes ces valeurs dans `config.py` avec des classes dataclass.

**Bénéfices**:
- ✅ Configuration centralisée
- ✅ Valeurs modifiables sans toucher code
- ✅ Validation des types avec dataclass
- ✅ Documentation auto via IDE

---

### Tâche #1: Refactoring des Fichiers Monolithiques
**Status**: ✅ **FAIT** (2025-12-14) - PR #2 merged
**Effort**: 2 jours (15 commits)

**Scores Fibonacci**:
- 📈 **Plus-value**: **13** ⬆️ (dette technique - base saine pour TOUTES futures tâches)
- 🔧 **Difficulté**: **13** (complexe - risque de régression)
- 🎯 **ROI**: **1.00** (investissement nécessaire, approche Dette Technique First)

**Pourquoi ce score** (révisé pour Dette Technique First):
- **Plus-value = 13** (anciennement 8):
  - ✅ **Impact multiplicateur**: Facilite TOUTES les futures tâches (tests, features, refactoring)
  - ✅ **Évite dette composée**: Refactorer maintenant évite refactoring complexe plus tard
  - ✅ **Qualité long terme**: Navigation code, tests unitaires, onboarding, maintenabilité
  - ✅ **Fondation solide**: Partir de bases propres = moins de bugs, plus de vélocité
  - 📊 **Raisonnement**: Refactorer 2 jours MAINTENANT évite 5-10 jours de refactoring PLUS TARD
- **Difficulté = 13**: Touche beaucoup de code, risque régression, imports complexes, tests exhaustifs requis

**Problème**: `lol_coach.py` (2,160 lignes) et `assistant.py` (2,381 lignes) sont trop grands.

**✅ Architecture finale implémentée**:

```
src/
├── ui/
│   ├── __init__.py
│   ├── menu_system.py           # Système de menus principal (45 lignes)
│   ├── draft_coach_ui.py        # Interface draft coach (52 lignes)
│   ├── champion_data_ui.py      # Gestion données champions (105 lignes)
│   └── lol_coach_legacy.py      # Fonctions UI temporaires (2,159 lignes)
├── analysis/
│   ├── __init__.py
│   ├── scoring.py               # Algorithmes de score (216 lignes)
│   ├── tier_list.py             # Génération tier lists (91 lignes)
│   ├── team_analysis.py         # Analyse compositions (129 lignes)
│   └── recommendations.py       # Système recommandations (116 lignes)
├── utils/
│   ├── __init__.py
│   ├── display.py               # Fallback emoji Windows (30 lignes)
│   └── champion_utils.py        # Validation/sélection (220 lignes)
└── assistant.py                 # Coordinateur avec délégation (190 lignes)
```

**✅ Résultats obtenus**:
- ✅ `assistant.py`: 2,381 → 190 lignes (-92%)
- ✅ `lol_coach.py`: 2,159 → 215 lignes (-90%)
- ✅ Largest file: 2,381 → 220 lignes (-91%)
- ✅ 9 modules créés (analysis, ui, utils)
- ✅ 100% backward compatibility
- ✅ Tous tests passent
- ✅ 15 commits atomiques

**✅ Bénéfices réalisés**:
- ✅ Code plus navigable (<500 lignes/fichier)
- ✅ Architecture modulaire claire
- ✅ Facilite tests unitaires (Tâche #3)
- ✅ Base saine pour futures features

---

## 🟡 PRIORITÉ MOYENNE - Sprint 2 (2-3 semaines)

### ⭐ Tâche #4: Amélioration du Web Scraping
**Status**: ✅ **FAIT** (2025-12-20) - PR #5 merged
**Effort**: 2 jours (effectif)

**Scores Fibonacci**:
- 📈 **Plus-value**: **13** (gain temps utilisateur massif)
- 🔧 **Difficulté**: **8** (modéré - threading + retry logic)
- 🎯 **ROI**: **1.63** ⭐ **HAUTE VALEUR**

**Pourquoi ce score**:
- **Plus-value = 13**: Parsing 90-120min → 12min = **87% plus rapide** 🚀🚀🚀
- **Difficulté = 8**: ThreadPoolExecutor + tenacity retry + thread-safe DB

**✅ Résultat obtenu**:
- ✅ Parallel scraping avec ThreadPoolExecutor (10 workers)
- ✅ Parsing time: 90-120min → **12min** (87% amélioration)
- ✅ Dynamic cookie acceptance (Bug #1 fixé)
- ✅ Retry logic avec exponential backoff (tenacity)
- ✅ Thread-safe database writes avec locking
- ✅ Real-time progress tracking (tqdm)
- ✅ Komorebi fullscreen mode pour stabilité

**Implémentation réalisée**:

```python
# src/parallel_parser.py - IMPLÉMENTÉ ✅
from concurrent.futures import ThreadPoolExecutor
from tenacity import retry, stop_after_attempt, wait_exponential
import threading

class ParallelParser:
    """Parallel web scraping with 10 workers."""

    def __init__(self, max_workers=10, patch_version=None):
        self.max_workers = max_workers
        self.db_lock = threading.Lock()  # Thread-safe DB writes

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _scrape_with_retry(self, champion, lane):
        """Scrape with automatic retry."""
        parser = self.get_thread_local_parser()
        return parser.get_champion_data(champion, lane)

    def parse_all_champions(self, db, champions, normalize_fn):
        """Parse all champions in parallel with progress tracking."""
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(self._parse_champion, db, champ, normalize_fn)
                      for champ in champions]

            # Track progress with tqdm
            for future in tqdm(as_completed(futures), total=len(champions)):
                result = future.result()
```

**✅ Gains réalisés**:
- ⏱️ Temps: 90-120 min → **12 min** (87% réduction) 🎉
- 🐛 Bugs: Bug #1 corrigé (cookie acceptance dynamique)
- 🔄 Fiabilité: Retry automatique avec tenacity
- 🔒 Thread-safety: Database locking pour writes concurrents
- 📊 UX: Progress bars temps réel avec tqdm

**✅ Dépendances installées**: `tenacity` ajouté dans requirements.txt

---

### Tâche #3: Framework de Tests Automatisés
**Status**: ✅ **FAIT** (2025-12-16) - PR #3 merged
**Effort**: 3 jours (74 tests, 89% coverage)

**Scores Fibonacci**:
- 📈 **Plus-value**: **13** (qualité et confiance code)
- 🔧 **Difficulté**: **13** (complexe - couverture 70%+)
- 🎯 **ROI**: **1.00** (investissement nécessaire)

**Pourquoi ce score**:
- **Plus-value = 13**: Prévient régressions, facilite refactoring, confiance déploiement
- **Difficulté = 13**: Écrire 70% tests = beaucoup de code, mocks complexes

**✅ Résultat obtenu**: **5% → 89% couverture** (objectif 70%+ largement dépassé)

**✅ Structure implémentée**:

```
tests/
├── __init__.py
├── conftest.py                    # ✅ Fixtures pytest (DB, scorer, helpers)
├── test_scoring.py                # ✅ 27 tests - 95% coverage
├── test_tier_list.py              # ✅ 18 tests - 100% coverage
├── test_team_analysis.py          # ✅ 13 tests - 97% coverage
└── test_recommendations.py        # ✅ 16 tests - 65% coverage
```

**✅ Couverture obtenue** (module analysis):
1. ✅ **test_tier_list.py** - 100% coverage (45 statements, 0 missed)
2. ✅ **test_team_analysis.py** - 97% coverage (69 statements, 2 missed)
3. ✅ **test_scoring.py** - 95% coverage (82 statements, 4 missed)
4. ✅ **test_recommendations.py** - 65% coverage (60 statements, 21 missed - draft_simple legacy)

**Total**: **74 tests**, **89% coverage** du module analysis ✅

**Commandes**:
```bash
pip install pytest pytest-cov pytest-mock
pytest tests/ -v --cov=src --cov-report=html
open htmlcov/index.html  # Voir rapport couverture
```

**Exemple test scoring**:
```python
# tests/test_assistant_scoring.py
import pytest
from src.assistant import Assistant

@pytest.fixture
def assistant(tmp_path):
    """Fixture pour Assistant avec DB temporaire."""
    db_path = tmp_path / "test.db"
    return Assistant(db_path)

def test_calculate_counter_score_basic(assistant):
    """Test calcul score counter simple."""
    # Arrange
    enemy_delta2 = 2.5

    # Act
    score = assistant.calculate_counter_score(enemy_delta2)

    # Assert
    assert score > 50  # Champion favorable contre ennemi
    assert 0 <= score <= 100  # Score normalisé

def test_tier_list_thresholds(assistant):
    """Test que les seuils tier list sont corrects."""
    # Test qu'un champion avec 53% winrate → Tier S
    tier = assistant.calculate_tier(53.0)
    assert tier == 'S'
```

**Bénéfices**:
- ✅ Détection régressions automatique
- ✅ Refactoring en confiance
- ✅ Documentation vivante du code
- ✅ CI/CD possible

---

## ✅ SPRINT 2 - Performance & Features (COMPLÉTÉ - 2025-12-28)

### ⭐ Tâche #4: Web Scraping Parallèle
**Status**: ✅ **FAIT** (2025-12-20) - Commit 8be5c86
**Effort**: 1-2 jours (27 commits)

**Scores Fibonacci**:
- 📈 **Plus-value**: **13** (performance massive + débloque Tâche #11)
- 🔧 **Difficulté**: **8** (complexe - threading + retry + thread-safety)
- 🎯 **ROI**: **1.63** ⭐⭐ **HAUTE VALEUR**

**Pourquoi ce score**:
- **Plus-value = 13**: 85-90% amélioration performance, débloque auto-update BD (Tâche #11)
- **Difficulté = 8**: ThreadPoolExecutor, thread-safe DB writes, retry mechanism, window manager compatibility

**✅ Implémentation réalisée**:

**1. ParallelParser (src/parallel_parser.py)**:
- ThreadPoolExecutor avec 10 workers (optimisé i5-14600KF)
- Thread-local parser instances (1 Firefox par worker, pas par champion)
- Retry automatique avec exponential backoff (tenacity)
- Thread-safe database writes avec Lock
- Progress tracking avec tqdm

**2. Bug Fixes**:
- ✅ Bug #1: Cookie click dynamique (4 stratégies fallback)
- ✅ Komorebi compatibility: Fullscreen mode + 1s stabilization delay
- ✅ Thread-local parsers: 171 fenêtres → 10 fenêtres
- ✅ Alembic compatibility: create_riot_champions_table() au lieu de init_champion_table()
- ✅ sqlite_sequence error: Graceful handling avec try/except

**3. Méthodes restaurées (Assistant)**:
- ✅ 24 méthodes manquantes restaurées (draft(), competitive_draft(), find_optimal_trios_holistic(), etc.)
- ✅ calculate_global_scores() pour tier list après scraping
- ✅ Live podium display pour optimal duo finder (🥇🥈🥉)

**4. Configuration**:
- config_constants.py: DEFAULT_MAX_WORKERS = 10, FIREFOX_STARTUP_DELAY = 1.0s
- Patch version support: ParallelParser accepte patch_version parameter
- Automatic Riot API updates: Champions toujours à jour (172 champions)

**✅ Performance Results**:
```
Séquentiel (Parser):     90-120 minutes
Parallèle (ParallelParser): 12 minutes
Amélioration:            87% plus rapide
```

**✅ Architecture**:
```python
# src/parallel_parser.py
class ParallelParser:
    def __init__(self, db: Database, max_workers: int = 8, patch_version: str = None)
    def parse_all_champions() -> tuple[int, int, float]  # (success, failed, duration)
    def parse_champions_by_role(role: str) -> tuple[int, int, float]
    def close()  # Cleanup threads and drivers

# main.py - API publique
def parse_all_champions_parallel(patch_version: str = None) -> None
def parse_champions_by_role_parallel(role: str, patch_version: str = None) -> None
```

**✅ Bénéfices obtenus**:
- ✅ **87% amélioration performance** (90-120min → 12min)
- ✅ **10 workers** au lieu de 8 (optimisé i5-14600KF 20 threads)
- ✅ **Tâche #11 débloquée**: Auto-update BD maintenant viable (12min = acceptable en background)
- ✅ **Retry mechanism**: Resilient aux erreurs réseau/timeout
- ✅ **Thread-safe**: Database writes avec Lock
- ✅ **Progress tracking**: Real-time progress bars
- ✅ **Komorebi compatible**: Firefox en fullscreen mode

**✅ Impact sur Tâche #11**:
- ❌ **AVANT**: 90-120min de parsing = PC bloqué 2h = INACCEPTABLE
- ✅ **APRÈS**: 12min de parsing = Background acceptable = Tâche #11 DÉBLOQUÉE ✅

**Recommandation**: Passer à **Tâche #11** (Auto-Update BD) maintenant que le parsing est suffisamment rapide.

---

### ⭐ Tâche #5: Pool Statistics Viewer
**Status**: ✅ **FAIT** (2025-12-22) - PR #18 merged
**Effort**: 1 jour (effectif)

**Scores Fibonacci**:
- 📈 **Plus-value**: **5** (insight utile mais non critique)
- 🔧 **Difficulté**: **3** (facile - réutilise code existant)
- 🎯 **ROI**: **1.67** ⭐ **QUICK WIN**

**Pourquoi ce score**:
- **Plus-value = 5**: Utile pour debug tier lists, mais pas essentiel
- **Difficulté = 3**: Réutilise méthodes existantes d'Assistant

**Features**:
- Afficher avg_delta2, variance, coverage pour chaque champion
- Distribution metrics (min/max/mean/median) du pool
- Identifier outliers (champions avec données insuffisantes)
- Export vers CSV/JSON (optionnel)

**Intégration**: Pool Manager Menu

```
Pool Manager:
1. Create New Pool
2. Edit Existing Pool
3. Delete Pool
4. View Pool Statistics  ← NOUVEAU
5. Search Pools
6. Back
```

**Exemple affichage**:
```
=== Pool Statistics: TOP_SOLOQ_POOL ===

Champion Count: 43
Total Matchups: 1,547

Distribution:
- Avg Delta2: 0.85 (min: -2.1, max: 3.4)
- Variance: 1.24 (min: 0.3, max: 4.8)
- Coverage: 87% (min: 45%, max: 98%)

Top 5 Best Performers:
1. Aatrox     - Avg Delta2: 3.4
2. Camille    - Avg Delta2: 2.9
...

Champions with Low Data:
- Gwen        - Coverage: 45% (insufficient)
- K'Sante     - Coverage: 52% (borderline)
```

**Bénéfices**:
- ✅ Debug tier lists facilement
- ✅ Identifier champions à re-scraper
- ✅ Valider normalization ranges

---

### ⭐ Tâche #11: Automatisation Mise à Jour BD (Service Windows)
**Status**: ✅ **DÉBLOQUÉ** - Prêt à implémenter (Tâche #4 terminée)
**Effort**: 2-3 jours (16-24h)

**Scores Fibonacci**:
- 📈 **Plus-value**: **13** (BD toujours à jour automatiquement)
- 🔧 **Difficulté**: **8** (complexe - service Windows silencieux + scraping parallèle requis)
- 🎯 **ROI**: **1.63** ⭐⭐ **HAUTE VALEUR**

**Pourquoi ce score**:
- **Plus-value = 13**: BD à jour sans intervention manuelle = gain temps massif + données fraîches
- **Difficulté = 8**: Service Windows background + scraping parallèle (Tâche #4) + gestion ressources + processus silencieux non-bloquant

**✅ DÉPENDANCE SATISFAITE**: Tâche #4 (Web Scraping Parallèle) COMPLÉTÉE ✅
- ✅ **Avec parallélisation**: 12 min de parsing = **Processus background ACCEPTABLE** ✅
- ✅ **Ready to implement**: Toutes les dépendances sont satisfaites
- 🎯 **Recommandation**: Implémenter cette tâche maintenant (priorité haute)

**Problème actuel**:
- ❌ Mise à jour manuelle de la BD (parsing 30-60 min)
- ❌ Données potentiellement obsolètes entre patches
- ❌ Oublis de mise à jour avant tournois

**Solutions proposées**:

#### Option 1: Windows Service + Task Scheduler (Recommandé pour desktop)
**Complexité**: Moyenne | **Flexibilité**: Haute

**⚠️ IMPORTANT**: Simple Task Scheduler **N'EST PAS SUFFISANT** pour un processus silencieux.
- Task Scheduler = Exécution en foreground (bloque le PC pendant parsing)
- Windows Service = Exécution en background (ne bloque pas le PC)

**Solution recommandée**: Windows Service avec priorité BELOW_NORMAL + Task Scheduler pour trigger

```python
# scripts/auto_update_db.py
"""
Script automatisé de mise à jour BD.
S'exécute en arrière-plan sans bloquer le PC.
REQUIERT: Web scraping parallèle (Tâche #4) pour temps d'exécution < 10 min.
"""
import sys
import os
import psutil
from datetime import datetime
import json
from pathlib import Path

# Set process priority to BELOW_NORMAL to avoid blocking PC
try:
    p = psutil.Process(os.getpid())
    p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)  # Windows: priorité basse
except:
    pass  # Fallback if psutil not available

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import Database
from src.parser import Parser
from src.config import config, get_resource_path
from src.constants import SOLOQ_POOL

def send_notification(title, message):
    """Send Windows notification."""
    try:
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(title, message, duration=10, threaded=True)
    except:
        print(f"[NOTIFICATION] {title}: {message}")

def log_update(status, message):
    """Log update to file."""
    log_file = get_resource_path('logs/auto_update.log')
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    with open(log_file, 'a', encoding='utf-8') as f:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        f.write(f"[{timestamp}] {status}: {message}\n")

def check_patch_version():
    """Check if patch version changed on LoLalytics."""
    # Scrape current patch from LoLalytics
    # Compare with last known patch
    # Return True if new patch detected
    pass

def main():
    try:
        log_update("START", "Auto-update BD started")
        send_notification("LeagueStats Coach", "Mise à jour BD démarrée...")

        # 1. Check patch version
        new_patch = check_patch_version()
        if not new_patch:
            log_update("SKIP", "No new patch detected, skipping update")
            return

        # 2. Initialize DB and Parser
        db_path = get_resource_path('data/db.db')
        db = Database(db_path)
        db.connect()

        parser = Parser(db)

        # 3. Parse SOLOQ_POOL only (faster, ~5-10 min with parallel scraping)
        log_update("PROGRESS", f"Parsing {len(SOLOQ_POOL)} champions...")

        success_count = 0
        for i, champion in enumerate(SOLOQ_POOL):
            try:
                parser.parse_champion(champion, role='all')
                success_count += 1

                # Log progress every 10 champions
                if (i + 1) % 10 == 0:
                    log_update("PROGRESS", f"Parsed {i+1}/{len(SOLOQ_POOL)} champions")
            except Exception as e:
                log_update("ERROR", f"Failed to parse {champion}: {e}")

        # 4. Recalculate champion scores
        log_update("PROGRESS", "Recalculating champion scores...")
        # Call recalculate scores method

        db.close()

        # 5. Success notification
        log_update("SUCCESS", f"Update completed: {success_count}/{len(SOLOQ_POOL)} champions")
        send_notification(
            "LeagueStats Coach ✅",
            f"BD mise à jour avec succès!\n{success_count} champions parsés."
        )

    except Exception as e:
        log_update("FATAL", f"Update failed: {e}")
        send_notification(
            "LeagueStats Coach ❌",
            f"Échec mise à jour BD: {str(e)}"
        )
        sys.exit(1)

if __name__ == '__main__':
    main()
```

**Configuration: Priorité Process + Task Scheduler**:

**Étape 1: Script avec priorité basse** (déjà fait dans le code ci-dessus)
```python
# Le script définit automatiquement BELOW_NORMAL_PRIORITY_CLASS
# Cela permet au parsing de tourner en background sans ralentir le PC
```

**Étape 2: Task Scheduler avec options avancées**:
```powershell
# Créer tâche planifiée qui s'exécute tous les jours à 3h AM
$action = New-ScheduledTaskAction -Execute "pythonw.exe" `  # pythonw = pas de console visible
                                  -Argument "C:\path\to\scripts\auto_update_db.py"
$trigger = New-ScheduledTaskTrigger -Daily -At 3am
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -Priority 7  # Priorité basse (0=haute, 10=basse)

Register-ScheduledTask -TaskName "LeagueStats Auto-Update" `
                       -Action $action `
                       -Trigger $trigger `
                       -Settings $settings `
                       -Description "Mise à jour automatique BD LeagueStats (background)"
```

**Étape 3: Alternative - Windows Service (optionnel, plus complexe)**:
```python
# Pour transformer en vrai Windows Service (non-recommandé sauf besoin spécifique)
# Utiliser pywin32 ou NSSM (Non-Sucking Service Manager)
# NSSM est plus simple:
# nssm install LeagueStatsUpdater "C:\Python313\pythonw.exe" "C:\path\to\auto_update_db.py"
# nssm set LeagueStatsUpdater AppPriority BELOW_NORMAL_PRIORITY_CLASS
```

**Avantages**:
- ✅ Natif Windows, pas de serveur nécessaire
- ✅ Exécution locale, pas de coûts cloud
- ✅ Notifications desktop
- ✅ **Processus background silencieux** (avec pythonw + priorité basse)
- ✅ **Ne bloque PAS le PC** (si Tâche #4 implémentée: 6-8 min seulement)

**Inconvénients**:
- ❌ Nécessite PC allumé à l'heure planifiée
- ❌ Pas accessible à distance
- ⚠️ **REQUIERT Tâche #4** (sans parallélisation: 1h de parsing = bloquant)

---

#### Option 2: Serveur Cloud avec Cron (Pour déploiement permanent)
**Complexité**: Moyenne | **Flexibilité**: Élevée

**Architecture**:
```
VPS Cloud (AWS/DigitalOcean/OVH)
├── Ubuntu Server 22.04
├── Python 3.13 + dependencies
├── LeagueStats app
├── Cron job (quotidien à 3h AM UTC)
└── Base de données SQLite accessible via SFTP/API
```

**Cron Configuration**:
```bash
# /etc/cron.d/leaguestats-update
# Exécute mise à jour tous les jours à 3h AM
0 3 * * * leaguestats /usr/bin/python3 /opt/leaguestats/scripts/auto_update_db.py >> /var/log/leaguestats/update.log 2>&1
```

**Script avec notifications email**:
```python
# scripts/auto_update_db_server.py
import smtplib
from email.mime.text import MIMEText

def send_email_notification(subject, body):
    """Send email notification via SMTP."""
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = 'leaguestats@yourdomain.com'
    msg['To'] = 'your-email@gmail.com'

    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        server.starttls()
        server.login('your-email@gmail.com', 'app-password')
        server.send_message(msg)

# Reste du code similaire à Option 1
```

**Synchronisation BD**:
```bash
# Sur ta machine locale, télécharger BD mise à jour
rsync -avz user@your-server:/opt/leaguestats/data/db.db ./data/db.db

# Ou via script Python
import paramiko

def download_updated_db():
    """Download updated DB from server via SFTP."""
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.connect('your-server.com', username='user', key_filename='~/.ssh/id_rsa')

    sftp = ssh.open_sftp()
    sftp.get('/opt/leaguestats/data/db.db', './data/db.db')
    sftp.close()
    ssh.close()
```

**Coût**: ~5-10€/mois (VPS DigitalOcean Droplet 1GB RAM)

**Avantages**:
- ✅ Toujours actif, pas besoin PC allumé
- ✅ Accessible à distance (SFTP/API)
- ✅ Notifications email/SMS
- ✅ Logs centralisés

**Inconvénients**:
- ❌ Coût mensuel récurrent
- ❌ Configuration serveur requise

---

#### Option 3: GitHub Actions (Gratuit, Cloud)
**Complexité**: Faible | **Flexibilité**: Moyenne

**Workflow GitHub Actions**:
```yaml
# .github/workflows/auto-update-db.yml
name: Auto-Update Database

on:
  schedule:
    # Exécute tous les jours à 3h AM UTC
    - cron: '0 3 * * *'
  workflow_dispatch:  # Permet exécution manuelle

jobs:
  update-database:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.13'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          sudo apt-get install -y firefox-geckodriver

      - name: Run auto-update script
        run: python scripts/auto_update_db.py
        env:
          NOTIFICATION_EMAIL: ${{ secrets.NOTIFICATION_EMAIL }}

      - name: Upload updated database
        uses: actions/upload-artifact@v3
        with:
          name: database-${{ github.run_number }}
          path: data/db.db

      - name: Commit and push if changed
        run: |
          git config user.name "GitHub Actions Bot"
          git config user.email "actions@github.com"
          git add data/db.db
          git diff --quiet && git diff --staged --quiet || \
            (git commit -m "Auto-update: Database updated $(date)" && git push)
```

**Récupération BD**:
```bash
# Pull latest changes
git pull origin main

# Ou télécharger artifact depuis GitHub Actions UI
```

**Avantages**:
- ✅ **100% gratuit** pour repos publics
- ✅ Aucun serveur à maintenir
- ✅ Logs dans GitHub Actions
- ✅ Historique Git des mises à jour

**Inconvénients**:
- ❌ Limite 2000 min/mois (gratuit)
- ❌ Exécution plus lente (cold start)
- ❌ DB stockée dans Git (limite taille repo)

---

**Recommandation**:

| Cas d'usage | Solution recommandée | Raison |
|-------------|---------------------|--------|
| Usage personnel desktop | **Option 1: Task Scheduler + Background** | Simple, gratuit, local, silencieux |
| Team/Gaming House | **Option 2: VPS Cloud** | Toujours à jour, accessible tous |
| Open Source / Communauté | **Option 3: GitHub Actions** | Gratuit, transparent, versionné |

**Implémentation suggérée (Mix)**:
1. **REQUIS d'abord**: Tâche #4 (Web Scraping Parallèle) - 1-2 jours ⚡
2. **Court terme**: Option 1 (Task Scheduler + Background) - 2-3 jours
3. **Moyen terme**: Option 3 (GitHub Actions) - 0.5 jour (optionnel)
4. **Long terme**: Option 2 (VPS) si nécessaire - 1 jour (optionnel)

**⚠️ ORDRE OBLIGATOIRE**:
1. Implémenter Tâche #4 (parsing 30-60min → 6-8min)
2. Puis implémenter Tâche #11 (auto-update background)
3. Sinon: Tâche #11 bloquera le PC pendant 1h chaque jour ❌

**Bénéfices**:
- ✅ BD toujours à jour avec dernier patch
- ✅ Zéro intervention manuelle
- ✅ Notifications en cas d'échec
- ✅ Logs pour debugging
- ✅ Gain temps massif (30-60 min/semaine économisés)

---

### ⭐ Tâche #14: Migration vers Dataclasses Immutables
**Status**: ✅ **FAIT** (2025-12-29) - PR #22 merged
**Effort**: 2 jours (effectif)

**Scores Fibonacci**:
- 📈 **Plus-value**: **5** (type safety, lisibilité, maintenabilité)
- 🔧 **Difficulté**: **5** (refactoring complet + tests backward compat)
- 🎯 **ROI**: **1.00** (investissement architecture long terme)

**Pourquoi ce score**:
- **Plus-value = 5**: Type safety IDE, code lisible, immutabilité garantie, validation automatique
- **Difficulté = 5**: Migration complète du code analysis/, tests backward compat, migration assistant.py

**Problème initial**: Tuples nommés difficiles à maintenir (`matchup[1]` vs `matchup.winrate`)

**✅ Solution implémentée**: Dataclasses Python immutables

**Architecture réalisée**:
```python
# src/models.py - ✅ CRÉÉ
from dataclasses import dataclass

@dataclass(frozen=True)
class Matchup:
    """Immutable matchup data with validation."""
    enemy_name: str
    winrate: float
    delta1: float
    delta2: float
    pickrate: float
    games: int

    def __post_init__(self):
        # Validation automatique
        if not 0.0 <= self.winrate <= 100.0:
            raise ValueError(f"Invalid winrate: {self.winrate}")

@dataclass(frozen=True)
class MatchupDraft:
    """Lightweight draft matchup (4 fields vs 6)."""
    enemy_name: str
    delta2: float
    pickrate: float
    games: int

@dataclass(frozen=True)
class ChampionScore:
    """Champion performance metrics."""
    champion_id: int
    avg_delta2: float
    variance: float
    coverage: float
    peak_impact: float
    volatility: float
    target_ratio: float
```

**✅ Migration réalisée (18 commits)**:

**Phase 1 - Infrastructure** (3 commits):
- ✅ Création `src/models.py` avec 3 dataclasses
- ✅ Tests complets `tests/test_models.py` (389 lignes)
- ✅ Support dataclass dans `Database` (backward compatible)

**Phase 2 - Migration analysis/** (5 commits):
- ✅ `scoring.py`: `.winrate` au lieu de `[1]`
- ✅ `tier_list.py`: Attributs dataclass
- ✅ `recommendations.py`: Attributs dataclass
- ✅ `pool_statistics.py`: Migration complète
- ✅ Tests et fixtures mis à jour

**Phase 2.5 - Migration assistant.py** (2 commits):
- ✅ Backward compatibility config
- ✅ Refactoring complet (64 insertions, 77 suppressions)

**Phase 3 - Corrections & Tests** (5 commits):
- ✅ Fix `champion_utils.py`, `draft_monitor.py`
- ✅ Fix Live Coach conversion
- ✅ Fix post-draft analysis
- ✅ Tests backward compatibility (139 lignes)
- ✅ Documentation CHANGELOG.md

**Bonus - Optimisation** (3 commits):
- ✅ Holistic Optimizer: 1h06 → 20s (99.5% speedup)
- ✅ Cache matchups en mémoire (147K queries → 1)
- ✅ Fix messages index redondants

**✅ Résultats obtenus**:
- ✅ **Type safety**: IDE autocomplete + détection erreurs compilation
- ✅ **Lisibilité**: `matchup.winrate` vs `matchup[1]`
- ✅ **Immutabilité**: `frozen=True` prévient mutations accidentelles
- ✅ **Validation**: `__post_init__` valide données automatiquement
- ✅ **Backward compatible**: 100% des tests passent
- ✅ **Performance**: Bonus 99.5% speedup optimizer
- ✅ **Tests coverage**: 89% maintenu
- ✅ **19 commits propres**: Black formatted, CI/CD green

**✅ Bénéfices réalisés**:
- ✅ Code plus maintenable et lisible
- ✅ Détection bugs à la compilation (IDE)
- ✅ Prévention bugs de mutation
- ✅ Base saine pour futures features
- ✅ Documentation auto via type hints

---

## 🟢 PRIORITÉ BASSE - Sprint 3+ (1-2 mois)

### Tâche #10: CI/CD Pipeline
**Status**: ✅ **FAIT** (2025-12-28) - PR #20 en cours de merge
**Effort**: 1 jour (effectif)

**Scores Fibonacci**:
- 📈 **Plus-value**: **8** (automatisation, qualité)
- 🔧 **Difficulté**: **5** (modéré - config YAML)
- 🎯 **ROI**: **1.60** ⭐ **BONNE VALEUR**

**Pourquoi ce score**:
- **Plus-value = 8**: Tests auto, builds auto, détection bugs early
- **Difficulté = 5**: Config GitHub Actions + debugging pipeline

**Plateforme**: GitHub Actions

**Pipeline proposé**:
```yaml
# .github/workflows/ci.yml
name: LeagueStats Coach CI/CD

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Python 3.13
        uses: actions/setup-python@v4
        with:
          python-version: '3.13'

      - name: Install dependencies
        run: |
          pip install -r requirements-dev.txt

      - name: Run linting
        run: |
          pylint src/ --fail-under=8.0

      - name: Run tests
        run: |
          pytest tests/ --cov=src --cov-report=xml --cov-report=term

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml

  build:
    runs-on: windows-latest
    needs: test
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.13'

      - name: Build executable
        run: |
          pip install -r requirements-dev.txt
          python build_app.py

      - name: Create package
        run: python create_package.py

      - name: Upload artifact
        uses: actions/upload-artifact@v3
        with:
          name: LeagueStatsCoach-${{ github.sha }}
          path: LeagueStatsCoach_Portable.zip
```

**Bénéfices**:
- ✅ Tests automatiques à chaque commit
- ✅ Build automatique sur main
- ✅ Détection régressions immédiate
- ✅ Artefacts versionnés

---

### Tâche #9: Système de Migrations de Base de Données (Alembic)
**Status**: ✅ **FAIT** (2025-12-16) - PR #4 (en validation)
**Effort**: 1 jour (4 commits)

**Scores Fibonacci**:
- 📈 **Plus-value**: **8** ⬆️ (infrastructure BD critique - évite pertes données)
- 🔧 **Difficulté**: **5** (modéré - config Alembic)
- 🎯 **ROI**: **1.60** (dette technique infrastructure)

**Pourquoi ce score** (révisé pour Dette Technique First):
- **Plus-value = 8** (anciennement 5):
  - ✅ **Protection données**: Évite DROP TABLE = zéro perte de données utilisateur
  - ✅ **Infrastructure critique**: Base données = fondation app, doit être fiable
  - ✅ **Évolutivité**: Permet changements schéma sans migration manuelle douloureuse
  - ✅ **Professionnalisme**: Migrations = standard industrie, pratique obligatoire production
  - 📊 **Raisonnement**: Implémenter migrations MAINTENANT évite perte données catastrophique PLUS TARD
- **Difficulté = 5**: Config Alembic + écriture migrations initiales

**✅ Implémentation réalisée**:

```bash
# Installation
pip install alembic>=1.13.0,<2.0.0  # ✅ FAIT

# Configuration
alembic.ini configuré avec sqlite:///data/db.db  # ✅ FAIT
alembic/env.py avec schema SQLAlchemy metadata  # ✅ FAIT

# Migration initiale
python -m alembic revision -m "Initial schema"  # ✅ FAIT
# Créé: alembic/versions/2124c2bc4262_initial_database_schema...py

# Tests validés
python -m alembic upgrade head      # ✅ OK - 3 tables + 6 indexes
python -m alembic downgrade base    # ✅ OK - Drop tables/indexes
python -m alembic current           # ✅ OK - 2124c2bc4262 (head)
```

**✅ Schema migré** (3 tables + 6 indexes):
- **champions**: id, key, name, title, created_at, updated_at
- **matchups**: id, champion, enemy, winrate, delta1, delta2, pickrate, games
- **champion_scores**: id, avg_delta2, variance, coverage, peak_impact, volatility, target_ratio
- **Indexes**: idx_champions_name + 5 matchups indexes (performance)

**✅ Résultats obtenus**:
- ✅ Alembic 1.17.2 installé et configuré
- ✅ Migration initiale (2124c2bc4262) créée et testée
- ✅ Migrations up/down validées (backup-safe)
- ✅ Documentation complète dans CLAUDE.md
- ✅ Corrections Copilot appliquées (sa.text(), drop indexes explicites)

**✅ Bénéfices réalisés**:
- ✅ Migrations réversibles et versionnées
- ✅ Historique changements schéma trackés
- ✅ Protection contre perte données (pas de DROP TABLE manuel)
- ✅ Autogenerate possible (si SQLAlchemy ORM ajouté)

---

### Tâche #6: Interface Graphique (GUI)
**Status**: ❌ Not started
**Effort**: 1-2 semaines (40-80h)

**Scores Fibonacci**:
- 📈 **Plus-value**: **13** (UX massif, accessibilité)
- 🔧 **Difficulté**: **21** (très complexe - nouveau paradigme)
- 🎯 **ROI**: **0.62** (faible ROI, gros effort)

**Pourquoi ce score**:
- **Plus-value = 13**: Amélioration UX massive, attire users non-tech
- **Difficulté = 21**: Nouveau paradigme UI, event-driven, layout complexe

**Options**:
- **Option 1**: `tkinter` (léger, inclus Python, courbe apprentissage faible)
- **Option 2**: `PyQt6` (moderne, professionnel, mais complexe)
- **Option 3**: Web UI (`Flask` + React/Vue, accessible depuis navigateur)

**Recommandation**: Commencer avec **tkinter** pour prototype rapide.

**Exemple prototype tkinter**:
```python
import tkinter as tk
from tkinter import ttk

class LeagueStatsGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("LeagueStats Coach")
        self.root.geometry("800x600")

        # Menu bar
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # Draft Coach Tab
        draft_frame = ttk.Frame(self.root)
        draft_frame.pack(fill='both', expand=True)

        # Role selection
        ttk.Label(draft_frame, text="Select Role:").pack()
        role_var = tk.StringVar()
        roles = ['Top', 'Jungle', 'Mid', 'ADC', 'Support']
        ttk.Combobox(draft_frame, textvariable=role_var, values=roles).pack()

        # Recommendations display
        rec_text = tk.Text(draft_frame, height=20)
        rec_text.pack()

    def run(self):
        self.root.mainloop()

if __name__ == '__main__':
    app = LeagueStatsGUI()
    app.run()
```

**⚠️ Note**: Gros investissement, à faire **après** stabilisation du backend.

---

### ~~Tâche #7: Support Multi-Plateformes~~ ❌ **ANNULÉE**
**Status**: ❌ **ANNULÉE** (2025-12-29)
**Raison**: Non pertinente - Efforts disproportionnés par rapport à la valeur réelle

**Scores Fibonacci** (initiaux):
- 📈 **Plus-value**: **5** (portabilité, mais users Windows majoritaires)
- 🔧 **Difficulté**: **8** (modéré - tests sur chaque OS)
- 🎯 **ROI**: **0.63**

**Pourquoi annulée**:

1. **League of Legends est Windows-only**
   - Le client LoL officiel ne tourne pas sur Linux/macOS
   - La feature principale (LCU draft monitor) est donc Windows-only par design
   - Même avec un code portable, l'utilisation principale reste limitée à Windows

2. **Le code est déjà majoritairement portable**
   - Python 3.13+, SQLite, Selenium sont cross-platform par nature
   - Les parties analyse/tier lists/optimizer fonctionnent déjà sur Linux
   - Seules les features liées au client LoL nécessitent Windows

3. **Chemins hardcodés sont une pratique acceptable**
   - Valeurs par défaut raisonnables dans `config.py`
   - Overridables par variables d'environnement (`FIREFOX_PATH`, `BRAVE_PATH`)
   - Chemins d'installation standard et documentés
   - Pragmatique pour 99% des utilisateurs

4. **Population utilisateur LoL = Windows**
   - Quasi-totalité des joueurs LoL sur Windows
   - Marché Linux/macOS pour LoL négligeable
   - Effort de portage ne correspond pas à la demande

**Conclusion**:
Tâche **surévaluée** et **non pertinente** - Le projet est déjà suffisamment portable pour les cas d'usage réels. Les quelques spécificités Windows sont justifiées par le contexte (client LoL Windows-only)

---

### Tâche #8: Internationalisation (i18n)
**Status**: ❌ Not started
**Effort**: 1-2 jours (8-16h)

**Scores Fibonacci**:
- 📈 **Plus-value**: **3** (accessibilité, mais users FR/EN déjà couverts)
- 🔧 **Difficulté**: **5** (modéré - extraction strings)
- 🎯 **ROI**: **0.60**

**Pourquoi ce score**:
- **Plus-value = 3**: Nice to have, mais pas critique (code déjà en FR/EN mixte)
- **Difficulté = 5**: Extraction toutes les strings, gestion fichiers .po

**Langues cibles**: Français, Anglais

**Méthode**: Utiliser `gettext`

```python
import gettext

# Setup
locale_dir = 'locales'
lang = 'fr'  # ou 'en'
translation = gettext.translation('app', locale_dir, languages=[lang])
translation.install()
_ = translation.gettext

# Usage dans le code
print(_("Welcome to LeagueStats Coach"))
print(_("Select your role:"))
```

**Structure fichiers**:
```
locales/
├── fr/
│   └── LC_MESSAGES/
│       ├── app.po   # Fichier source (éditable)
│       └── app.mo   # Fichier compilé
└── en/
    └── LC_MESSAGES/
        ├── app.po
        └── app.mo
```

**Commandes**:
```bash
# Extraire strings
xgettext -o locales/app.pot src/*.py

# Compiler .po → .mo
msgfmt locales/fr/LC_MESSAGES/app.po -o locales/fr/LC_MESSAGES/app.mo
```

---

### Tâche #12: Architecture Client-Serveur + Web App
**Status**: ❌ Not started
**Effort**: 2-3 semaines (80-120h)

**Scores Fibonacci**:
- 📈 **Plus-value**: **21** (révolution UX + BD centralisée)
- 🔧 **Difficulté**: **34** (très complexe - full-stack + déploiement)
- 🎯 **ROI**: **0.62** (gros investissement, gains à long terme)

**Pourquoi ce score**:
- **Plus-value = 21**: Accès distant BD, multi-users, web UI moderne, toujours à jour
- **Difficulté = 34**: Backend API + Frontend React + Base données PostgreSQL + Déploiement cloud + Auth

**Vision**: Transformer LeagueStats en **SaaS accessible depuis navigateur**

---

#### Architecture Proposée

```
┌─────────────────────────────────────────────────────────┐
│                    UTILISATEURS                          │
│  Desktop PC │ Laptop │ Tablette │ Smartphone             │
└─────────────────┬───────────────────────────────────────┘
                  │ HTTPS
                  ▼
┌─────────────────────────────────────────────────────────┐
│              WEB APP (React/Vue/Svelte)                  │
│  ┌──────────────┬──────────────┬──────────────────────┐ │
│  │ Draft Coach  │ Tier Lists   │ Champion Pools       │ │
│  │ Real-time UI │ Visualisation│ Gestion Pools        │ │
│  └──────────────┴──────────────┴──────────────────────┘ │
└─────────────────┬───────────────────────────────────────┘
                  │ REST API / GraphQL / WebSocket
                  ▼
┌─────────────────────────────────────────────────────────┐
│           BACKEND API (FastAPI / Flask)                  │
│  ┌──────────────┬──────────────┬──────────────────────┐ │
│  │ Auth JWT     │ API Endpoints│ WebSocket Server     │ │
│  │ Rate Limiting│ Caching Redis│ Background Tasks     │ │
│  └──────────────┴──────────────┴──────────────────────┘ │
│                                                           │
│  ┌──────────────────────────────────────────────────┐   │
│  │          Core Logic (Python)                      │   │
│  │  - Assistant (algorithmes scoring)                │   │
│  │  - Parser (web scraping)                          │   │
│  │  - Pool Manager                                   │   │
│  │  - LCU Client (pour draft real-time)             │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────┬───────────────────────────────────────┘
                  │ SQL / ORM (SQLAlchemy)
                  ▼
┌─────────────────────────────────────────────────────────┐
│      BASE DE DONNÉES (PostgreSQL / MySQL)                │
│  ┌──────────────┬──────────────┬──────────────────────┐ │
│  │ champions    │ matchups     │ users                │ │
│  │ pools        │ drafts       │ subscriptions        │ │
│  └──────────────┴──────────────┴──────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

#### Stack Technologique Recommandée

**Backend**:
- **Framework**: FastAPI (moderne, async, auto-docs)
- **ORM**: SQLAlchemy (migration depuis SQLite facile)
- **Database**: PostgreSQL 15+ (production) / SQLite (dev)
- **Cache**: Redis (optionnel, pour tier lists)
- **Auth**: JWT avec refresh tokens
- **Background Jobs**: Celery + Redis (parsing automatique)
- **WebSocket**: FastAPI WebSocket (draft real-time)

**Frontend**:
- **Framework**: React 18 + TypeScript
  - Alternative: Vue 3 / Svelte (plus simple)
- **UI Library**: shadcn/ui ou Material-UI
- **State Management**: Zustand / Redux Toolkit
- **API Client**: React Query (caching auto)
- **WebSocket**: Socket.io-client
- **Build**: Vite (rapide)

**Infrastructure**:
- **Hosting Backend**: Railway / Render / DigitalOcean App Platform
- **Hosting Frontend**: Vercel / Netlify (gratuit!)
- **Database**: Railway PostgreSQL / Supabase (gratuit tier)
- **CDN**: Cloudflare (gratuit)
- **Monitoring**: Sentry (erreurs) + Plausible (analytics)

**Coût estimé**: 0-15€/mois (gratuit avec tiers gratuits)

---

#### Étapes d'Implémentation

**Phase 1: Backend API (1 semaine)**

```python
# backend/main.py - FastAPI setup
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import uvicorn

app = FastAPI(title="LeagueStats API", version="2.0")

# CORS pour accès depuis web app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://leaguestats.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes API
@app.get("/api/v1/champions")
async def get_champions(db: Session = Depends(get_db)):
    """Get all champions."""
    champions = db.query(Champion).all()
    return {"champions": [ChampionSchema.from_orm(c) for c in champions]}

@app.get("/api/v1/champions/{champion_id}/matchups")
async def get_champion_matchups(champion_id: int, db: Session = Depends(get_db)):
    """Get matchups for a champion."""
    matchups = db.query(Matchup).filter(Matchup.champion_id == champion_id).all()
    return {"matchups": [MatchupSchema.from_orm(m) for m in matchups]}

@app.post("/api/v1/pools")
async def create_pool(
    pool: PoolCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new champion pool."""
    new_pool = Pool(**pool.dict(), user_id=current_user.id)
    db.add(new_pool)
    db.commit()
    return {"pool": PoolSchema.from_orm(new_pool)}

@app.get("/api/v1/tierlist/{role}")
async def get_tierlist(role: str, pool_id: Optional[int] = None):
    """Generate tier list for role."""
    assistant = Assistant()
    tierlist = assistant.generate_tierlist(role, pool_id)
    return {"tierlist": tierlist}

# WebSocket pour draft real-time
@app.websocket("/ws/draft/{draft_id}")
async def draft_websocket(websocket: WebSocket, draft_id: str):
    await websocket.accept()
    # Stream draft updates en temps réel
    draft_monitor = DraftMonitor()
    async for update in draft_monitor.stream_updates():
        await websocket.send_json(update)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**Endpoints API** (exemples):
```
GET    /api/v1/champions                  # Liste champions
GET    /api/v1/champions/{id}/matchups    # Matchups champion
POST   /api/v1/pools                      # Créer pool
GET    /api/v1/pools/{id}                 # Détails pool
GET    /api/v1/tierlist/{role}            # Tier list
POST   /api/v1/auth/register              # Inscription
POST   /api/v1/auth/login                 # Connexion
WS     /ws/draft/{id}                     # Draft real-time
```

---

**Phase 2: Migration Base de Données (2-3 jours)**

```python
# backend/models.py - SQLAlchemy models
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class Champion(Base):
    __tablename__ = "champions"

    id = Column(Integer, primary_key=True)
    key = Column(String(50), unique=True)  # "Aatrox"
    name = Column(String(100))
    title = Column(String(200))
    matchups = relationship("Matchup", back_populates="champion")

class Matchup(Base):
    __tablename__ = "matchups"

    id = Column(Integer, primary_key=True)
    champion_id = Column(Integer, ForeignKey("champions.id"))
    enemy_id = Column(Integer, ForeignKey("champions.id"))
    winrate = Column(Float)
    delta1 = Column(Float)
    delta2 = Column(Float)
    pickrate = Column(Float)
    games = Column(Integer)

    champion = relationship("Champion", foreign_keys=[champion_id])
    enemy = relationship("Champion", foreign_keys=[enemy_id])

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True)
    password_hash = Column(String(255))
    created_at = Column(DateTime)
    pools = relationship("Pool", back_populates="user")

class Pool(Base):
    __tablename__ = "pools"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String(100))
    description = Column(String(500))
    champions = Column(JSON)  # Liste IDs champions

    user = relationship("User", back_populates="pools")
```

**Migration SQLite → PostgreSQL**:
```bash
# Export SQLite
sqlite3 data/db.db .dump > dump.sql

# Import PostgreSQL
psql -U postgres -d leaguestats < dump.sql

# Ou via script Python
import sqlite3
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Read from SQLite
sqlite_conn = sqlite3.connect('data/db.db')
sqlite_cursor = sqlite_conn.cursor()
sqlite_cursor.execute("SELECT * FROM champions")
champions = sqlite_cursor.fetchall()

# Write to PostgreSQL
pg_engine = create_engine('postgresql://user:pass@localhost/leaguestats')
Session = sessionmaker(bind=pg_engine)
session = Session()

for champ in champions:
    new_champ = Champion(id=champ[0], name=champ[1], ...)
    session.add(new_champ)

session.commit()
```

---

**Phase 3: Frontend React (1 semaine)**

```typescript
// frontend/src/App.tsx - React app structure
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from 'react-query'
import { DraftCoach } from './pages/DraftCoach'
import { TierLists } from './pages/TierLists'
import { PoolManager } from './pages/PoolManager'
import { Login } from './pages/Login'

const queryClient = new QueryClient()

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<DraftCoach />} />
          <Route path="/tierlists" element={<TierLists />} />
          <Route path="/pools" element={<PoolManager />} />
          <Route path="/login" element={<Login />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

// frontend/src/components/TierListDisplay.tsx
import { useQuery } from 'react-query'
import { fetchTierList } from '../api/client'

export function TierListDisplay({ role }: { role: string }) {
  const { data, isLoading } = useQuery(['tierlist', role], () =>
    fetchTierList(role)
  )

  if (isLoading) return <div>Loading tier list...</div>

  return (
    <div className="tier-list">
      {['S', 'A', 'B', 'C'].map(tier => (
        <div key={tier} className="tier-row">
          <h3>{tier} Tier</h3>
          <div className="champions">
            {data.tierlist[tier].map(champ => (
              <ChampionCard key={champ.id} champion={champ} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

// frontend/src/hooks/useDraftWebSocket.ts
import { useEffect, useState } from 'react'

export function useDraftWebSocket(draftId: string) {
  const [recommendations, setRecommendations] = useState([])

  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8000/ws/draft/${draftId}`)

    ws.onmessage = (event) => {
      const update = JSON.parse(event.data)
      setRecommendations(update.recommendations)
    }

    return () => ws.close()
  }, [draftId])

  return recommendations
}
```

---

**Phase 4: Déploiement (2-3 jours)**

**Option 1: Railway (Recommandé - Simple)**
```bash
# Deploy backend + PostgreSQL en 1 clic
railway login
railway init
railway up

# Variables d'environnement auto-configurées
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
```

**Option 2: DigitalOcean App Platform**
```yaml
# app.yaml
name: leaguestats
services:
  - name: api
    github:
      repo: username/leaguestats
      branch: main
    build_command: pip install -r requirements.txt
    run_command: uvicorn main:app --host 0.0.0.0 --port 8000
    envs:
      - key: DATABASE_URL
        scope: RUN_AND_BUILD_TIME
        value: ${db.DATABASE_URL}

databases:
  - name: db
    engine: PG
    version: "15"
```

**Frontend déployé sur Vercel**:
```bash
cd frontend
vercel --prod
# Auto-deploy à chaque push sur main
```

---

#### Features Clés Web App

1. **Draft Coach Real-Time**
   - WebSocket connection vers LCU
   - Affichage top 3 recommandations live
   - Historique drafts sauvegardés
   - Partage draft via URL

2. **Tier Lists Interactives**
   - Filtrage par rôle
   - Tri par métrique (winrate, delta2, etc.)
   - Comparaison multiple pools
   - Export PNG/PDF

3. **Pool Manager Cloud**
   - Sync automatique entre devices
   - Partage pools avec équipe
   - Import/Export JSON
   - Tags et catégories

4. **Dashboard Analytics**
   - Statistiques d'utilisation
   - Champions populaires
   - Trends patch par patch
   - Suggestions personnalisées

5. **Authentification & Comptes**
   - Inscription/Connexion
   - Profils utilisateurs
   - Favoris et historique
   - Plans gratuit/premium (optionnel)

---

#### Avantages Architecture Client-Serveur

✅ **Utilisateur**:
- Accès depuis n'importe quel device
- Pas d'installation requise
- BD toujours à jour (serveur scrape auto)
- Synchronisation multi-devices
- Interface moderne et réactive

✅ **Développement**:
- Backend Python réutilisé (Assistant, Parser)
- API testable facilement
- Scalabilité (Redis cache, load balancing)
- Monitoring et analytics intégrés
- CI/CD simple (auto-deploy)

✅ **Business** (si monetization future):
- Modèle SaaS (abonnements)
- Freemium (tier gratuit + premium)
- Analytics utilisateurs
- A/B testing facile

---

#### Inconvénients & Défis

❌ **Complexité**:
- Full-stack développement
- DevOps et déploiement
- Sécurité (auth, CORS, rate limiting)
- Coûts cloud récurrents (même minimes)

❌ **Maintenance**:
- Serveur à surveiller 24/7
- Backups BD réguliers
- Gestion utilisateurs
- Support utilisateurs potentiels

---

#### Timeline & Roadmap

**MVP (4 semaines)**:
- Semaine 1: Backend API (FastAPI) + Migration BD
- Semaine 2: Frontend React (pages principales)
- Semaine 3: Features core (Draft, Tier Lists, Pools)
- Semaine 4: Déploiement + Tests

**Version 1.0 (2 mois)**:
- MVP + Auth utilisateurs
- WebSocket draft real-time
- Amélioration UI/UX
- Tests et optimisations

**Version 2.0 (3-4 mois)**:
- Dashboard analytics
- Partage social
- Mobile responsive
- Premium features (optionnel)

---

#### ROI & Décision

**Investissement**: 80-120h (2-3 semaines full-time)

**Retour**:
- **Court terme**: Application moderne accessible partout
- **Moyen terme**: Base utilisateurs potentielle élargie
- **Long terme**: Monétisation possible (SaaS)

**Recommandation**:
- **Si usage perso/petit groupe**: Pas nécessaire (desktop app suffit)
- **Si ambition communauté/open-source**: Excellente idée
- **Si Gaming House/équipe pro**: Très utile (accès centralisé)

---

**Dépendances requises**:
- Tâche #4 (Web Scraping parallèle) - Parsing auto serveur
- Tâche #3 (Tests) - API testée avant production
- Tâche #10 (CI/CD) - Déploiement automatisé

**Bénéfices**:
- ✅ Accès BD distant depuis navigateur
- ✅ Multi-users avec authentification
- ✅ BD centralisée toujours à jour
- ✅ Interface moderne et réactive
- ✅ Scalable et maintenable
- ✅ Potentiel monétisation future

---

## 📊 Matrice de Décision

### Quick Wins (ROI élevé) 🎯 - ✅ COMPLÉTÉ

| Tâche | Plus-value | Difficulté | ROI | Temps | Statut |
|-------|------------|------------|-----|-------|--------|
| #2 Extraction hardcoded | 8 | 3 | **2.67** | 1 jour | ✅ **FAIT** |
| #5 Pool Statistics | 5 | 3 | **1.67** | 1 jour | ✅ **FAIT** |
| #11 Auto-Update BD (Service) | 13 | 8 | **1.63** | 2-3 jours | ✅ **FAIT** |
| #4 Web Scraping parallèle | 13 | 8 | **1.63** | 1-2 jours | ✅ **FAIT** |
| #9 Migrations BD | 8 ⬆️ | 5 | **1.60** | 1 jour | ✅ **FAIT** |
| #10 CI/CD | 8 | 5 | **1.60** | 1 jour | ✅ **FAIT** |

**🎉 TOUS LES QUICK WINS COMPLÉTÉS !** (6/6 tâches - ~8 jours investis)
**Impact**: Parsing 87% plus rapide, BD auto-update quotidien, Tests automatisés (89%), CI/CD opérationnel

---

### Dette Technique (Approche "Dette Technique First") 🔴🔴🔴

**Philosophie**: Investir dans la qualité MAINTENANT pour éviter refactoring complexe PLUS TARD

| Tâche | Plus-value | Difficulté | ROI | Temps | Priorité |
|-------|------------|------------|-----|-------|----------|
| #1 Refactoring fichiers | 13 ⬆️ | 13 | **1.00** | 2-3 jours | 🔴🔴🔴 **NEXT** |
| #3 Tests Automatisés | 13 | 13 | **1.00** | 3-5 jours | 🔴🔴 |
| #9 Migrations BD | 8 ⬆️ | 5 | **1.60** | 1 jour | 🔴 |

**Approche recommandée**: Dette Technique → Refactoring + Tests + Migrations **AVANT** features
**Total**: 6-9 jours pour fondations solides et maintenabilité long terme
**Impact**: Base saine = vélocité élevée pour TOUTES futures tâches

---

### Gros Chantiers (Faire après stabilisation)

| Tâche | Plus-value | Difficulté | ROI | Temps |
|-------|------------|------------|-----|-------|
| #7 Multi-plateformes | 5 | 8 | 0.63 | 2-3 jours |
| #6 GUI Desktop | 13 | 21 | 0.62 | 1-2 semaines |
| #12 Web App (Client-Serveur) | 21 | 34 | 0.62 | 2-3 semaines |
| #8 i18n | 3 | 5 | 0.60 | 1-2 jours |

**Total**: 3-5 semaines - À faire en Phase 3+ (après Dette Technique résolue)

---

## 🎯 Sprint Planning Recommandé (Dette Technique First)

### ✅ Sprint 0 (COMPLÉTÉ): Configuration Foundation
**Objectif**: Bases configurables et maintenables

- [x] #2 Extraction hardcoded values (1j) - ROI 2.67 ✅ **FAIT**
- [x] Bug #2 fix (parser.py SyntaxWarning) (0.1j) ✅ **FAIT**

**Total**: 1 jour ✅
**Résultat**: Code configurable, type-safe, IDE-documented, backward compatible

---

### ✅ Sprint 1 (COMPLÉTÉ - 2025-12-16): Dette Technique First
**Objectif**: Fondations solides avant features
**Philosophie**: Refactoring + Infrastructure + Tests MAINTENANT = Vélocité élevée APRÈS

**Tâches complétées**:
- [x] **#1 Refactoring fichiers monolithiques** (2-3j) - ROI 1.00 ✅ **FAIT (PR #2)**
  - ✅ `lol_coach.py` (2,160 lignes) → `src/ui/` modules (215 lignes)
  - ✅ `assistant.py` (2,381 lignes) → `src/analysis/` modules (190 lignes)
  - ✅ Objectif <500 lignes/fichier atteint
  - ✅ 9 modules créés (analysis, ui, utils)
  - ✅ 100% backward compatibility

- [x] **#3 Framework Tests Automatisés** (3j) - ROI 1.00 ✅ **FAIT (PR #3)**
  - ✅ Setup pytest + pytest-cov + pytest-mock
  - ✅ 74 tests créés (scoring, tier list, team analysis, recommendations)
  - ✅ **89% couverture** (objectif 70%+ largement dépassé !)
  - ✅ test_tier_list.py: 100% coverage
  - ✅ test_team_analysis.py: 97% coverage
  - ✅ test_scoring.py: 95% coverage

- [x] **#9 Migrations Base de Données Alembic** (1j) - ROI 1.60 ✅ **FAIT (PR #4)**
  - ✅ Alembic 1.17.2 installé et configuré
  - ✅ Migration initiale (2124c2bc4262) créée
  - ✅ 3 tables + 6 indexes migrés
  - ✅ Tests up/down validés
  - ✅ Documentation CLAUDE.md complète
  - ✅ Corrections Copilot appliquées

**Total**: 6 jours effectifs ✅
**Résultat**:
- ✅ Code maintenable (fichiers <500 lignes)
- ✅ Tests automatiques (89% coverage)
- ✅ Migrations versionnées (Alembic)
- ✅ Configuration centralisée (config_constants.py)

**Impact réalisé**: Base saine établie pour TOUS futurs développements ! 🎉

---

### ✅ Sprint 2 (COMPLÉTÉ - 2025-12-28): Performance & Features
**Objectif**: Gains utilisateur rapides (après fondations solides)

**Tâches complétées**:
1. [x] **#4 Web Scraping parallèle** (2j) - ROI 1.63 ⚡ **FAIT** ✅
   - ✅ ThreadPoolExecutor avec 10 workers
   - ✅ Retry logic avec exponential backoff (tenacity)
   - ✅ Parsing 90-120 min → 12 min (87% amélioration) 🎉
   - ✅ Thread-safe database writes
   - ✅ Real-time progress tracking (tqdm)
   - ✅ Dynamic cookie acceptance (Bug #1 fixé)

2. [x] **#11 Auto-Update BD (Service Windows)** (2-3j) - ROI 1.63 ✅ **FAIT**
   - ✅ Windows Service avec priorité BELOW_NORMAL
   - ✅ Processus background silencieux
   - ✅ Notifications Windows Toast
   - ✅ Task Scheduler setup wizard
   - ✅ Zero maintenance - Daily automated updates (3 AM)

3. [x] **#5 Pool Statistics Viewer** (1j) - ROI 1.67 ✅ **FAIT**
   - ✅ Affichage stats détaillées pools
   - ✅ Integrated in Pool Manager menu

4. [x] **#10 CI/CD Pipeline** (1j) - ROI 1.60 ✅ **FAIT**
   - ✅ GitHub Actions avec 5 jobs
   - ✅ Tests automatiques (89% coverage)
   - ✅ Pylint, Black, Mypy, Bandit
   - ✅ Codecov integration
   - ✅ Build automatique sur main branch

**Total Sprint 2**: 5-7 jours (tous complétés ✅)
**Résultat**: ✅ Parsing 87% plus rapide (12min), ✅ BD auto-update quotidien (zero maintenance), ✅ Pool stats viewer, ✅ CI/CD opérationnel (89% coverage)
**Impact**: Infrastructure automatisée, qualité garantie, gains massifs pour utilisateur 🎉

---

### 🟢 Sprint 3+ (Mois 2+): Features Avancées
**Objectif**: UX et portabilité (après code stable et testé)

- [ ] #6 GUI Desktop (1-2 semaines) - ROI 0.62
  - Prototype tkinter ou PyQt6
  - Interface moderne et réactive
- [ ] #7 Support Multi-plateformes (2-3j) - ROI 0.63
  - Linux et macOS support
  - Tests sur chaque OS
- [ ] #8 Internationalisation i18n (1-2j) - ROI 0.60
  - Support FR/EN avec gettext
  - Extraction strings
- [ ] #12 Web App Client-Serveur (2-3 semaines) - ROI 0.62 (optionnel)
  - Backend FastAPI + Frontend React
  - Base PostgreSQL
  - Déploiement cloud

**Total**: 3-6 semaines
**Résultat**: Application accessible, portable, moderne

**Note**: Ces features ne seront implémentées qu'APRÈS avoir résolu la dette technique (Sprint 1). Sinon, le refactoring de ces features sera très douloureux.

---

## 📝 Notes de Développement

### Commandes Utiles

```bash
# Installation dépendances
pip install -r requirements.txt          # Production
pip install -r requirements-dev.txt      # Développement

# Tests
python test_db_fixes.py                  # Tests sécurité/performance
pytest tests/ -v                         # Tous les tests
pytest tests/ --cov=src --cov-report=html  # Avec couverture

# Linting (à ajouter)
pylint src/ --fail-under=8.0
black src/ --check
mypy src/

# Build
python build_app.py                      # Build executable
python create_package.py                 # Package portable

# Database
python cleanup_db.py                     # Backup et nettoyage
```

---

### Métriques Réalisées (Dette Technique First)

| Métrique | Avant | Sprint 0 ✅ | Sprint 1 ✅ COMPLÉTÉ | Sprint 2 🔴 (EN COURS) | Final |
|----------|-------|-------------|----------------------|----------------------|-------|
| **Test Coverage** | ~5% | ~5% | **89%** ✅✅✅ | 89% | 95%+ |
| **Largest File** | 2,381 lignes | 2,381 lignes | **220 lignes** ✅✅✅ | 220 lignes | <200 lignes |
| **SQL Injections** | 0 ✅ | 0 ✅ | 0 ✅ | 0 ✅ | 0 ✅ |
| **Hardcoded Values** | ~20 | **0** ✅ | 0 ✅ | 0 ✅ | 0 ✅ |
| **Migrations BD** | Non 🔴 | Non | **Alembic 1.17.2** ✅✅ | Alembic 1.17.2 ✅ | Alembic + ORM |
| **Parse Time (all)** | 90-120 min | 90-120 min | 90-120 min | **12 min** ✅✅✅ | <10 min |
| **Assistant Methods** | 30 | 30 | 30 | **54** ✅✅ | 54+ |
| **Build Time** | ~2 min | ~2 min | ~2 min | ~2 min | <1 min |

**Résultat Sprint 1** ✅:
- **Test Coverage**: Objectif 70%+ → **89% atteint** (dépassé de 19%) 🎉
- **Largest File**: Objectif <500 lignes → **220 lignes atteint** (dépassé de 56%) 🎉
- **Migrations BD**: Alembic configuré et testé 🎉

**Impact Sprint 1**: Base saine = Toutes futures tâches PLUS RAPIDES et PLUS SÛRES ! 🚀

**Résultat Sprint 2 (partiel)** ✅:
- **Parse Time**: 90-120 min → **12 min** (87% amélioration) 🎉🎉🎉
- **Assistant Methods**: 30 → **54 méthodes** (24 méthodes restaurées) 🎉
- **Parallel Workers**: 1 → **10 workers** (ThreadPoolExecutor optimisé) 🎉
- **Bug #1 Fixed**: Cookie click dynamique (plus de coordonnées hardcodées) 🎉

**Impact Sprint 2**: Performance massive + features complètes = Outil professionnel ! 🚀

---

## 🐛 Bugs Connus

### Bug #1: Cookie Click Coordinates ⭐ FIXÉ dans Tâche #4
**Fichier**: `parser.py:111`
**Priorité**: Haute
**Problème**: `pyautogui.click(1661, 853)` ne fonctionne pas sur tous les écrans
**Solution**: Voir Tâche #4 - `accept_cookies_dynamic()`

### Bug #2: SyntaxWarning in parser.py ✅ FIXÉ
**Fichier**: `parser.py:111`
**Priorité**: Basse
**Warning**: `invalid escape sequence '\['`
**Status**: ✅ **Corrigé** (2025-11-27 dans Tâche #2)
**Solution appliquée**:
```python
# AVANT
elem.find_element(By.CLASS_NAME, "text-\[9px\]")

# APRÈS
elem.find_element(By.CLASS_NAME, r"text-\[9px\]")
```

---

## 💡 Idées Futures (Backlog)

### En Cours de Planification
- **Tâche #11** : Auto-Update BD (Service Windows) - Plus-value: 13, Difficulté: 8, ROI: 1.63 ⭐ (DÉPEND de #4)
- **Tâche #12** : Web App Client-Serveur - Plus-value: 21, Difficulté: 34, ROI: 0.62

### Backlog Long Terme
- **API REST** - Exposer fonctionnalités via API (Plus-value: 8, Difficulté: 13)
- **Discord Bot** - Recommandations draft dans Discord (Plus-value: 5, Difficulté: 8)
- **Overlay en jeu** - Affichage tier lists pendant draft (Plus-value: 13, Difficulté: 21)
- **Machine Learning** - Prédiction winrate avancée (Plus-value: 8, Difficulté: 21)
- **Cloud Sync** - Synchronisation pools entre devices (Plus-value: 5, Difficulté: 13)
- **Mobile App** - React Native (Plus-value: 8, Difficulté: 21)
- **Monitoring Dashboard** - Sentry + Grafana pour prod (Plus-value: 5, Difficulté: 8)

---

## ✅ Completed Features

### Version 1.0.2 - Configuration Refactoring (2025-11-27)
- ✅ **Tâche #2: Extraction valeurs hardcodées** - config_constants.py avec 5 dataclasses
- ✅ **Bug #2 Fix: SyntaxWarning parser.py** - Raw string literal pour regex
- ✅ **Backward Compatibility** - @property decorators dans config.py
- ✅ **TODO.md Update** - Approche "Dette Technique First" avec scores révisés

### Version 1.0.1 - Security & Performance Update (2025-11-27)
- ✅ **SQL Injection Fixes** - Toutes les requêtes paramétrées
- ✅ **Database Indexes** - 6 index pour performance (50-90% amélioration)
- ✅ **Requirements Management** - requirements.txt + requirements-dev.txt
- ✅ **Test Suite** - test_db_fixes.py pour sécurité et index
- ✅ **Documentation** - SECURITY_FIXES.md, CHANGELOG.md, AUDIT_REPORT.md

### Version 1.0.0 - Initial Release (2025-10-15)
- ✅ **Tier List Generator** - Blind Pick & Counter Pick
- ✅ **Code Refactoring** - champion normalization → constants.py
- ✅ **Real-time Draft Coach** - LCU integration
- ✅ **Champion Pool Manager** - CRUD operations
- ✅ **Team Builder** - Optimal trios/duos
- ✅ **Standalone Distribution** - PyInstaller executable

---

**Dernière mise à jour**: 2025-11-27
**Mainteneur**: @pj35
**Version**: 1.0.1
**Méthode**: Agile/Scrum avec scores Fibonacci
