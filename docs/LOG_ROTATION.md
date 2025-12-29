# 📋 Log Rotation System - LeagueStats Coach

## 🎯 Objectif

Le système de log rotation empêche le fichier `logs/auto_update.log` de devenir trop volumineux (actuellement ~1 GB!) en archivant automatiquement les anciens logs.

---

## 🔧 Installation Rapide

### **Étape 1: Configurer Task Scheduler**

```powershell
# En tant qu'Administrateur
cd C:\Users\pj35\.claude-worktrees\LeagueStats\inspiring-rhodes
.\scripts\setup_log_rotation.ps1
```

**Configuration par défaut**:
- **Fréquence**: Hebdomadaire (dimanche)
- **Heure**: 2h00 AM (1h avant auto-update à 3h00 AM)
- **Taille max**: 50 MB
- **Backups**: 5 fichiers conservés

### **Étape 2: Tester Manuellement**

```powershell
# Lancer rotation manuellement (test)
.\scripts\rotate_logs.ps1

# Vérifier les logs de rotation
Get-Content logs\log_rotation.log -Tail 20
```

---

## 📖 Utilisation Avancée

### **Options de Configuration**

```powershell
# Rotation quotidienne à 1h00 AM
.\scripts\setup_log_rotation.ps1 -Schedule Daily -Time "01:00"

# Rotation avec compression (économie d'espace)
.\scripts\setup_log_rotation.ps1 -Compress

# Rotation à 100 MB, garder 10 backups
.\scripts\setup_log_rotation.ps1 -MaxSizeMB 100 -MaxBackups 10

# Configuration complète personnalisée
.\scripts\setup_log_rotation.ps1 `
    -Schedule Weekly `
    -DayOfWeek Sunday `
    -Time "02:00" `
    -MaxSizeMB 50 `
    -MaxBackups 5 `
    -Compress
```

### **Paramètres Disponibles**

| Paramètre | Description | Valeur par défaut |
|-----------|-------------|-------------------|
| `-Schedule` | Fréquence: Daily, Weekly, Monthly | Weekly |
| `-DayOfWeek` | Jour (pour Weekly): Sunday, Monday, etc. | Sunday |
| `-Time` | Heure au format HH:MM | 02:00 |
| `-MaxSizeMB` | Taille max avant rotation (MB) | 50 |
| `-MaxBackups` | Nombre de backups à conserver | 5 |
| `-Compress` | Compresser les archives (.zip) | Non |

---

## 🔍 Fonctionnement

### **Processus de Rotation**

1. **Vérification**: Script vérifie la taille de `logs/auto_update.log`
2. **Condition**: Si taille > `MaxSizeMB` → Rotation déclenchée
3. **Archive**: Fichier renommé en `auto_update_YYYYMMDD_HHMMSS.log`
4. **Compression**: (Optionnel) Archive compressée en `.zip`
5. **Nouveau**: Création d'un nouveau `auto_update.log` vide
6. **Cleanup**: Suppression des anciens backups (garder seulement `MaxBackups`)

### **Exemple de Rotation**

**Avant rotation**:
```
logs/
├── auto_update.log (1 GB)
├── auto_update_20251220_020000.log (50 MB)
├── auto_update_20251213_020000.log (50 MB)
└── auto_update_20251206_020000.log (50 MB)
```

**Après rotation**:
```
logs/
├── auto_update.log (0 KB - nouveau fichier vide)
├── auto_update_20251229_020000.log (1 GB - ancien fichier archivé)
├── auto_update_20251220_020000.log (50 MB)
├── auto_update_20251213_020000.log (50 MB)
└── auto_update_20251206_020000.log (50 MB)
```

---

## 🛠️ Gestion

### **Vérifier l'État de la Tâche**

```powershell
# Vérifier si la tâche existe
Get-ScheduledTask -TaskName "LeagueStats Log Rotation"

# Voir dernière exécution
Get-ScheduledTaskInfo -TaskName "LeagueStats Log Rotation"
```

### **Lancer Manuellement**

```powershell
# Déclencher rotation immédiatement
Start-ScheduledTask -TaskName "LeagueStats Log Rotation"

# Ou lancer le script directement
.\scripts\rotate_logs.ps1
```

### **Modifier la Configuration**

```powershell
# Supprimer ancienne tâche
Unregister-ScheduledTask -TaskName "LeagueStats Log Rotation" -Confirm:$false

# Recréer avec nouveaux paramètres
.\scripts\setup_log_rotation.ps1 -MaxSizeMB 100 -Compress
```

### **Désinstaller**

```powershell
# Supprimer la tâche planifiée
Unregister-ScheduledTask -TaskName "LeagueStats Log Rotation" -Confirm:$false
```

---

## 📊 Monitoring

### **Vérifier les Logs de Rotation**

```powershell
# Voir dernières rotations
Get-Content logs\log_rotation.log -Tail 50

# Chercher erreurs
Select-String -Path logs\log_rotation.log -Pattern "ERROR|FATAL"
```

