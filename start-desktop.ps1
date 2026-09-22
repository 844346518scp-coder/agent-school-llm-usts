# Optional desktop-window entry point. The normal launcher (CMD + start.ps1) is unchanged.
# Purpose: prepare the same project-local runtime, then open the app window via desktop.py.
# Keep this file ASCII-only: Windows PowerShell 5.1 decodes BOM-less scripts as ANSI.
param([int]$Port = 0, [switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$taskRoot = $PSScriptRoot

try {
    & (Join-Path $taskRoot 'bootstrap.ps1')
    $taskPython = Join-Path $taskRoot '.runtime/python-3.13.13/python.exe'
    if (-not (Test-Path -LiteralPath $taskPython)) {
        throw 'Project-local Python runtime is missing. Run the normal launcher once first.'
    }
    $taskArgs = @('-B', (Join-Path $taskRoot 'desktop.py'))
    if ($Port -ne 0) { $taskArgs += @('--port', "$Port") }
    if ($CheckOnly) { $taskArgs += '--check' }
    & $taskPython @taskArgs
    exit $LASTEXITCODE
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
