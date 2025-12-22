# =============================================================================
# LeagueStats Coach - Auto-Update Task Scheduler Setup
# =============================================================================
# This script creates a Windows Task Scheduler task to automatically update
# the champion database daily at 3 AM using the ParallelParser.
#
# REQUIREMENTS:
# - Administrator privileges (for Task Scheduler)
# - Python 3.13+ installed
# - LeagueStats Coach installed
# - Web Scraping Parallèle (Tâche #4) completed
#
# USAGE:
#   Run as Administrator:
#   .\scripts\setup_auto_update.ps1
#
# Author: @pj35 - LeagueStats Coach
# Version: 1.1.0-dev
# =============================================================================

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "ERROR: This script must be run as Administrator!" -ForegroundColor Red
    Write-Host "Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    pause
    exit 1
}

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "LeagueStats Coach - Auto-Update Task Scheduler Setup" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host ""

# Detect project root directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$autoUpdateScript = Join-Path $projectRoot "scripts\auto_update_db.py"

Write-Host "[INFO] Project root: $projectRoot" -ForegroundColor Gray
Write-Host "[INFO] Auto-update script: $autoUpdateScript" -ForegroundColor Gray

# Check if auto_update_db.py exists
if (-not (Test-Path $autoUpdateScript)) {
    Write-Host "ERROR: auto_update_db.py not found at $autoUpdateScript" -ForegroundColor Red
    pause
    exit 1
}

Write-Host "[OK] Auto-update script found" -ForegroundColor Green
Write-Host ""

# Find Python executable
$pythonPaths = @(
    "C:\Python313\pythonw.exe",
    "C:\Python312\pythonw.exe",
    "C:\Users\$env:USERNAME\AppData\Local\Programs\Python\Python313\pythonw.exe",
    "C:\Users\$env:USERNAME\AppData\Local\Programs\Python\Python312\pythonw.exe",
    (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source,
    (Get-Command python.exe -ErrorAction SilentlyContinue).Source
)

$pythonExe = $null
foreach ($path in $pythonPaths) {
    if ($path -and (Test-Path $path)) {
        $pythonExe = $path
        break
    }
}

if (-not $pythonExe) {
    Write-Host "ERROR: Python executable not found!" -ForegroundColor Red
    Write-Host "Please install Python 3.13+ or specify path manually" -ForegroundColor Yellow
    pause
    exit 1
}

Write-Host "[OK] Python found: $pythonExe" -ForegroundColor Green

# Prefer pythonw.exe (no console window)
if ($pythonExe -like "*python.exe" -and (Test-Path ($pythonExe -replace "python.exe", "pythonw.exe"))) {
    $pythonExe = $pythonExe -replace "python.exe", "pythonw.exe"
    Write-Host "[INFO] Using pythonw.exe (no console window)" -ForegroundColor Gray
}

Write-Host ""

# Configuration
$taskName = "LeagueStats Auto-Update"
$taskDescription = "Automatically updates LeagueStats Coach champion database daily using parallel scraping (12min background process)"

# Prompt for schedule time
Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "Schedule Configuration" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "When should the auto-update run?" -ForegroundColor Yellow
Write-Host "  Recommended: 3 AM (low PC usage time)" -ForegroundColor Gray
Write-Host "  Duration: ~12 minutes (background process, low priority)" -ForegroundColor Gray
Write-Host ""

$scheduleTime = Read-Host "Enter time (HH:MM format, e.g., 03:00)"

if (-not $scheduleTime -or $scheduleTime -notmatch "^\d{1,2}:\d{2}$") {
    Write-Host "Invalid time format, using default: 03:00" -ForegroundColor Yellow
    $scheduleTime = "03:00"
}

Write-Host "[OK] Schedule time: $scheduleTime" -ForegroundColor Green
Write-Host ""

# Create scheduled task action
Write-Host "[INFO] Creating scheduled task..." -ForegroundColor Gray

$action = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument "`"$autoUpdateScript`"" `
    -WorkingDirectory $projectRoot

# Create daily trigger at specified time
$trigger = New-ScheduledTaskTrigger `
    -Daily `
    -At $scheduleTime

# Create settings with background execution options
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -Priority 7 `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

# Create principal (run whether user is logged in or not)
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType S4U `
    -RunLevel Highest

# Register the task (delete if exists)
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "[INFO] Removing existing task..." -ForegroundColor Gray
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -Description $taskDescription `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Force | Out-Null

    Write-Host ""
    Write-Host "==============================================================================" -ForegroundColor Green
    Write-Host "SUCCESS! Auto-update task created successfully" -ForegroundColor Green
    Write-Host "==============================================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Task Details:" -ForegroundColor Cyan
    Write-Host "  Name: $taskName" -ForegroundColor White
    Write-Host "  Schedule: Daily at $scheduleTime" -ForegroundColor White
    Write-Host "  Script: $autoUpdateScript" -ForegroundColor White
    Write-Host "  Python: $pythonExe" -ForegroundColor White
    Write-Host "  Priority: Low (background execution)" -ForegroundColor White
    Write-Host "  Duration: ~12 minutes" -ForegroundColor White
    Write-Host ""
    Write-Host "Next Steps:" -ForegroundColor Cyan
    Write-Host "  1. Task will run daily at $scheduleTime automatically" -ForegroundColor White
    Write-Host "  2. Check logs at: $projectRoot\logs\auto_update.log" -ForegroundColor White
    Write-Host "  3. Test manually: Right-click task in Task Scheduler → Run" -ForegroundColor White
    Write-Host "  4. Disable/Enable: Use Task Scheduler GUI (taskschd.msc)" -ForegroundColor White
    Write-Host ""
    Write-Host "To test the task now:" -ForegroundColor Yellow
    Write-Host "  Start-ScheduledTask -TaskName '$taskName'" -ForegroundColor Gray
    Write-Host ""

    # Ask if user wants to test now
    $testNow = Read-Host "Do you want to test the auto-update now? (y/N)"
    if ($testNow -eq 'y' -or $testNow -eq 'Y') {
        Write-Host ""
        Write-Host "[INFO] Starting auto-update task (background)..." -ForegroundColor Gray
        Write-Host "[INFO] Check logs/auto_update.log for progress" -ForegroundColor Gray
        Start-ScheduledTask -TaskName $taskName
        Write-Host "[OK] Task started! Check Task Scheduler for status" -ForegroundColor Green
    }

} catch {
    Write-Host ""
    Write-Host "ERROR: Failed to create scheduled task!" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    pause
    exit 1
}

Write-Host ""
Write-Host "Press any key to exit..." -ForegroundColor Gray
pause
