# Build and Test Guide

Guide pour builder et tester le .exe avec détection automatique du mode de données.

## Configuration Automatique

Le mode de données est **détecté automatiquement** selon le contexte d'exécution :

| Contexte | Mode | Data Source | Performance |
|----------|------|-------------|-------------|
| **Development** (Python) | `sqlite_only` | SQLite local | < 0.1ms |
| **Production** (.exe) | `postgresql_only` | PostgreSQL Neon | 100-300ms |

### Implémentation

Fichier : `src/config_constants.py`

```python
def _get_default_mode() -> str:
    """Detect execution context and return appropriate data source mode."""
    import sys

    # Check if running as PyInstaller compiled executable
    is_compiled = getattr(sys, 'frozen', False)

    if is_compiled:
        return "postgresql_only"  # Production .exe
    else:
        return "sqlite_only"       # Development
```

---

## Build du .exe

### Prérequis

```bash
pip install -r requirements.txt
```

### Build

```bash
pyinstaller --clean LeagueStatsCoach.spec
```

**Fichier produit** : `dist/LeagueStatsCoach.exe`

---

## Tests

### Test 1 : Mode Development (Python)

```bash
python -c "
from src.config_constants import api_config
print(f'Mode: {api_config.MODE}')
print(f'Expected: sqlite_only')
"
```

**Résultat attendu** :
```
Mode: sqlite_only
Expected: sqlite_only
```

### Test 2 : Mode Development (Performance)

```bash
python -c "
from src.hybrid_data_source import HybridDataSource
import time

ds = HybridDataSource()
ds.connect()

start = time.time()
champions = ds.get_all_champion_names()
duration = time.time() - start

print(f'Data source: SQLite local')
print(f'Query time: {duration:.3f}s')
print(f'Champions: {len(champions)}')
print(f'Expected: < 0.1s')
ds.close()
"
```

**Résultat attendu** :
```
Data source: SQLite local
Query time: 0.000s
Champions: 172
Expected: < 0.1s
```

### Test 3 : Mode Production (.exe)

Après build du .exe :

```powershell
# Lancer le .exe et vérifier dans les logs
dist\LeagueStatsCoach.exe
```

**Vérification manuelle** :
1. Le .exe démarre sans erreur
2. Les données champions sont chargées
3. La connexion PostgreSQL est utilisée (latence ~300ms au lieu de <1ms)

**Vérification programmatique** :

Créer un script de test dans le .exe :

```python
# Dans lol_coach.py, ajouter temporairement au démarrage:
from src.config_constants import api_config
print(f"[DEBUG] Execution mode: {api_config.MODE}")
print(f"[DEBUG] sys.frozen: {getattr(sys, 'frozen', False)}")
```

**Résultat attendu dans .exe** :
```
[DEBUG] Execution mode: postgresql_only
[DEBUG] sys.frozen: True
```

---

## Override Manuel (Si Nécessaire)

Si tu veux forcer un mode spécifique (testing), modifier **avant** l'import :

```python
# Forcer PostgreSQL en dev (pour tester)
import os
os.environ['LEAGUESTATS_MODE'] = 'postgresql_only'

from src.hybrid_data_source import HybridDataSource
# ...
```

**Note** : Actuellement non implémenté, mais peut être ajouté si besoin.

---

## Troubleshooting

### Problème : .exe utilise SQLite au lieu de PostgreSQL

**Cause** : `sys.frozen` non détecté correctement.

**Solution** :
1. Vérifier que PyInstaller a bien compilé :
   ```bash
   file dist/LeagueStatsCoach.exe
   # Doit être : PE32+ executable (console) x86-64
   ```

2. Tester `sys.frozen` dans le .exe :
   ```python
   # Ajouter au début de lol_coach.py
   import sys
   print(f"sys.frozen = {getattr(sys, 'frozen', False)}")
   ```

### Problème : .exe timeout PostgreSQL

**Cause** : Neon PostgreSQL indisponible ou connection string invalide.

**Solution** :
1. Vérifier connection string dans `src/credentials.py`
2. Tester connexion PostgreSQL en dev :
   ```bash
   python -c "from src.postgresql_data_source import PostgreSQLDataSource; ds = PostgreSQLDataSource(); ds.connect()"
   ```

3. Vérifier que `OBFUSCATED_READONLY_CONNECTION_STRING` est à jour

---

## Distribution

### Package Final

```bash
# Créer le ZIP portable
python create_package.py
```

**Fichier produit** : `LeagueStatsCoach_Portable.zip`

**Contenu** :
- `LeagueStatsCoach.exe` (mode `postgresql_only` automatique)
- `data/db.db` (SQLite backup, non utilisé par .exe mais présent)
- `README.md`

### Installation Utilisateur

1. Extraire `LeagueStatsCoach_Portable.zip`
2. Lancer `LeagueStatsCoach.exe`
3. Le .exe se connecte automatiquement à PostgreSQL Neon (remote)

**Aucune configuration manuelle requise** ✅

---

## Résumé

| Scénario | Commande | Mode | Data Source |
|----------|----------|------|-------------|
| Développement local | `python lol_coach.py` | `sqlite_only` | SQLite local |
| Test performance | Script Python ci-dessus | `sqlite_only` | SQLite local |
| Production .exe | `dist/LeagueStatsCoach.exe` | `postgresql_only` | PostgreSQL Neon |
| Gaming café | `.exe` sur clé USB | `postgresql_only` | PostgreSQL Neon |

**Configuration automatique** : Aucune intervention manuelle nécessaire 🎉
