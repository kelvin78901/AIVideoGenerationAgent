# Modified for AI Drama Studio: starts the backend (`drama-studio dev`) + `pnpm -C web dev` (no pip / npm).
# AI Drama Studio launcher (Windows PowerShell)
# Usage (the execution policy on this machine blocks running .ps1 files directly):
#   powershell -ExecutionPolicy Bypass -File .\start.ps1                       # backend + web
#   powershell -ExecutionPolicy Bypass -File .\start.ps1 -NoWeb                # backend only
#   powershell -ExecutionPolicy Bypass -File .\start.ps1 -Port 8001 -SkipInstall
#
# The backend always binds 127.0.0.1. Mock adapters are the default; set $env:DRAMA_MOCK = "0"
# to call real models.

[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$NoWeb,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

# .env (KEY=VALUE lines) for upstream settings such as COMFYUI_URL / FFMPEG_PATH.
# API keys belong in the keyring (Models page); the backend also reads .env as a fallback.
$EnvFile = Join-Path $Root ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $idx = $line.IndexOf("=")
        if ($idx -lt 1) { return }
        $key = $line.Substring(0, $idx).Trim()
        $val = $line.Substring($idx + 1).Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($key, $val, "Process")
    }
}
$env:DRAMA_SERIES_ROOT = $Root
if (-not $env:COMFYUI_URL) { $env:COMFYUI_URL = "http://127.0.0.1:8188" }
$env:DRAMA_BACKEND_URL = "http://127.0.0.1:$Port"   # Vite proxies /api here
$env:COREPACK_ENABLE_DOWNLOAD_PROMPT = "0"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv not found. Install it: winget install --id astral-sh.uv -e"
}
if (-not $NoWeb -and -not (Get-Command corepack -ErrorAction SilentlyContinue)) {
    throw "corepack not found. Install Node.js 24 (it ships corepack), or run with -NoWeb."
}

if (-not $SkipInstall) {
    Write-Host "[Setup] uv sync"
    & uv sync
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }
    if (-not $NoWeb) {
        Write-Host "[Setup] pnpm install (web/)"
        & corepack pnpm -C web install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw "pnpm install failed in web/" }
    }
}

$mock = if ($env:DRAMA_MOCK -eq "0") { "off (real models)" } else { "on" }
Write-Host "========================================"
Write-Host "  AI Drama Studio"
Write-Host "========================================"
Write-Host "  API:   http://127.0.0.1:$Port   (docs: /docs)"
if (-not $NoWeb) { Write-Host "  Web:   http://127.0.0.1:5173" }
Write-Host "  Mock:  $mock"
Write-Host "  Comfy: $env:COMFYUI_URL"
Write-Host "  Ctrl+C to stop"
Write-Host "========================================"

$webProc = $null
try {
    if (-not $NoWeb) {
        Write-Host "[Starting] web workbench (pnpm -C web dev)"
        # corepack is corepack.cmd on Windows; start it through cmd.exe.
        $webProc = Start-Process -FilePath "cmd.exe" `
            -ArgumentList "/c", "corepack", "pnpm", "-C", "web", "dev" `
            -WorkingDirectory $Root -PassThru -NoNewWindow
    }
    # `python -m`, not the drama-studio.exe entry point: Windows Application Control may block it.
    Write-Host "[Starting] backend (uv run python -m drama_series_agent.studio_cli dev)"
    & uv run python -m drama_series_agent.studio_cli dev --port $Port
}
finally {
    if ($webProc -and -not $webProc.HasExited) {
        # Kill cmd + the node/vite tree under it.
        & taskkill.exe /PID $webProc.Id /T /F 2>$null | Out-Null
    }
}
