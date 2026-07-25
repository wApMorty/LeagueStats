# Structure de la Base de Données - League Stats Coach

## 📁 Organisation des fichiers

### **Base de données légitime**

```
LeagueStats/
├── data/
│   └── db.db                 ← BASE DE DONNÉES PRINCIPALE (développement)
```

**Emplacement unique** : `data/db.db`
- Contient 171 champions, 36k+ matchups
- Utilisée en mode développement
- Sauvegardée dans Git (via .gitignore mais peut être trackée explicitement)

---

## 🔧 Résolution des chemins (config.py)

### **Mode développement** (python lol_coach.py)
```python
config.DATABASE_PATH → "d:/Users/.../LeagueStats/data/db.db"
```

### **Mode exécutable** (LeagueStatsCoach.exe)
```
LeagueStatsCoach_Release/
├── LeagueStatsCoach.exe
└── db.db                     ← Copié depuis data/db.db lors du build
```

```python
config.DATABASE_PATH → "{exe_dir}/db.db"
```

### **Logique de résolution**

1. **Si PyInstaller temp** (`_MEIPASS`) : `{_MEIPASS}/db.db`
2. **Si exécutable frozen** : `{exe_dir}/db.db`
3. **Si développement** : `{project_root}/data/db.db` ✅ PRIORITÉ
4. ~~Fallback : `{project_root}/db.db`~~ ❌ SUPPRIMÉ

---

## 🛠️ Build Process

### **Script : build_app.py**

```python
# 1. PyInstaller emballe data/db.db dans l'exe
'--add-data', 'data/db.db;.'

# 2. Copie explicite dans le dossier release
shutil.copy2("data/db.db", "LeagueStatsCoach_Release/db.db")
```

### **Fichier .spec : LeagueStatsCoach.spec**

```python
datas=[('data/db.db', '.'), ('README.md', '.')]
```

- Première entrée : `('data/db.db', '.')` → Emballe data/db.db dans le root de l'exe
- Lors de l'exécution : Extrait dans `_MEIPASS/db.db`

---

## 🗑️ Fichiers obsolètes (à supprimer)

### **Reliquats d'anciennes architectures**

❌ `db.db` (racine du projet)
- Ancien emplacement avant refactoring
- Peut causer confusion avec get_resource_path()
- **Action** : Supprimer

❌ `db_2.db` (racine du projet)
- Backup manuel obsolète
- **Action** : Supprimer

❌ `LeagueStatsCoach_Release/db.db`
- Build ancien
- **Action** : Supprimer manuellement

### **Nettoyage manuel**

```bash
rm -f db.db db_2.db LeagueStatsCoach_Release/db.db
```

Fichiers a supprimer :
- `db.db` (racine)
- `db_2.db`
- `LeagueStatsCoach_Release/` (dossier complet)
- `build/`, `dist/`, `__pycache__/`

---

## ✅ Checklist de validation

### **Développement**
- [ ] `data/db.db` existe et est à jour
- [ ] `db.db` à la racine n'existe PAS
- [ ] `python lol_coach.py` fonctionne
- [ ] Affiche : `DATABASE_PATH = .../data/db.db`

### **Build**
- [ ] `python build_app.py` réussit
- [ ] `LeagueStatsCoach_Release/db.db` existe (2.7 MB)
- [ ] `LeagueStatsCoach_Release/LeagueStatsCoach.exe` existe
- [ ] Double-clic sur exe → Fonctionne

### **Après nettoyage**

Structure finale :
```
LeagueStats/
├── data/
│   └── db.db                 ✅ SEUL FICHIER .db
├── src/
├── lol_coach.py
└── build_app.py
```

---

## 🐛 Résolution de problèmes

### **Erreur : "DATABASE NOT FOUND"**

**En développement** :
```bash
# Vérifier que data/db.db existe
ls -la data/db.db

# Si absent, recréer
python lol_coach.py
# Option 2: Update Champion Data
```

**En mode exe** :
```bash
# Vérifier que db.db est à côté de l'exe
cd LeagueStatsCoach_Release
ls -la db.db

# Si absent, rebuild
python build_app.py
```

### **L'exe utilise la mauvaise database**

**Symptôme** : Données anciennes ou manquantes

**Solution** :
1. Vérifier `data/db.db` est à jour
2. Rebuild : `python build_app.py`
3. Vérifier taille de `LeagueStatsCoach_Release/db.db`

### **Plusieurs fichiers db.db trouvés**

**Diagnostic** :
```bash
find . -name "*.db" -type f
```

**Solution** : supprimer les `.db` hors de `data/`.

---

## 📝 Notes pour les développeurs

### **Règle d'or**
> **TOUJOURS** utiliser `config.DATABASE_PATH` pour accéder à la base de données.
> **JAMAIS** hardcoder `"db.db"` ou `"data/db.db"`.

### **Exemples corrects**

✅ **Assistant** :
```python
from .config import config
self.db = Database(config.DATABASE_PATH)
```

✅ **Draft Monitor** :
```python
self.assistant = Assistant()  # Utilise config.DATABASE_PATH en interne
```

✅ **Main** :
```python
from src.config import config
db = Database(config.DATABASE_PATH)
```

### **Exemples INCORRECTS**

❌ Hardcodé :
```python
db = Database("db.db")
db = Database("data/db.db")
```

❌ Fallback non sûr :
```python
db = Database(config.DATABASE_PATH if 'config' in globals() else "db.db")
```

---

## 🔄 Workflow de mise à jour

### **1. Update data (développement)**
```bash
python lol_coach.py
# Option 2: Update Champion Data (Riot API)
# Option 3: Parse Match Statistics
```
→ Met à jour `data/db.db`

### **2. Build pour distribution**
```bash
python build_app.py
```
→ Copie `data/db.db` → `LeagueStatsCoach_Release/db.db`

### **3. Distribution**
```bash
cd LeagueStatsCoach_Release
zip -r LeagueStatsCoach_v1.2.zip .
```

---

## 📊 Historique des changements

| Date | Changement | Raison |
|------|-----------|--------|
| Sept 2024 | `db.db` à la racine | Architecture initiale |
| Sept 2024 | Migration vers `data/db.db` | Organisation du projet |
| Oct 2024 | Fix `get_resource_path()` | Priorité explicite à `data/` |

---

**Dernière mise à jour** : 3 octobre 2025