### **Exemple de Log Rotation.log**

```
[2025-12-29 02:00:00] INFO: ==================== Log Rotation Started ====================
[2025-12-29 02:00:00] INFO: Max size: 50 MB | Max backups: 5 | Compress: False
[2025-12-29 02:00:00] INFO: Current log file size: 1022.44 MB
[2025-12-29 02:00:00] INFO: Log file size (1022.44 MB) exceeds threshold (50 MB) - rotating...
[2025-12-29 02:00:01] SUCCESS: Rotated log file to: logs\auto_update_20251229_020000.log
[2025-12-29 02:00:01] SUCCESS: Created new log file: logs\auto_update.log
[2025-12-29 02:00:01] INFO: Found 2 old backup(s) to delete (keeping 5 most recent)
[2025-12-29 02:00:01] SUCCESS: Deleted old backup: auto_update_20251101_020000.log
[2025-12-29 02:00:01] SUCCESS: Deleted old backup: auto_update_20251025_020000.log
[2025-12-29 02:00:01] SUCCESS: Log rotation completed successfully
[2025-12-29 02:00:01] INFO: =============================================================
```

### **Surveiller l'Espace Disque**

```powershell
# Taille totale des logs
Get-ChildItem logs\auto_update*.log* | Measure-Object -Property Length -Sum |
    Select-Object @{Name="TotalSizeMB";Expression={[math]::Round($_.Sum / 1MB, 2)}}

# Lister tous les backups avec tailles
Get-ChildItem logs\auto_update*.log* |
    Select-Object Name, @{Name="SizeMB";Expression={[math]::Round($_.Length / 1MB, 2)}} |
    Sort-Object Name -Descending
```

---

## ⚙️ Intégration avec Auto-Update

**Ordre d'exécution recommandé** (Task Scheduler):

1. **2h00 AM**: Log Rotation (dimanche)
   - Nettoie les logs avant l'auto-update
   - Libère de l'espace disque si nécessaire

2. **3h00 AM**: Auto-Update Database (quotidien)
   - Scrape les données (12-16 min)
   - Écrit dans le nouveau `auto_update.log` propre

**Avantages**:
- ✅ Logs propres chaque semaine
- ✅ Pas de fichier géant (>1 GB)
- ✅ Historique conservé (5 derniers backups)
- ✅ Espace disque maîtrisé

---

## 🧹 Nettoyage Manuel Urgent

Si `auto_update.log` est déjà énorme (>1 GB) et que tu veux nettoyer immédiatement:

```powershell
# Option 1: Rotation manuelle immédiate
.\scripts\rotate_logs.ps1

# Option 2: Supprimer complètement et recommencer
Remove-Item logs\auto_update.log -Force
New-Item logs\auto_update.log -ItemType File

# Option 3: Garder seulement les dernières lignes
Get-Content logs\auto_update.log -Tail 1000 | Set-Content logs\auto_update_clean.log
Move-Item -Force logs\auto_update_clean.log logs\auto_update.log
```

---

## ❓ FAQ

### **Q: Quelle taille de MaxSizeMB choisir?**
**R**:
- **50 MB** (défaut): Bon compromis, ~1 mois de logs avec verbosité INFO
- **100 MB**: Si tu veux plus d'historique
- **25 MB**: Si espace disque limité

### **Q: Dois-je activer la compression?**
**R**:
- **Oui** si espace disque limité (économie ~80%)
- **Non** si tu veux lire les anciens logs facilement (pas besoin de décompresser)

### **Q: Que se passe-t-il si auto_update.log est en cours d'écriture?**
**R**: Le script échoue gracieusement et réessaiera à la prochaine exécution planifiée. C'est pourquoi on planifie la rotation 1h AVANT l'auto-update (2h AM vs 3h AM).

### **Q: Puis-je changer la fréquence de rotation?**
**R**: Oui! Relance `setup_log_rotation.ps1` avec différents paramètres:
- **Daily**: Si logs grossissent très vite
- **Weekly** (défaut): Pour la plupart des usages
- **Monthly**: Si logs restent petits

---

## 🔗 Fichiers Associés

- **Script rotation**: `scripts/rotate_logs.ps1`
- **Script setup**: `scripts/setup_log_rotation.ps1`
- **Log principal**: `logs/auto_update.log`
- **Log rotation**: `logs/log_rotation.log`
- **Backups**: `logs/auto_update_YYYYMMDD_HHMMSS.log`

---

## 📞 Support

Si problèmes avec la rotation:
1. Vérifier `logs/log_rotation.log` pour les erreurs
2. Tester manuellement: `.\scripts\rotate_logs.ps1`
3. Vérifier Task Scheduler: `Win+R` → `taskschd.msc`
4. Relancer setup si nécessaire

---

**Dernière mise à jour**: 2025-12-29
**Version**: 1.0.0
**Auteur**: @pj35 - LeagueStats Coach
