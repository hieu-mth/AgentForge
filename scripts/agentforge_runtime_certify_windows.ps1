<#
.SYNOPSIS
  Đợt 5: kiểm tra runtime AgentForge trên máy Owner (PowerShell 5.1+).
.DESCRIPTION
  Mặc định: chỉ đọc localhost, trạng thái tool và cấu hình.
  Những phép thử tạo tải thực bắt buộc có cờ xác nhận riêng:
    -RunOllama -ConfirmInference
    -RunFFmpeg -ConfirmLocalExec
    -RunDocker -ConfirmDockerRun
  Không pull model, cài package, public, sửa owner SQLite/artifact,
  hoặc tự báo production-ready.
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_runtime_certify_windows.ps1
.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\agentforge_runtime_certify_windows.ps1 -RunFFmpeg -ConfirmLocalExec -SaveReport
#>
[CmdletBinding()]
param(
    [string]$ModelRef = "local_primary",
    [switch]$RunOllama,
    [switch]$ConfirmInference,
    [switch]$RunFFmpeg,
    [switch]$ConfirmLocalExec,
    [switch]$RunDocker,
    [switch]$ConfirmDockerRun,
    [switch]$SaveReport
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($RunOllama -and -not $ConfirmInference) {
    throw "RunOllama requires ConfirmInference (one real local Ollama call)."
}
if ($RunFFmpeg -and -not $ConfirmLocalExec) {
    throw "RunFFmpeg requires ConfirmLocalExec (disposable local MP4 fixture)."
}
if ($RunDocker -and -not $ConfirmDockerRun) {
    throw "RunDocker requires ConfirmDockerRun (one pinned offline container)."
}

$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$venv = Join-Path $root ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $venv -PathType Leaf) {
    $python = $venv
} else {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "Python not found. Install Python 3.13+ and AgentForge first."
    }
    $python = $command.Source
}

$argsList = @("-B", "-m", "agentforge.ops.runtime_certification",
              "--model-ref", $ModelRef)
if ($RunOllama) { $argsList += @("--run-ollama", "--confirm-inference") }
if ($RunFFmpeg) { $argsList += @("--run-ffmpeg", "--confirm-local-exec") }
if ($RunDocker) { $argsList += @("--run-docker", "--confirm-docker-run") }
if ($SaveReport) { $argsList += "--save-report" }

Write-Host "AgentForge - Owner Runtime Evidence V1"
Write-Host "Default preflight does not invoke AI or GPU."
Write-Host "Real hardware, product QA and deployment remain Owner-certified only."
& $python @argsList
if ($LASTEXITCODE -ne 0) {
    throw ("Runtime certification probe reported failure (exit " + $LASTEXITCODE + ").")
}
