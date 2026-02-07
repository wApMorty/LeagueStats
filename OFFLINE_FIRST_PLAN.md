# Plan d'Action - OfflineFirstDataSource

**Date de création** : 2026-02-07
**Objectif** : Passer d'une architecture API-first à Offline-first
**Approche** : Approche 2 - OfflineFirstDataSource dédiée (recommandée par Architecte)

## 🎯 Vue d'Ensemble

**Architecture Cible** :
- **Offline-first** : Utiliser SQLite par défaut (rapide, fiable, 0ms latency)
- **Refresh intelligent** : Si données > 24h → Télécharger depuis API et remplacer SQLite
- **Fallback gracieux** : Si API échoue → Continuer avec SQLite existante
- **Auto-update inchangé** : Script continue scraping → SQLite, mais met à jour timestamp

**Estimation** : 11-15 heures de développement (11 tâches en 4 phases)

---

## 📋 Les 11 Tâches

### Phase 1 - Foundation (2-3h)

#### Tâche #1 : Migration Alembic table metadata
- **Expert** : database-expert
- **Dépendances** : Aucune ✅ PRÊTE
- **Fichier à créer** : `alembic/versions/XXXXXX_add_metadata_table.py`
- **Schema** :
  ```sql
  CREATE TABLE metadata (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );
  ```
- **Validation** :
  - `alembic upgrade head` passe
  - Table metadata existe avec schema correct
  - Migration réversible (downgrade fonctionne)

#### Tâche #2 : Méthodes metadata dans src/db.py
- **Expert** : python-expert
- **Dépendances** : #1
- **Fichier à modifier** : `src/db.py`
- **Méthodes à ajouter** :
  - `get_metadata(key: str) -> Optional[str]`
  - `set_metadata(key: str, value: str) -> None`
  - `replace_all_data(champions, matchups, synergies) -> None`
  - `_ensure_metadata_table_exists() -> None` (backward compatibility)
- **Validation** :
  - Type hints sur toutes méthodes
  - Requêtes SQL paramétrées
  - Transaction atomique pour replace_all_data
  - Backward compatibility (BD sans metadata)

#### Tâche #3 : Méthodes metadata dans src/sqlite_data_source.py
- **Expert** : python-expert
- **Dépendances** : #2
- **Fichier à modifier** : `src/sqlite_data_source.py`
- **Méthodes à ajouter** :
  - `get_last_sync_timestamp() -> Optional[datetime]`
  - `update_last_sync_timestamp(timestamp: datetime) -> None`
  - `replace_all_data(champions, matchups, synergies) -> None`
- **Validation** :
  - Pure delegation (Adapter Pattern)
  - Format datetime ISO 8601
  - Tests avec mocks Database

---

### Phase 2 - Core Logic (4-5h)

#### Tâche #4 : Module metadata_manager.py
- **Expert** : python-expert
- **Dépendances** : #2
- **Fichier à créer** : `src/utils/metadata_manager.py`
- **Fonctions à ajouter** :
  - `get_last_sync_timestamp(db: Database) -> Optional[datetime]`
  - `update_last_sync_timestamp(db: Database, timestamp: datetime) -> None`
  - `is_data_stale(db: Database, threshold_hours: int = 24) -> bool`
- **Validation** :
  - Type hints + docstrings complètes
  - Gestion erreurs (format invalide, BD sans metadata)
  - Tests unitaires 100% coverage

#### Tâche #5 : Méthode download_all_data_bulk dans API
- **Expert** : python-expert
- **Dépendances** : Aucune ✅ PRÊTE
- **Fichier à modifier** : `src/api_data_source.py`
- **Méthode à ajouter** :
  - `download_all_data_bulk() -> Dict[str, List]`
  - Retourne : `{"champions": [...], "matchups": [...], "synergies": [...]}`
- **Endpoints utilisés** :
  - `GET /api/champions`
  - `GET /api/matchups/bulk`
  - `GET /api/synergies/bulk`
