<#
.SYNOPSIS
  AgentForge one-pass owner acceptance, PowerShell 5.1+ / Windows CI.
.DESCRIPTION
  Default is LOCAL READ-ONLY: prints registry, owner pause, SQLite integrity,
  datasets and scheduler/backup health. No model, network, browser, OAuth,
  social publishing or process execution beyond these local Python CLIs.
  Explicit flags opt into isolated CI contract tests, an unencrypted local
  backup, optional non-destructive staging restore, or a foreground Dashboard.
  Machine/model runtime QA remains a manual Owner step.
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_acceptance_windows.ps1 -RunTests
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_acceptance_windows.ps1 -CreateBackup
#>
[CmdletBinding()]
param(
    [switch]$RunTests,
    [switch]$RunContractTests,
    [switch]$CreateBackup,
    [switch]$StageRestore,
    [switch]$StartDashboard
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if ($StageRestore -and -not $CreateBackup) {
    throw "-StageRestore requires explicit -CreateBackup"
}

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
Invoke-LocalCheck -Label "Base V1 readiness (not hardware acceptance)" -PythonArguments @("-B","-m","agentforge.ops.base_acceptance")

if ($RunContractTests) {
    Write-Host ""
    Write-Host "=== Isolated trusted contract suite (no real model or GPU) ==="
    Invoke-LocalCheck -Label "Base V1 contracts" -PythonArguments @(
        "-B","-m","unittest","-q",
        "tests.test_wave5_acceptance",
        "tests.test_model_hub",
        "tests.test_s4_brain",
        "tests.test_artifact_acceptance",
        "tests.test_acceptance_http",
        "tests.test_ops_reliability",
        "tests.test_ops_control"
    )
    Write-Host "Trusted local fixtures passed; Owner hardware/product QA is still UNVERIFIED."
}

if ($RunTests) {
    Invoke-LocalCheck -Label "Full Python Unit/Integration Regression" -PythonArguments @("-m","unittest","discover","-s","tests","-q")
}

if ($CreateBackup) {
    Write-Warning "Backups contain UNENCRYPTED owner-local business data. Protect the archive and do not upload publicly."
    Write-Host ""
    Write-Host "=== Consented Local Backup + Integrity Verification ==="
    $raw = & $python -B -m agentforge.ops_backup create --confirm-backup
    if ($LASTEXITCODE -ne 0) { throw "Backup creation failed" }
    $backup = ($raw -join [Environment]::NewLine) | ConvertFrom-Json
    if ($null -eq $backup -or $backup.status -ne "CREATED_AND_VERIFIED") {
        throw "Backup did not report verified status"
    }
    Invoke-LocalCheck -Label "Verify Backup" -PythonArguments @("-m","agentforge.ops_backup","verify", [string]$backup.archive)
    Write-Host ("Created verified backup: " + $backup.archive)
    if ($StageRestore) {
        Write-Warning "An UNENCRYPTED copy of the snapshot will be staged under workspace/acceptance-restore."
        Write-Warning "Do not share the restored files; review and remove them manually when safe."
        $stageRoot = Join-Path $root "workspace\acceptance-restore"
        $archiveStem = [IO.Path]::GetFileNameWithoutExtension([string]$backup.archive)
        $destination = Join-Path $stageRoot $archiveStem
        $stagedJson = & $python -B -m agentforge.ops_backup stage-restore ([string]$backup.archive) $destination --confirm-restore
        if ($LASTEXITCODE -ne 0) { throw "Staging restore failed" }
        $staged = ($stagedJson -join [Environment]::NewLine) | ConvertFrom-Json
        if ($null -eq $staged -or $staged.status -ne "RESTORED_TO_STAGING_ONLY" -or
            $staged.active_databases_overwritten -ne $false -or
            $staged.manual_owner_inspection_required -ne $true) {
            throw "Restore staging did not confirm active database preservation"
        }
        Write-Host ("Staged for Owner review (never applied): " + $staged.destination)
    }
}

Write-Host ""
Write-Host "Local acceptance completed. Demo data is NOT verified business revenue."
Write-Host "Owner pause/resume, deployments and external account grants remain separate."
if ($StartDashboard) {
    Write-Host "Launching local authenticated Control Center at http://127.0.0.1:8780/"
    Write-Host "Use the fresh owner code printed below; never share it in chat or screenshots."
    Invoke-LocalCheck -Label "Control Center V1" -PythonArguments @("-m","agentforge.control_center_v1","--port","8780")
}
