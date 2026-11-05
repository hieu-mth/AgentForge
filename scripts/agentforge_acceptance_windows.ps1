<#
.SYNOPSIS
  AgentForge one-pass owner acceptance, PowerShell 5.1+ / Windows CI.
.DESCRIPTION
  Default is LOCAL READ-ONLY: prints registry, owner pause, SQLite integrity,
  datasets and scheduler/backup health. No model, network, browser, OAuth,
  social publishing or process execution beyond these local Python CLIs.
  Explicit flags opt into unit tests, local unencrypted backup, or starting
  the authenticated Control Center in the foreground.
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_acceptance_windows.ps1 -RunTests
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_acceptance_windows.ps1 -CreateBackup
#>
[CmdletBinding()]
param(
    [switch]$RunTests,
    [switch]$CreateBackup,
    [switch]$StartDashboard
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$venv = Join-Path $root ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $venv -PathType Leaf) {
    $python = $venv
} else {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "No local .venv Python or PATH Python. Install Python 3.13 and pip install -e ."
    }
    $python = $command.Source
}

function Invoke-LocalCheck {
    param(
        [Parameter(Mandatory=$true)][string]$Label,
        [Parameter(Mandatory=$true)][string[]]$PythonArguments
    )
    Write-Host ""
    Write-Host ("=== " + $Label + " ===")
    & $python @PythonArguments
    if ($LASTEXITCODE -ne 0) {
        throw ("Failed: " + $Label + " (exit " + $LASTEXITCODE + ")")
    }
}

Write-Host "AgentForge Local Operations Acceptance (no remote actions)"
Write-Host ("Repository: " + $root)
Write-Host ("Python: " + $python)
Invoke-LocalCheck -Label "Skill Registry" -PythonArguments @("-m","agentforge.skill_registry","validate")
Invoke-LocalCheck -Label "Owner Dispatch State" -PythonArguments @("-m","agentforge.ops_control","status")
Invoke-LocalCheck -Label "Database / Scheduler / Backup Doctor" -PythonArguments @("-m","agentforge.ops_doctor")
Invoke-LocalCheck -Label "Existing Intelligence Datasets" -PythonArguments @("-m","agentforge.analytics_pipeline","datasets")

if ($RunTests) {
    Invoke-LocalCheck -Label "Full Python Unit/Integration Regression" -PythonArguments @("-m","unittest","discover","-s","tests","-q")
}

if ($CreateBackup) {
    Write-Warning "Backups contain UNENCRYPTED owner-local business data. Protect the archive and do not upload publicly."
    Write-Host ""
    Write-Host "=== Consented Local Backup + Integrity Verification ==="
    $raw = & $python -m agentforge.ops_backup create --confirm-backup
    if ($LASTEXITCODE -ne 0) { throw "Backup creation failed" }
    $backup = ($raw -join [Environment]::NewLine) | ConvertFrom-Json
    if ($null -eq $backup -or $backup.status -ne "CREATED_AND_VERIFIED") {
        throw "Backup did not report verified status"
    }
    Invoke-LocalCheck -Label "Verify Backup" -PythonArguments @("-m","agentforge.ops_backup","verify", [string]$backup.archive)
    Write-Host ("Created verified backup: " + $backup.archive)
}

Write-Host ""
Write-Host "Local acceptance completed. Demo data is NOT verified business revenue."
Write-Host "Owner pause/resume, deployments and external account grants remain separate."
if ($StartDashboard) {
    Write-Host "Launching local authenticated Control Center at http://127.0.0.1:8780/"
    Write-Host "Use the fresh owner code printed below; never share it in chat or screenshots."
    Invoke-LocalCheck -Label "Control Center V1" -PythonArguments @("-m","agentforge.control_center_v1","--port","8780")
}