- **Validation** :
  - Timeout 300s (5 min)
  - Retry logic (3 tentatives)
  - Logging progression
  - Exceptions propagées pour fallback

#### Tâche #6 : Classe OfflineFirstDataSource
- **Expert** : python-expert
- **Dépendances** : #3, #4, #5
- **Fichier à créer** : `src/offline_first_data_source.py`
- **Classe** : `OfflineFirstDataSource(DataSource)`
- **Méthodes clés** :
  - `__init__(database_path, api_base_url)`
  - `connect() -> None` (vérifie staleness + refresh si nécessaire)
  - `_download_and_replace_data() -> None` (download API + remplace SQLite)
  - Toutes méthodes DataSource : Délègue à SQLiteDataSource
- **Validation** :
  - Composition SQLiteDataSource + APIDataSource
  - Graceful fallback si API échoue
  - Logging verbeux
  - Tests refresh + fallback

---

### Phase 3 - Integration (2-3h)

#### Tâche #7 : Config OfflineFirstConfig
- **Expert** : python-expert
- **Dépendances** : Aucune ✅ PRÊTE
- **Fichier à modifier** : `src/config_constants.py`
- **Config à ajouter** :
  ```python
  @dataclass
  class OfflineFirstConfig:
      ENABLED: bool = True
      REFRESH_THRESHOLD_HOURS: int = 24
      AUTO_REFRESH_ON_CONNECT: bool = True
      FALLBACK_TO_CACHED: bool = True
  ```
- **Validation** :
  - Docstring complète
  - Valeurs par défaut sensées
  - Backward compatible avec HybridDataSource

#### Tâche #8 : Modifier Assistant pour OfflineFirstDataSource
- **Expert** : python-expert
- **Dépendances** : #6, #7
- **Fichier à modifier** : `src/assistant.py`
- **Changements** :
  - Import OfflineFirstDataSource + offline_first_config
  - Modifier `__init__()` logique sélection data source
  - Mettre à jour docstring Assistant (nouveau mode)
- **Validation** :
  - Backward compatibility HybridDataSource
  - Tests Assistant avec OfflineFirstDataSource
  - Docstring claire sur modes

#### Tâche #9 : Modifier auto_update_db.py pour timestamp
- **Expert** : python-expert
- **Dépendances** : #4
- **Fichier à modifier** : `scripts/auto_update_db.py`
- **Changements** :
  - Import metadata_manager
  - Appeler `update_last_sync_timestamp()` après scraping réussi
  - Ligne ~420 (après recalcul scores)
- **Validation** :
  - Timestamp mis à jour UNIQUEMENT si succès
  - Format ISO 8601
  - Logging clair
  - Tests manuels `SELECT * FROM metadata`

---

### Phase 4 - Testing (3-4h)

#### Tâche #10 : Tests OfflineFirstDataSource
- **Expert** : qa-expert
- **Dépendances** : #6
- **Fichier à créer** : `tests/test_offline_first_data_source.py`
- **Tests à créer** :
  - `test_connect_with_fresh_data` (pas de refresh)
  - `test_connect_with_stale_data` (refresh déclenché)
  - `test_connect_with_api_failure_fallback`
  - `test_backward_compatibility_no_metadata`
  - `test_all_methods_delegate_to_sqlite`
- **Validation** :
  - Coverage >= 70% OfflineFirstDataSource
  - Mocks SQLiteDataSource + APIDataSource
  - `pytest tests/test_offline_first_data_source.py -v` passe

#### Tâche #11 : Tests Assistant integration
- **Expert** : qa-expert
- **Dépendances** : #8
- **Fichier à modifier** : `tests/test_assistant_integration.py`
- **Tests à ajouter** :
  - `test_assistant_uses_offline_first_by_default`
  - `test_assistant_offline_first_refresh_on_stale_data`
  - `test_assistant_backward_compatibility_hybrid`
