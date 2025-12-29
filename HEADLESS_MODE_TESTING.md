# 🧪 Guide de Test - Mode Headless pour Auto-Update

## 📋 Résumé du Fix

**Problème identifié**: Auto-update (Task Scheduler) échouait à scraper les données
- Logs montraient: `0/172 champions succeeded, 172 failed` (depuis 2025-12-23)
- Root cause: `pythonw.exe` ne peut pas lancer Firefox GUI en background

**Solution implémentée**: Mode headless pour Firefox WebDriver
- Firefox s'exécute sans interface graphique (`--headless`)
- Compatible avec Task Scheduler et pythonw.exe
- Tous les DOM operations (clics, scrolls) fonctionnent identiquement

---

## 🔧 Changements Techniques

### Fichiers Modifiés

1. **`src/parser.py`** (27 lignes modifiées)
   - Ajout paramètre `headless: bool = False` dans `__init__()`
   - Firefox lancé avec `--headless` si `headless=True`
   - Skip fullscreen/maximize en mode headless (inutile sans GUI)

2. **`src/parallel_parser.py`** (8 lignes modifiées)
   - Propagation du paramètre `headless` à tous les workers
   - Logging amélioré (affiche `headless=True/False` par thread)

3. **`scripts/auto_update_db.py`** (13 lignes modifiées)
   - `ParallelParser(headless=True)` pour Task Scheduler
   - Calcul du taux d'échec + warnings si >50%
   - Logging détaillé avec traceback pour premier échec

---

## ✅ Tests à Effectuer

### Test 1: Mode Headless Manuel (Quick Test - 3 champions)

```bash
# Terminal 1 - Lancer test rapide
python -c "
from src.parallel_parser import ParallelParser
from src.db import Database
from src.constants import normalize_champion_name_for_url

db = Database('data/db.db')
db.connect()

# Test avec 1 worker, 3 champions, headless=True
parser = ParallelParser(max_workers=1, headless=True)
test_champions = ['Aatrox', 'Ahri', 'Akali']

print('Testing headless scraping with 3 champions...')
# Vous ne verrez PAS de fenêtre Firefox s'ouvrir (c'est normal!)

for champ in test_champions:
    try:
        result, matchups = parser._scrape_champion_with_retry(champ, normalize_champion_name_for_url)
        print(f'✅ {champ}: {len(matchups)} matchups scraped')
    except Exception as e:
        print(f'❌ {champ}: FAILED - {e}')

parser.close()
db.close()
"
```

**Résultat attendu**:
- Aucune fenêtre Firefox visible (headless = sans GUI)
- Console affiche: `[PARSER] Headless mode enabled - Firefox will run without GUI`
- Chaque champion devrait retourner ~20-30 matchups
- Aucune erreur Selenium

---

### Test 2: Auto-Update Complet (Full Test - 172 champions)

**⚠️ ATTENTION**: Ce test prend ~12-14 minutes et va **reset la database**

```bash
# Backup database d'abord!
cp data/db.db data/db_backup_before_headless_test.db

# Lancer auto-update avec headless mode
python scripts/auto_update_db.py
```

**Résultat attendu**:
```
[INFO] Initializing ParallelParser (10 workers, headless mode)...
[SUCCESS] ParallelParser initialized in headless mode (no GUI)
[INFO] Starting parallel scraping of champions from Riot API...
[SUCCESS] Scraping completed in 12.5 minutes
[INFO] Champions parsed: 172/172 succeeded, 0 failed  ← CECI EST LE SUCCESS METRIC
```

**Si échecs** (ex: `0/172 succeeded`):
- Vérifier `logs/auto_update.log` pour traceback détaillé
- Première erreur aura full stack trace
- Possibilité: LoLalytics bloque headless mode (détection anti-bot)

---

### Test 3: Vérifier Task Scheduler (Production Test)

**Option A - Lancer manuellement la tâche**:
```powershell
# PowerShell en Administrateur
Start-ScheduledTask -TaskName "LeagueStats Auto-Update"
```

**Option B - Attendre exécution automatique (3 AM)**:
- Checker logs le lendemain matin

**Vérifier le résultat**:
```bash
# Voir les logs de la dernière exécution
tail -n 50 logs/auto_update.log
```

**Success indicators**:
- `[SUCCESS] ParallelParser initialized in headless mode (no GUI)`
- `Champions parsed: 172/172 succeeded, 0 failed` (ou proche de 172)
- `[SUCCESS] Auto-update completed successfully`
- Windows notification: "BD mise à jour avec succès!"

---

## 🐛 Troubleshooting

### Problème: Toujours `0/172 succeeded`

**Causes possibles**:
1. **LoLalytics détecte headless mode**
   - Solution: Ajouter User-Agent personnalisé dans `parser.py`
   - Exemple: `options.set_preference("general.useragent.override", "Mozilla/5.0...")`

2. **Cookie banner bloque le scraping**
   - Vérifier logs pour `accept_cookies` errors
   - Tester stratégies de détection (ID, CSS, XPath)

3. **Timeouts en headless**
   - Augmenter `FIREFOX_STARTUP_DELAY` dans `config_constants.py`
   - Augmenter timeouts Selenium (actuellement defaults)

### Problème: Fenêtres Firefox s'ouvrent quand même

**Cause**: `headless=False` quelque part
- Vérifier `auto_update_db.py` ligne 177: `headless=True`
- Vérifier logs: devrait afficher `headless mode enabled`

### Problème: Erreur `'NoneType' object has no attribute 'write'`

**Résolu**: Ce bug était lié à tqdm en mode headless
- Le code détecte déjà `sys.stdout is None` (ligne 55-65 parallel_parser.py)
- tqdm est automatiquement désactivé en headless

---

## 📊 Métriques de Validation

| Métrique | Avant Fix | Après Fix (Attendu) |
|----------|-----------|---------------------|
| Success rate | **0/172 (0%)** | **172/172 (100%)** |
| Duration | 6 min (échecs rapides) | 12-14 min (scraping complet) |
| Database state | Vide après update | 29,000+ matchups |
| Firefox windows | 0 (crash silencieux) | 0 (headless intentionnel) |
| Logs clarity | Peu d'infos | Traceback + failure rate |

---

## 🎯 Checklist de Validation Complète

- [ ] **Test 1**: 3 champions en headless → 3/3 succeeded
- [ ] **Test 2**: Auto-update manuel → 172/172 succeeded (ou >95%)
- [ ] **Test 3**: Task Scheduler → Windows notification success
- [ ] **Vérification DB**: `SELECT COUNT(*) FROM matchups` → >25,000 rows
- [ ] **Backward compat**: Scraping manuel (GUI) toujours fonctionnel
- [ ] **Logs propres**: Pas d'erreurs critiques dans `logs/auto_update.log`

---

## 📞 Si Problèmes Persistent

**Informations à fournir**:
1. Dernière sortie de `logs/auto_update.log` (50 dernières lignes)
2. Résultat de Test 1 (3 champions)
3. Version de Firefox: `firefox --version`
4. Version de Selenium: `pip show selenium`
5. Screenshot ou copie d'erreur complète

**Contact**: Ouvrir un issue ou demander à Claude
