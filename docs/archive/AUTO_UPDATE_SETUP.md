# Auto-Update Database Setup Guide

> **⚠️ Automatisation suspendue par choix (@pj35, depuis mars 2026)** — la mise à
> jour des données est manuelle (`python scripts/update_all.py` ou le menu 3 de
> l'application), voir `README.md`. Ce guide décrit `scripts/auto_update_db.py`,
> l'**ancien** orchestrateur (Task Scheduler, ~3h du matin) — superseded par
> `scripts/update_all.py` (pas de tâche planifiée équivalente aujourd'hui).
> Conservé comme référence si l'automatisation nocturne est un jour réactivée,
> auquel cas la tâche planifiée devrait pointer vers `update_all.py` plutôt que
> vers le script décrit ci-dessous (`docs/archive/BACKLOG_2026_08.md`, section
> "Si un jour l'automatisation nocturne reprend").

## 📋 Overview

The LeagueStats Coach auto-update system automatically updates your champion matchup database daily using **parallel scraping** (12 minutes execution time). This eliminates manual database maintenance and ensures you always have fresh data.

**Features**:
- ⚡ **Fast**: 12 minutes execution (87% faster than sequential)
- 🔕 **Silent**: Runs in background with low priority (no PC blocking)
- 🔔 **Notifications**: Windows toast notifications on success/failure
- 📊 **Logging**: Detailed logs for debugging (`logs/auto_update.log`)
- ⏰ **Scheduled**: Runs daily at 3 AM (customizable)
- 🎯 **Smart**: Detects patch changes, skips unnecessary updates

---

## ⚙️ Prerequisites

**Required**:
- ✅ Windows 10/11
- ✅ Python 3.13+
- ✅ LeagueStats Coach installed
- ✅ **Tâche #4 completed** (Web Scraping Parallèle)

**Optional**:
- 🔔 `win10toast` for notifications (highly recommended)

---

## 🚀 Quick Setup (3 steps)

### Step 1: Install Dependencies

```bash
# Install win10toast for notifications (optional but recommended)
pip install win10toast

# Verify installation
python scripts/test_auto_update.py
```

**Expected output**:
```
✅ All core components are functional
✅ ParallelParser ready for auto-update
```

---

### Step 2: Configure Task Scheduler

**Run PowerShell as Administrator** and execute:

```powershell
# Navigate to project root
cd C:\path\to\LeagueStats

# Run setup script
.\scripts\setup_auto_update.ps1
```

**Interactive prompts**:
1. **Schedule time**: Enter time (e.g., `03:00` for 3 AM)
2. **Test now?**: Type `y` to test immediately (optional)

**Example output**:
```
SUCCESS! Auto-update task created successfully

Task Details:
  Name: LeagueStats Auto-Update
  Schedule: Daily at 03:00
  Priority: Low (background execution)
  Duration: ~12 minutes
```

---

### Step 3: Verify Setup

**Check Task Scheduler**:
```powershell
# Open Task Scheduler GUI
taskschd.msc

# Find task: "LeagueStats Auto-Update"
# Verify: Next Run Time shows tomorrow at 3 AM
```

**Test manually**:
```powershell
# Test the scheduled task (runs in background)
Start-ScheduledTask -TaskName "LeagueStats Auto-Update"

# Check logs for progress
Get-Content logs\auto_update.log -Tail 20 -Wait
```

---

## 📂 File Structure

```
LeagueStats/
├── scripts/
│   ├── auto_update_db.py           # Main auto-update script
│   ├── setup_auto_update.ps1        # Task Scheduler setup
│   └── test_auto_update.py          # Dry-run test script
├── logs/
│   └── auto_update.log              # Operation logs
└── data/
    └── db.db                         # Main database
```

---

## ⚙️ Configuration

The auto-update script uses hardcoded settings optimized for most use cases:

**Default Settings**:
- **Workers**: 10 parallel workers (optimal for i5-14600KF multi-core CPUs)
- **Patch**: "14" (rolling 14-day window, always up-to-date)
- **Schedule**: Daily at 3 AM (configured via `setup_auto_update.ps1`)
- **Priority**: BELOW_NORMAL (background execution, no PC blocking)
- **Notifications**: Enabled (Windows toast on success/failure)
- **Logging**: Enabled (`logs/auto_update.log`)

**To customize**:
- **Change schedule time**: Re-run `setup_auto_update.ps1`
- **Disable notifications**: Modify `scripts/auto_update_db.py` line 144 (`enabled=False`)
- **Change worker count**: Modify `scripts/auto_update_db.py` line 175 (`max_workers=10`)

---

## 🔍 Monitoring & Troubleshooting

### Check Auto-Update Status

**View logs**:
```powershell
# View latest logs
Get-Content logs\auto_update.log -Tail 50

# Watch logs in real-time
Get-Content logs\auto_update.log -Tail 20 -Wait
```

**Check Task Scheduler status**:
```powershell
# Get task info
Get-ScheduledTask -TaskName "LeagueStats Auto-Update"

# View last run result
Get-ScheduledTaskInfo -TaskName "LeagueStats Auto-Update"
```

---

### Common Issues

#### ❌ Issue: "Python executable not found"

**Solution**:
```powershell
# Find Python location
Get-Command python.exe | Select-Object -ExpandProperty Source

# Update setup_auto_update.ps1 with correct path
# Or add Python to PATH environment variable
```

---

#### ❌ Issue: "win10toast not installed"

**Solution**:
```bash
pip install win10toast

# Verify
python -c "import win10toast; print('OK')"
```

---

#### ❌ Issue: Task fails with "Access Denied"

**Solution**:
- Ensure Task Scheduler was created with Administrator privileges
- Re-run `setup_auto_update.ps1` as Administrator
- Check that user has permission to write to `logs/` directory

---

#### ❌ Issue: Firefox windows stay open after scraping

**Solution**:
- This is expected during execution (10 Firefox windows for 10 workers)
- Windows close automatically after scraping completes
- If windows persist, check `logs/auto_update.log` for errors

---

## 🎯 Manual Execution

### Test Auto-Update (Dry Run)

**Quick test** (no scraping):
```bash
python scripts/test_auto_update.py
```

**Full execution** (~12 minutes):
```bash
python scripts/auto_update_db.py
```

**Expected log output**:
```
[2025-12-21 03:00:00] START: Auto-update process started
[2025-12-21 03:00:01] INFO: Checking for new patch version...
[2025-12-21 03:00:01] INFO: Using rolling 14-day window (always update)
[2025-12-21 03:00:02] INFO: Starting parallel scraping of 172 champions...
[2025-12-21 03:00:02] INFO: Estimated time: ~12 minutes (background process)
...
[2025-12-21 03:12:15] SUCCESS: Scraping completed in 12.2 minutes
[2025-12-21 03:12:15] INFO: Champions parsed: 171/172 succeeded, 1 failed
[2025-12-21 03:12:20] SUCCESS: Champion scores recalculated
[2025-12-21 03:12:20] SUCCESS: Auto-update completed successfully in 12.3 minutes
```

---

## 🛠️ Advanced Configuration

### Change Schedule Time

```powershell
# Option 1: Re-run setup script
.\scripts\setup_auto_update.ps1

# Option 2: Modify existing task
$trigger = New-ScheduledTaskTrigger -Daily -At "05:00"
Set-ScheduledTask -TaskName "LeagueStats Auto-Update" -Trigger $trigger
```

---

### Disable Auto-Update

```powershell
# Disable task (keeps configuration)
Disable-ScheduledTask -TaskName "LeagueStats Auto-Update"

# Re-enable later
Enable-ScheduledTask -TaskName "LeagueStats Auto-Update"

# Completely remove task
Unregister-ScheduledTask -TaskName "LeagueStats Auto-Update" -Confirm:$false
```

---

### Run on Specific Days Only

```powershell
# Example: Mondays and Fridays only
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Friday -At "03:00"
Set-ScheduledTask -TaskName "LeagueStats Auto-Update" -Trigger $trigger
```

---

## 📊 Performance Metrics

**Expected performance** (i5-14600KF, 32GB RAM):
- **Execution time**: 10-15 minutes (average: 12 min)
- **Worker count**: 10 parallel workers
- **Success rate**: ~99% (171/172 champions typically succeed)
- **CPU usage**: ~50% (low priority, no PC blocking)
- **RAM usage**: ~3 GB (10 × 300 MB per Firefox instance)
- **Network**: ~500 MB data transfer

**Comparison with sequential scraping**:
- Sequential: 90-120 minutes
- Parallel: 12 minutes
- **Improvement**: **87% faster** ⚡

---

## 🔐 Security & Privacy

**Data collected**:
- ✅ Champion matchup statistics from LoLalytics (public data)
- ✅ Logs stored locally only (`logs/auto_update.log`)

**No data sent**:
- ❌ No personal information collected
- ❌ No usage telemetry
- ❌ No external APIs (except LoLalytics scraping)

**Process priority**:
- Script runs at `BELOW_NORMAL` priority
- Does not block other applications
- Safe to run in background while gaming/working

---

## ❓ FAQ

### Q: Can I run auto-update while using LeagueStats?

**A**: Yes, but not recommended during draft.
- Auto-update clears matchup tables during import
- Wait for draft to finish before running
- Scheduled at 3 AM to avoid conflicts

---

### Q: What happens if my PC is off at 3 AM?

**A**: Task will run at next available time.
- Task Scheduler option: "Start when available"
- Will execute when PC turns on
- Alternatively, change schedule time to when PC is always on

---

### Q: How do I know if auto-update succeeded?

**A**: Check notifications and logs.
- ✅ Success: Green notification "BD mise à jour avec succès!"
- ❌ Failure: Red notification "Échec mise à jour BD"
- 📊 Details: Check `logs/auto_update.log`

---

### Q: Can I customize which champions are scraped?

**A**: Yes, edit `auto_update_db.py`:
```python
# Line ~180: Change SOLOQ_POOL to custom list
champion_pool = ["Aatrox", "Ahri", "Jinx"]  # Your custom pool
```

---

### Q: Will auto-update work with future patches?

**A**: Yes, patch "14" is rolling window.
- `patch_version = "14"` means "last 14 days"
- Automatically includes latest patch data
- No manual updates needed

---

## 📚 Related Documentation

- [TODO.md](../TODO.md) - Full task backlog (Tâche #11 details)
- [CLAUDE.md](../CLAUDE.md) - Development workflow
- [CHANGELOG.md](../CHANGELOG.md) - Version history

---

## 🆘 Support

**Issues?**
1. Check `logs/auto_update.log` for errors
2. Run `python scripts/test_auto_update.py` for diagnostics
3. Review Task Scheduler Last Run Result
4. Report issue with log file attached

**Contact**: @pj35 - LeagueStats Coach

---

**Version**: 1.1.0-dev
**Last Updated**: 2025-12-21
**Sprint**: Sprint 2 - Tâche #11 (Auto-Update BD)