- **Validation** :
  - Tests avec mocks (pas de BD/API réelle)
  - Coverage Assistant.__init__() augmenté
  - `pytest tests/test_assistant_integration.py -v` passe

---

## 🔄 Ordre d'Exécution Recommandé

### Vague 1 (parallèle possible) - PRÊTES MAINTENANT
- ✅ **#1** : Migration Alembic
- ✅ **#5** : download_all_data_bulk API
- ✅ **#7** : OfflineFirstConfig

### Vague 2 (après Vague 1)
- **#2** : Méthodes Database (attend #1)

### Vague 3 (après Vague 2)
- **#3** : Méthodes SQLiteDataSource (attend #2)
- **#4** : metadata_manager.py (attend #2)

### Vague 4 (après Vague 3)
- **#6** : OfflineFirstDataSource (attend #3, #4, #5)
- **#9** : auto_update_db (attend #4)

### Vague 5 (après Vague 4)
- **#8** : Modifier Assistant (attend #6, #7)
- **#10** : Tests OfflineFirstDataSource (attend #6)

### Vague 6 (finale)
- **#11** : Tests Assistant integration (attend #8)

---

## ✅ Critères de Succès Final

L'implémentation sera considérée complète quand :

### Fonctionnel
- ✅ Données SQLite < 24h → Utilise SQLite directement (0ms latency)
- ✅ Données SQLite > 24h → Download API + remplace SQLite atomiquement
- ✅ API échoue → Continue avec SQLite (graceful fallback)
- ✅ Auto-update met à jour timestamp après scraping
- ✅ Backward compatibility : Ancienne BD sans metadata → Créer table auto

### Technique
- ✅ Toutes les 11 tâches marquées "completed"
- ✅ Migration Alembic passe (`alembic upgrade head`)
- ✅ Tous tests passent (`pytest tests/ -v`)
- ✅ Formatage Black appliqué (`python -m black src/ tests/`)
- ✅ Type hints sur toutes nouvelles fonctions
- ✅ Coverage >= 70% sur nouvelles classes
- ✅ Compilation Python OK (`python -m py_compile src/**/*.py`)

---

## 🚀 Comment Reprendre

### 1. Voir les tâches restantes
```python
# Dans Claude Code
TaskList
```

### 2. Voir les détails d'une tâche
```python
TaskGet(taskId="#1")
```

### 3. Spawner un expert pour une tâche
```bash
# Exemple pour tâche #1
/spawn database-expert

# Puis lui passer :
"Crée la migration Alembic pour table metadata selon le plan de la tâche #1.
Voir OFFLINE_FIRST_PLAN.md pour les détails."
```

### 4. Marquer une tâche complétée
```python
TaskUpdate(taskId="#1", status="completed")
```

### 5. Vérifier déblocage tâches suivantes
```python
TaskList
```

---

## ⚠️ Risques et Mitigations

### Risque 1 : Download API lent (30-60s)
**Mitigation** : Timeout 5 min, logging progression, abandon si trop lent

### Risque 2 : Transaction SQLite peut bloquer DB (2-5s)
**Mitigation** : Transaction IMMEDIATE, logs clairs, tester performance

### Risque 3 : Ancienne BD sans table metadata
**Mitigation** : Créer table auto au connect(), initialiser timestamp à epoch 0

---

## 📚 Références

- **Architecture complète** : Voir output de l'Architecte (agent `adb7da5`)
- **Plan détaillé** : Voir output du Tech Lead (agent `a29bdb6`)
- **Code existant** :
  - `src/hybrid_data_source.py` - Pattern API-first actuel
  - `src/api_data_source.py` - Client API HTTP
  - `scripts/sync_local_to_neon.py` - Pattern de transfert bulk (à inverser)

---

**Dernière mise à jour** : 2026-02-07 01:15 AM
**Status** : Plan créé, prêt pour implémentation
