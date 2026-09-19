# Double-click the CMD launcher, or run ./start.ps1 [-NoBrowser].
param([switch]$NoBrowser, [int]$Port = 0, [switch]$Dev, [switch]$SetupOnly)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$taskRoot = $PSScriptRoot
$taskPortablePython = Join-Path $taskRoot 'runtime/python.exe'
if (Test-Path -LiteralPath (Join-Path $taskRoot 'portable-manifest.json')) {
    if (-not (Test-Path -LiteralPath $taskPortablePython)) {
        Write-Host 'ERROR: Portable runtime missing. Extract the complete portable ZIP first.' -ForegroundColor Red
        exit 1
    }
    $taskPortableArgs = @('-B', (Join-Path $taskRoot 'backend/app/platform/portable.py'), '--port', "$Port")
    if ($NoBrowser) { $taskPortableArgs += '--no-browser' }
    & $taskPortablePython @taskPortableArgs
    exit $LASTEXITCODE
}
if (-not $Dev) {
    try {
        & (Join-Path $taskRoot 'bootstrap.ps1')
        if ($SetupOnly) { exit 0 }
        $taskSourceArgs = @('-B', (Join-Path $taskRoot 'backend/app/platform/portable.py'), '--source', '--port', "$Port")
        if ($NoBrowser) { $taskSourceArgs += '--no-browser' }
        & (Join-Path $taskRoot '.runtime/python-3.13.13/python.exe') @taskSourceArgs
        exit $LASTEXITCODE
    } catch {
        Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}
$taskPython = Join-Path $taskRoot '.venv/Scripts/python.exe'
$taskFrontend = Join-Path $taskRoot 'frontend'
$taskBackendUrl = 'http://127.0.0.1:8000/api/health'
$taskFrontendUrl = 'http://127.0.0.1:5173/'
$taskExpectedTitle = [regex]::Match((Get-Content -LiteralPath (Join-Path $taskFrontend 'index.html') -Raw -Encoding UTF8), '<title>.*?</title>').Value

function Test-TaskPort([int]$Port) {
    $taskSocket = [System.Net.Sockets.TcpClient]::new()
    try { $taskSocket.Connect('127.0.0.1', $Port); return $true }
    catch { return $false }
    finally { $taskSocket.Dispose() }
}

function Test-TaskHealth([string]$Url) {
    try {
        $taskResponse = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        $taskHealth = $taskResponse.Content | ConvertFrom-Json
        return ($taskHealth.status -eq 'ok' -and $taskHealth.agent_mode -in @('demo', 'live') -and $taskHealth.version -eq '0.2.0' -and $taskHealth.agent_version -eq '0.2.0' -and $taskHealth.teaching_version -eq '0.3.0' -and $taskHealth.schema_version -eq 3)
    } catch { return $false }
}

function Test-TaskFrontend {
    try {
        $taskResponse = Invoke-WebRequest -Uri $taskFrontendUrl -UseBasicParsing -TimeoutSec 2
        # Vite returns text/html without charset; Windows PowerShell 5.1 otherwise
        # decodes Chinese as Latin-1. Read the page's UTF-8 bytes explicitly.
        $taskHtml = [Text.Encoding]::UTF8.GetString($taskResponse.RawContentStream.ToArray())
        return ($taskExpectedTitle -and $taskResponse.StatusCode -eq 200 -and $taskHtml.Contains($taskExpectedTitle))
    } catch { return $false }
}

function Wait-TaskReady([string]$Kind, [System.Diagnostics.Process]$Process) {
    $taskDeadline = [DateTime]::UtcNow.AddSeconds(45)
    do {
        $Process.Refresh()
        if ($Process.HasExited) { throw "$Kind exited before becoming ready. See $Kind/server.err.log and $Kind/server.out.log." }
        $taskReady = if ($Kind -eq 'backend') { Test-TaskHealth $taskBackendUrl } else { Test-TaskFrontend }
        if ($taskReady) { return }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $taskDeadline)
    throw "$Kind did not become ready within 45 seconds. Check $Kind/server.err.log and $Kind/server.out.log."
}

# Serialize double-clicks so two launchers do not start the same service at once.
$taskHasher = [System.Security.Cryptography.SHA256]::Create()
$taskHash = [BitConverter]::ToString($taskHasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($taskRoot.ToLowerInvariant()))).Replace('-', '').Substring(0, 16)
$taskHasher.Dispose()
$taskMutex = [System.Threading.Mutex]::new($false, "Local\ShubanLauncher-$taskHash")
$taskLockHeld = $false
try {
    try { $taskLockHeld = $taskMutex.WaitOne(0) }
    catch [System.Threading.AbandonedMutexException] { $taskLockHeld = $true }
    if (-not $taskLockHeld) { Write-Output 'SHUBAN is already starting. Please wait for the first launcher.'; exit 0 }

    Write-Output 'Starting SHUBAN...'
    $taskBackendRunning = Test-TaskPort 8000
    $taskFrontendRunning = Test-TaskPort 5173
    if ($taskBackendRunning -and -not (Test-TaskHealth $taskBackendUrl)) {
        throw 'Port 8000 is occupied, but a healthy SHUBAN backend was not found. No process was stopped.'
    }
    if ($taskFrontendRunning -and -not (Test-TaskFrontend)) {
        throw 'Port 5173 is occupied, but a SHUBAN page was not found. No process was stopped.'
    }
    if (-not $taskBackendRunning) {
        if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Source checkout: Python environment missing. Testers should use the portable ZIP; developers should follow README.md.' }
    }
    if (-not $taskFrontendRunning) {
        if (-not (Test-Path -LiteralPath (Join-Path $taskFrontend 'node_modules/vite/bin/vite.js'))) { throw 'Source checkout: frontend dependencies missing. Testers should use the portable ZIP; developers run npm ci in frontend. See README.md.' }
        $taskNodeCommand = Get-Command node -ErrorAction SilentlyContinue
        if (-not $taskNodeCommand) { throw 'Node.js was not found. Install Node.js 22.12+ and reopen the launcher.' }
        $taskNode = $taskNodeCommand.Source
    }

    if (-not $taskBackendRunning) {
        $taskBackendProcess = Start-Process -FilePath $taskPython -ArgumentList @('-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', '8000') -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskRoot 'backend/server.out.log') -RedirectStandardError (Join-Path $taskRoot 'backend/server.err.log') -PassThru
        Write-Output "Backend process: $($taskBackendProcess.Id)"
        Wait-TaskReady 'backend' $taskBackendProcess
    } else { Write-Output 'Backend is ready; reusing the existing service.' }

    if (-not $taskFrontendRunning) {
        $taskFrontendProcess = Start-Process -FilePath $taskNode -ArgumentList @('node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '5173', '--strictPort') -WorkingDirectory $taskFrontend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskFrontend 'server.out.log') -RedirectStandardError (Join-Path $taskFrontend 'server.err.log') -PassThru
        Write-Output "Frontend process: $($taskFrontendProcess.Id)"
        Wait-TaskReady 'frontend' $taskFrontendProcess
    } else { Write-Output 'Frontend is ready; reusing the existing service.' }

    if (-not (Test-TaskHealth ($taskFrontendUrl + 'api/health'))) { throw 'The page is running, but its backend proxy is unavailable. Check frontend/server.err.log.' }
    Write-Output "Ready: $taskFrontendUrl"
    Write-Output 'Services stay running in the background after this launcher closes.'
    if (-not $NoBrowser) { Start-Process -FilePath $taskFrontendUrl }
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
} finally {
    if ($taskLockHeld) { $taskMutex.ReleaseMutex() }
    $taskMutex.Dispose()
}
