<#
.SYNOPSIS
    Log rotation script for LeagueStats Coach auto-update logs.

.DESCRIPTION
    This script manages log file rotation to prevent auto_update.log from growing too large.
    - Rotates log file when it exceeds maximum size
    - Keeps a configurable number of backup files
    - Optionally compresses old backups to save disk space
    - Can be scheduled via Task Scheduler (daily or weekly)

.PARAMETER MaxSizeMB
    Maximum size of auto_update.log before rotation (default: 50 MB)

.PARAMETER MaxBackups
    Maximum number of backup files to keep (default: 5)

.PARAMETER Compress
    If set, compress old log files to .zip format to save space

.PARAMETER LogRotationFile
    Path to log rotation operations log (default: logs/log_rotation.log)

.EXAMPLE
    .\scripts\rotate_logs.ps1
    Rotate with default settings (50 MB max, 5 backups, no compression)

.EXAMPLE
    .\scripts\rotate_logs.ps1 -MaxSizeMB 100 -MaxBackups 10 -Compress
    Rotate at 100 MB, keep 10 backups, compress old files

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File "scripts\rotate_logs.ps1"
    Run from Task Scheduler

.NOTES
    Author: @pj35 - LeagueStats Coach
    Version: 1.0.0
    Compatible with: Windows 10/11, PowerShell 5.1+
#>

param(
    [int]$MaxSizeMB = 50,
    [int]$MaxBackups = 5,
    [switch]$Compress,
    [string]$LogRotationFile = "logs\log_rotation.log"
)

# Get project root (script is in scripts/ subdirectory)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

# Paths
$LogFile = Join-Path $ProjectRoot "logs\auto_update.log"
$LogDir = Join-Path $ProjectRoot "logs"
$RotationLog = Join-Path $ProjectRoot $LogRotationFile

# Create logs directory if doesn't exist
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

# Function to write to rotation log
function Write-RotationLog {
    param([string]$Message, [string]$Level = "INFO")

    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogEntry = "[$Timestamp] $Level: $Message"

    # Write to console
    Write-Host $LogEntry

    # Write to rotation log file
    Add-Content -Path $RotationLog -Value $LogEntry
}

# Start rotation process
Write-RotationLog "==================== Log Rotation Started ====================" "INFO"
Write-RotationLog "Max size: $MaxSizeMB MB | Max backups: $MaxBackups | Compress: $Compress" "INFO"

# Check if log file exists
if (-not (Test-Path $LogFile)) {
    Write-RotationLog "Log file not found: $LogFile (nothing to rotate)" "INFO"
    exit 0
}

# Get current log file size
$LogFileSize = (Get-Item $LogFile).Length
$LogFileSizeMB = [math]::Round($LogFileSize / 1MB, 2)

Write-RotationLog "Current log file size: $LogFileSizeMB MB" "INFO"

# Check if rotation is needed
if ($LogFileSizeMB -lt $MaxSizeMB) {
    Write-RotationLog "Log file size ($LogFileSizeMB MB) is below threshold ($MaxSizeMB MB) - no rotation needed" "INFO"
    exit 0
}

Write-RotationLog "Log file size ($LogFileSizeMB MB) exceeds threshold ($MaxSizeMB MB) - rotating..." "INFO"

# Generate backup filename with timestamp
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupFile = Join-Path $LogDir "auto_update_$Timestamp.log"

try {
    # Rotate: Rename current log to backup
    Move-Item -Path $LogFile -Destination $BackupFile -Force
    Write-RotationLog "Rotated log file to: $BackupFile" "SUCCESS"

    # Create new empty log file
    New-Item -ItemType File -Path $LogFile | Out-Null
    Write-RotationLog "Created new log file: $LogFile" "SUCCESS"

    # Compress backup if requested
    if ($Compress) {
        $ZipFile = "$BackupFile.zip"
        try {
            Compress-Archive -Path $BackupFile -DestinationPath $ZipFile -Force
            Remove-Item $BackupFile -Force
            Write-RotationLog "Compressed backup to: $ZipFile" "SUCCESS"
            $BackupFile = $ZipFile
        }
        catch {
            Write-RotationLog "Failed to compress backup: $_" "WARNING"
        }
    }

    # Clean up old backups (keep only MaxBackups)
    $BackupPattern = "auto_update_*.log"
    if ($Compress) {
        $BackupPattern = "auto_update_*.log.zip"
    }

    $AllBackups = Get-ChildItem -Path $LogDir -Filter $BackupPattern |
                  Sort-Object LastWriteTime -Descending

    $BackupsToDelete = $AllBackups | Select-Object -Skip $MaxBackups

    if ($BackupsToDelete) {
        Write-RotationLog "Found $($BackupsToDelete.Count) old backup(s) to delete (keeping $MaxBackups most recent)" "INFO"

        foreach ($OldBackup in $BackupsToDelete) {
            try {
                Remove-Item $OldBackup.FullName -Force
                Write-RotationLog "Deleted old backup: $($OldBackup.Name)" "SUCCESS"
            }
            catch {
                Write-RotationLog "Failed to delete backup $($OldBackup.Name): $_" "ERROR"
            }
        }
    }
    else {
        Write-RotationLog "No old backups to delete (current count: $($AllBackups.Count))" "INFO"
    }

    Write-RotationLog "Log rotation completed successfully" "SUCCESS"
    Write-RotationLog "=============================================================" "INFO"
    exit 0
}
catch {
    Write-RotationLog "FATAL: Log rotation failed: $_" "ERROR"
    Write-RotationLog "=============================================================" "INFO"
    exit 1
}
