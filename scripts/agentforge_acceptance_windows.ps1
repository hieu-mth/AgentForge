<#
.SYNOPSIS
  Owner local acceptance for AgentForge Video Studio (PowerShell 5.1+).
.DESCRIPTION
  Default checks only source/config and current pause state. Unit/contract
  regressions and Dashboard startup are explicit. No model inference, GPU
  jobs, network calls, publishing or changes to Owner data by default.
#>
[CmdletBinding()]
param(
    [switch]$RunTests,
    [switch]$RunContractTests,
    [switch]$StartDashboard
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$venv = Join-Path $root ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $venv -PathType Leaf) {
    $python = $venv
} else {
    $found = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $found) { throw "Python 3.13+ not found" }
    $python = $found.Source
}

function Invoke-CheckedPython {
    param([Parameter(Mandatory=$true)][string[]]$Arguments)
    & $python @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python check failed (exit $LASTEXITCODE)" }
}

Write-Host "AgentForge Video Studio — local acceptance"
Invoke-CheckedPython -Arguments @("-B","-m","agentforge.ops.preflight")
Invoke-CheckedPython -Arguments @("-B","-m","agentforge.ops_control","status")

if ($RunContractTests) {
    Invoke-CheckedPython -Arguments @("-B","-m","unittest","-q",
        "tests.test_owner_auth_video_foundation",
        "tests.test_video_projects",
        "tests.test_character_registry",
        "tests.test_film_motion_comfy",
        "tests.test_motion_runtime",
        "tests.test_film_production",
        "tests.test_film_publishing",
        "tests.test_runtime_certification",
        "tests.test_video_backend_boundary",
        "tests.test_ops_control")
    Write-Host "Contract fixtures passed; GPU and video playback remain Owner-unverified."
}
if ($RunTests) {
    Invoke-CheckedPython -Arguments @("-B","-m","unittest","discover","-s","tests","-q")
}
if ($StartDashboard) {
    Write-Host "Starting localhost Dashboard: http://127.0.0.1:8780/"
    Invoke-CheckedPython -Arguments @("-m","agentforge","--port","8780")
}
