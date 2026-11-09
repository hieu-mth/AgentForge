<#
.SYNOPSIS
  M9 local AgentForge Windows setup. Default is read-only inspection.
.DESCRIPTION
  Without switches, checks versions and runs the safe Python preflight.
  -Install -AllowNetwork explicitly opts into trusted pip/npm dependency installs,
  writes only .venv, dashboard/node_modules, and dashboard/dist, and builds UI.
  Does not touch data/, workspace/, .env or model weights; does not start GPU
  tools or publish. Python package installation can contact package registries.
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup_windows.ps1 -Install -AllowNetwork
#>
[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$AllowNetwork,
    [switch]$RunTests,
    [switch]$StartDashboard
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Assert-NotRedirected {
    param([Parameter(Mandatory=$true)][string]$Path)
    if (Test-Path -LiteralPath $Path) {
        $item = Get-Item -LiteralPath $Path -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw ("Refusing symlink/junction path: " + $Path)
        }
    }
}
function Assert-Exit {
    param([string]$Label)
    if ($LASTEXITCODE -ne 0) { throw ("Failed: " + $Label + " (exit " + $LASTEXITCODE + ")") }
}

$venvDir = Join-Path $root ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$dashboard = Join-Path $root "dashboard"
foreach ($path in @($venvDir,(Join-Path $venvDir "Scripts"),$venvPython,$dashboard,(Join-Path $dashboard "node_modules"),
                    (Join-Path $dashboard "dist"))) { Assert-NotRedirected $path }
if ($AllowNetwork -and -not $Install) {
    throw "-AllowNetwork is only valid with -Install"
}
if ($StartDashboard -and -not $Install) {
    throw "StartDashboard requires explicit -Install -AllowNetwork"
}

$python = $null
if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    $python = $venvPython
} else {
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -ne $command) { $python = $command.Source }
}
if ($null -eq $python -and $Install) {
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($null -eq $launcher) { throw "Python 3.13+ is required; install it first." }
}
Write-Host "AgentForge M9 setup · local-first"
Write-Host ("Mode: " + $(if ($Install) {"CONSENTED_INSTALL"} else {"READ_ONLY"}))
$pyVersion = $null
if ($null -ne $python) {
    $pyVersion = & $python -c "import sys; print('.'.join(str(x) for x in sys.version_info[:3]))"
    Assert-Exit "Python version check"
    Write-Host ("Python: " + $pyVersion)
} else {
    Write-Warning "Python not found in PATH. Install Python 3.13+ or create .venv."
}
$node = Get-Command node.exe -ErrorAction SilentlyContinue
$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($null -ne $node) { $nodeVersion = & $node.Source --version; Assert-Exit "Node version"; Write-Host ("Node: " + $nodeVersion) }
else { Write-Warning "Node.js 22 not found." }
if ($null -ne $npm) { $npmVersion = & $npm.Source --version; Assert-Exit "npm version"; Write-Host ("npm: " + $npmVersion) }
else { Write-Warning "npm.cmd not found." }

if (-not $Install) {
    if ($null -ne $python) {
        & $python -B -m agentforge.ops.preflight
        Assert-Exit "Read-only preflight"
    }
    Write-Host "No files installed or modified by this script."
    Write-Host "To install: -Install -AllowNetwork (explicit package registry access)."
    return
}
if (-not $AllowNetwork) { throw "Network/package installation requires explicit -AllowNetwork" }
if ($null -eq $node -or $null -eq $npm -or $nodeVersion -notmatch '^v22\.') {
    throw "Node.js 22 and npm.cmd are required before installation."
}
$launcher = Get-Command py.exe -ErrorAction SilentlyContinue
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    if ($null -eq $launcher) { throw "Python 3.13 launcher py.exe is required to create .venv" }
    & $launcher.Source -3.13 -m venv $venvDir
    Assert-Exit "Create Python virtualenv"
}
$python = $venvPython
& $python -c "import sys; sys.exit(0 if sys.version_info >= (3, 13) else 2)"
Assert-Exit "Python must be 3.13+"
Write-Warning "Installing trusted project dependencies can contact package registries. No data/workspace cleanup."
& $python -m pip install -e ".[media]"
Assert-Exit "Install Python package"
& $npm.Source ci --prefix dashboard --ignore-scripts --no-audit --no-fund
Assert-Exit "Install Dashboard dependencies"
& $npm.Source run build --prefix dashboard
Assert-Exit "Build Dashboard"
& $python -B -m agentforge.ops.preflight
Assert-Exit "Local environment preflight"
if ($RunTests) {
    & $python -m unittest discover -s tests -q
    Assert-Exit "Python regression tests"
    & $npm.Source run test:navigation --prefix dashboard
    Assert-Exit "Dashboard navigation tests"
}
Write-Host "Local setup complete. Model/GPU/ComfyUI and generated app QA remain unverified."
if ($StartDashboard) {
    Write-Host "Starting authenticated local Dashboard on 127.0.0.1:8780 (Ctrl+C to stop)."
    & $python -m agentforge --port 8780
    Assert-Exit "Dashboard foreground process"
}
