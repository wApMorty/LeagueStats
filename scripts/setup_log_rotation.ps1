<#
.SYNOPSIS
    Setup Windows Task Scheduler for automatic log rotation.

.DESCRIPTION
    This script creates a scheduled task to rotate logs automatically.
    Default schedule: Weekly on Sunday at 2:00 AM (before auto-update at 3:00 AM)

.PARAMETER TaskName
    Name of the scheduled task (default: "LeagueStats Log Rotation")

.PARAMETER Schedule
    When to run rotation: Daily, Weekly, or Monthly (default: Weekly)

.PARAMETER Time
    Time to run rotation in HH:MM format (default: 02:00)

.PARAMETER DayOfWeek
    For Weekly schedule: Sunday, Monday, etc. (default: Sunday)

.PARAMETER MaxSizeMB
    Maximum log size before rotation (default: 50 MB)

.PARAMETER MaxBackups
    Number of backup files to keep (default: 5)

.PARAMETER Compress
    If set, compress old backups to save disk space

.EXAMPLE
    .\scripts\setup_log_rotation.ps1
    Setup weekly rotation on Sunday at 2:00 AM (default)

.EXAMPLE
    .\scripts\setup_log_rotation.ps1 -Schedule Daily -Time "01:00"
    Setup daily rotation at 1:00 AM

.EXAMPLE
    .\scripts\setup_log_rotation.ps1 -MaxSizeMB 100 -MaxBackups 10 -Compress
    Setup with custom parameters (100 MB max, 10 backups, compression)

.NOTES
    Author: @pj35 - LeagueStats Coach
    Version: 1.0.0
    Requires: Administrator privileges
#>

param(
    [string]$TaskName = "LeagueStats Log Rotation",
    [ValidateSet("Daily", "Weekly", "Monthly")]
    [string]$Schedule = "Weekly",
    [string]$Time = "02:00",
    [ValidateSet("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")]
    [string]$DayOfWeek = "Sunday",
    [int]$MaxSizeMB = 50,
    [int]$MaxBackups = 5,
    [switch]$Compress
)

# Check if running as Administrator
$CurrentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = New-Object Security.Principal.WindowsPrincipal($CurrentUser)
$IsAdmin = $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $IsAdmin) {
    Write-Host ""
    Write-Host "ERROR: This script requires Administrator privileges!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please run PowerShell as Administrator and try again." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Right-click PowerShell > Run as Administrator" -ForegroundColor Cyan
    Write-Host ""
    exit 1
}

Write-Host ""
Write-Host "==================== LeagueStats Log Rotation Setup ====================" -ForegroundColor Cyan
Write-Host ""

# Get project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

# Paths
$RotateScriptPath = Join-Path $ScriptDir "rotate_logs.ps1"
$PythonwPath = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source

Write-Host "Project root: $ProjectRoot" -ForegroundColor Gray
Write-Host "Rotate script: $RotateScriptPath" -ForegroundColor Gray
Write-Host ""

# Verify rotate script exists
if (-not (Test-Path $RotateScriptPath)) {
    Write-Host "ERROR: rotate_logs.ps1 not found at $RotateScriptPath" -ForegroundColor Red
    exit 1
}

# Build PowerShell command with parameters
$PSCommand = "powershell.exe"
$PSArgs = "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$RotateScriptPath`""
$PSArgs += " -MaxSizeMB $MaxSizeMB -MaxBackups $MaxBackups"
if ($Compress) {
    $PSArgs += " -Compress"
}

Write-Host "Task configuration:" -ForegroundColor Yellow
Write-Host "  Task Name: $TaskName" -ForegroundColor White
Write-Host "  Schedule: $Schedule" -ForegroundColor White
if ($Schedule -eq "Weekly") {
    Write-Host "  Day: $DayOfWeek" -ForegroundColor White
}
Write-Host "  Time: $Time" -ForegroundColor White
Write-Host "  Max Size: $MaxSizeMB MB" -ForegroundColor White
Write-Host "  Max Backups: $MaxBackups" -ForegroundColor White
Write-Host "  Compress: $Compress" -ForegroundColor White
Write-Host ""

# Ask for confirmation
$Confirmation = Read-Host "Create this scheduled task? (Y/N)"
if ($Confirmation -ne "Y" -and $Confirmation -ne "y") {
    Write-Host ""
    Write-Host "Setup cancelled by user." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "Creating scheduled task..." -ForegroundColor Cyan

try {
    # Check if task already exists
    $ExistingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

    if ($ExistingTask) {
        Write-Host ""
        Write-Host "WARNING: Task '$TaskName' already exists!" -ForegroundColor Yellow
        $Overwrite = Read-Host "Do you want to overwrite it? (Y/N)"

        if ($Overwrite -ne "Y" -and $Overwrite -ne "y") {
            Write-Host ""
            Write-Host "Setup cancelled. Existing task not modified." -ForegroundColor Yellow
            exit 0
        }

        # Delete existing task
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Deleted existing task." -ForegroundColor Gray
    }

    # Create task action
    $Action = New-ScheduledTaskAction -Execute $PSCommand -Argument $PSArgs -WorkingDirectory $ProjectRoot

    # Create task trigger based on schedule
    switch ($Schedule) {
        "Daily" {
            $Trigger = New-ScheduledTaskTrigger -Daily -At $Time
        }
        "Weekly" {
            $Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $DayOfWeek -At $Time
        }
        "Monthly" {
            $Trigger = New-ScheduledTaskTrigger -Monthly -At $Time
        }
    }

    # Create task settings
    $Settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable:$false `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

    # Create task principal (run with highest privileges, whether user logged in or not)
    $Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Highest

    # Register task
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "Rotate LeagueStats auto-update logs to prevent excessive disk usage" | Out-Null

    Write-Host ""
    Write-Host "SUCCESS: Scheduled task created!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Task details:" -ForegroundColor Cyan
    Write-Host "  Name: $TaskName" -ForegroundColor White
    Write-Host "  Schedule: $Schedule at $Time" -ForegroundColor White
    if ($Schedule -eq "Weekly") {
        Write-Host "  Day: $DayOfWeek" -ForegroundColor White
    }
    Write-Host "  Status: Ready" -ForegroundColor White
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "  1. Verify task in Task Scheduler: Win+R > taskschd.msc" -ForegroundColor White
    Write-Host "  2. Test rotation manually: " -ForegroundColor White
    Write-Host "     Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor Cyan
    Write-Host "  3. Check rotation log: logs\log_rotation.log" -ForegroundColor White
    Write-Host ""
    Write-Host "Logs will be rotated when auto_update.log exceeds $MaxSizeMB MB" -ForegroundColor Gray
    Write-Host "Keeping $MaxBackups most recent backups" -ForegroundColor Gray
    Write-Host ""

    exit 0
}
catch {
    Write-Host ""
    Write-Host "ERROR: Failed to create scheduled task!" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    exit 1
}
