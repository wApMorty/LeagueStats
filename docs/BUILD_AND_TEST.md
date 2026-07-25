# Build and Test Guide

Guide pour builder, tester et distribuer le `.exe`.

## Source de données

**SQLite local, en dev comme en production.** La couche distante (API FastAPI sur
Render + PostgreSQL Neon, modes `hybrid` / `postgresql_only`) a été décommissionnée —
voir `docs/ROADMAP_2026.md` (Décisions B & C). Il n'y a plus de détection de mode ni
de bascule : `Assistant()` ouvre `config.DATABASE_PATH`.

Le chemin de la base est résolu par `get_resource_path()` dans `src/config.py`, qui
gère les trois cas : `_MEIPASS` (PyInstaller), à côté de l'exécutable, et `data/db.db`
en développement.

---

## Build du .exe

### Prérequis

```bash
pip install -r requirements-dev.txt   # inclut pyinstaller
```

### Build

```bash
python build_app.py
```

ou directement :

```bash
pyinstaller --clean LeagueStatsCoach.spec
```

**Fichier produit** : `dist/LeagueStatsCoach.exe`

> `data/db.db` est gitignoré (données personnelles) mais embarqué par le `.spec`.
> En CI, un schéma vide est généré avant le build via `python -m alembic upgrade head`.

---

## Tests

```bash
pytest tests/ -v                                      # suite complète
pytest tests/ --cov=src/analysis --cov-fail-under=70  # avec seuil de couverture
```

Avant toute PR (voir `CLAUDE.md`) :

```bash
python -m black src/ tests/ scripts/
python -m black --check --diff src/ tests/ scripts/
python -m pylint src/ --fail-under=8.0
python -m bandit -r src/ -f screen --severity-level medium -c pyproject.toml
```

### Vérifier la base utilisée

```bash
python -c "from src.config import config; print(config.DATABASE_PATH)"
```

### Mesurer une requête

```bash
python -c "
from src.db import Database
from src.config import config
import time

db = Database(config.DATABASE_PATH)
db.connect()

start = time.time()
champions = db.get_all_champion_names()
print(f'Query time: {time.time() - start:.3f}s  ({len(champions)} champions)')
db.close()
"
```

Attendu en local : **< 0,1 s**.

---

## Troubleshooting

### Le .exe ne trouve pas la base

`get_resource_path()` cherche dans l'ordre : `sys._MEIPASS`, le dossier de
l'exécutable, puis `data/`. Vérifier que `db.db` est bien à côté du `.exe` ou
embarqué par le `.spec`.

```python
# Diagnostic rapide
import sys
print(f"sys.frozen = {getattr(sys, 'frozen', False)}")
from src.config import config
print(f"DATABASE_PATH = {config.DATABASE_PATH}")
```

### Base vide ou incomplète

L'app affiche l'âge des données à chaque lancement (`src/data_freshness.py`).
Pour re-remplir :

```bash
python scripts/update_all.py                          # pipeline complet
python scripts/repair_data.py --target matchups       # réparation ciblée
python scripts/repair_data.py --target synergies
```

Voir `docs/runbook_scraping.md` en cas d'échec de scraping.

---

## Distribution

### Package final

```bash
python create_package.py
```

**Fichier produit** : `LeagueStatsCoach_Portable.zip`

**Contenu** :
- `LeagueStatsCoach.exe`
- `data/db.db`
- `README.md`

### Installation utilisateur

1. Extraire `LeagueStatsCoach_Portable.zip`
2. Lancer `LeagueStatsCoach.exe`

Aucune configuration manuelle requise.

---

## Résumé

| Scénario | Commande | Source de données |
|----------|----------|-------------------|
| Développement local | `python lol_coach.py` | `data/db.db` |
| Tests | `pytest tests/ -v` | base temporaire (fixtures) |
| Production `.exe` | `dist/LeagueStatsCoach.exe` | `db.db` embarqué / voisin |
