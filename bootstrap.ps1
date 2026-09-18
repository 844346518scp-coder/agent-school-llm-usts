# Project-local, pinned runtime setup for a source ZIP. No admin/global PATH changes.
param([switch]$SetupOnly)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$env:PSModulePath = (Join-Path $PSHOME 'Modules') + [IO.Path]::PathSeparator + $env:PSModulePath
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$taskRoot = $PSScriptRoot
$taskRuntime = Join-Path $taskRoot '.runtime'
if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64' -or $env:PROCESSOR_ARCHITEW6432 -eq 'ARM64') {
    throw 'Automatic setup currently supports Windows 10/11 x64 (Intel/AMD). See README.md for manual setup.'
}
New-Item -ItemType Directory -Force -Path $taskRuntime | Out-Null
$taskCache = Join-Path $taskRuntime 'downloads'
New-Item -ItemType Directory -Force -Path $taskCache | Out-Null

function Get-VerifiedDownload([string]$Name, [string]$Url, [string]$Sha) {
    $target = Join-Path $taskCache $Name
    if ((Test-Path -LiteralPath $target) -and (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -eq $Sha) { return $target }
    $partial = "$target.partial"
    Write-Host "Downloading $Name (first run requires internet)..."
    try {
        Invoke-WebRequest -Uri $Url -OutFile $partial -UseBasicParsing -TimeoutSec 180
        if ((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash -ne $Sha) {
            throw "Checksum mismatch for $Name. Download was not executed."
        }
        Move-Item -LiteralPath $partial -Destination $target -Force
    } catch { throw "Cannot prepare $Name. Check network access to $Url and retry. $($_.Exception.Message)" }
    return $target
}

function Invoke-Checked([string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Setup command failed (exit $LASTEXITCODE). See the output above, fix the network/dependency issue and double-click again." }
}

# One installer per source directory; never allow pip/npm to race another launcher.
$taskHasher = [Security.Cryptography.SHA256]::Create()
$taskHash = [BitConverter]::ToString($taskHasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($taskRoot.ToLowerInvariant()))).Replace('-', '')
$taskHasher.Dispose()
$taskMutex = [Threading.Mutex]::new($false, "Local\ShubanSetup-$taskHash")
$taskHeld = $false
$taskOldPath = $env:PATH
$taskOldTemp = $env:TEMP
$taskOldTmp = $env:TMP
$taskOldNpmCache = $env:npm_config_cache
try {
    try { $taskHeld = $taskMutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $taskHeld = $true }
    if (-not $taskHeld) { throw 'SHUBAN setup is already running for this folder. Wait for the first launcher to finish.' }
    $taskTemp = Join-Path $taskRuntime 'temp'
    New-Item -ItemType Directory -Force -Path $taskTemp | Out-Null
    $env:TEMP = $taskTemp; $env:TMP = $taskTemp
    $env:npm_config_cache = Join-Path $taskRuntime 'npm-cache'

    $taskPythonDir = Join-Path $taskRuntime 'python-3.13.13'
    $taskPython = Join-Path $taskPythonDir 'python.exe'
    if (-not (Test-Path -LiteralPath (Join-Path $taskPythonDir '.complete'))) {
        $archive = Get-VerifiedDownload 'python-3.13.13.zip' 'https://www.python.org/ftp/python/3.13.13/python-3.13.13-embed-amd64.zip' '8766a8775746235e23cf5aee5027ab1060bb981d93110577adcf3508aa0cbd55'
        Expand-Archive -LiteralPath $archive -DestinationPath $taskPythonDir -Force
        Set-Content -LiteralPath (Join-Path $taskPythonDir '.complete') -Value '3.13.13' -Encoding ASCII
    }
    $taskNodeDir = Join-Path $taskRuntime 'node-v22.23.2-win-x64'
    $taskNode = Join-Path $taskNodeDir 'node.exe'
    if (-not (Test-Path -LiteralPath (Join-Path $taskNodeDir '.complete'))) {
        $archive = Get-VerifiedDownload 'node-v22.23.2.zip' 'https://nodejs.org/dist/v22.23.2/node-v22.23.2-win-x64.zip' '1177b4137ba5adaa56354ae40f1080c7450e8ae09cecb47da459d1c52ac99f97'
        Expand-Archive -LiteralPath $archive -DestinationPath $taskRuntime -Force
        Set-Content -LiteralPath (Join-Path $taskNodeDir '.complete') -Value '22.23.2' -Encoding ASCII
    }
    $env:PATH = "$taskNodeDir;$taskPythonDir;$taskOldPath"
    $taskLock = Join-Path $taskRoot 'backend/requirements.lock.txt'
    $taskDepsHash = (Get-FileHash -LiteralPath $taskLock -Algorithm SHA256).Hash.ToLowerInvariant()
    $taskDepsName = "deps-py313-$taskDepsHash"
    $taskDeps = Join-Path $taskRuntime $taskDepsName
    [IO.File]::WriteAllLines((Join-Path $taskPythonDir 'python313._pth'), [string[]]@('python313.zip', '.', $taskDeps, $taskRoot), [Text.UTF8Encoding]::new($false))
    if (-not (Test-Path -LiteralPath (Join-Path $taskDeps '.complete'))) {
        $pip = Get-VerifiedDownload 'pip-26.2.1.zip' 'https://files.pythonhosted.org/packages/f3/6e/1736e5b4ae2b778ef2f81c47d797de9f891d4d8acb047a24ca37a60294dd/pip-26.2.1-py3-none-any.whl' '71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e'
        $taskPipDir = Join-Path $taskRuntime 'pip-26.2.1'
        Expand-Archive -LiteralPath $pip -DestinationPath $taskPipDir -Force
        [IO.File]::AppendAllText((Join-Path $taskPythonDir 'python313._pth'), "$taskPipDir`n", [Text.UTF8Encoding]::new($false))
        Write-Host 'Installing locked Python dependencies...'
        Invoke-Checked $taskPython @('-m', 'pip', '--isolated', 'install', '--cache-dir', (Join-Path $taskRuntime 'pip-cache'), '--disable-pip-version-check', '--no-warn-script-location', '--only-binary=:all:', '--upgrade', '--target', $taskDeps, '-r', $taskLock)
        Set-Content -LiteralPath (Join-Path $taskDeps '.complete') -Value $taskDepsHash -Encoding ASCII
    }
    try {
        Invoke-Checked $taskPython @('-B', '-c', 'import fastapi, uvicorn, sqlalchemy, pydantic, httpx, dotenv, sqlite3, backend.app.ai.config')
    } catch {
        Remove-Item -LiteralPath (Join-Path $taskDeps '.complete') -ErrorAction SilentlyContinue
        throw 'Python dependency check failed. Double-click again to repair the project-local dependencies.'
    }
    Write-Host 'Python dependencies ready.'

    $taskFrontend = Join-Path $taskRoot 'frontend'
    $taskNpmHash = (Get-FileHash -LiteralPath (Join-Path $taskFrontend 'package-lock.json') -Algorithm SHA256).Hash
    $taskNpmStamp = Join-Path $taskRuntime 'npm-lock.sha256'
    $taskNeedNpm = -not (Test-Path -LiteralPath $taskNpmStamp)
    if (-not $taskNeedNpm) { $taskNeedNpm = (Get-Content -LiteralPath $taskNpmStamp -Raw).Trim() -ne $taskNpmHash }
    if (-not (Test-Path -LiteralPath (Join-Path $taskFrontend 'node_modules/vite/bin/vite.js'))) { $taskNeedNpm = $true }
    Push-Location $taskFrontend
    try {
        if ($taskNeedNpm) {
            $taskEsbuildPath = Join-Path $taskFrontend 'node_modules/@esbuild/win32-x64/esbuild.exe'
            $taskBusyBuild = Get-CimInstance Win32_Process -Filter "Name = 'esbuild.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.ExecutablePath -eq $taskEsbuildPath.Replace('/', '\') }
            if ($taskBusyBuild) { throw 'This folder has an active Vite/build process. Stop its development server before installing dependencies, then retry.' }
            Write-Host 'Installing frontend dependencies...'
            Invoke-Checked $taskNode @((Join-Path $taskNodeDir 'node_modules/npm/bin/npm-cli.js'), 'ci', '--no-audit', '--no-fund')
            Set-Content -LiteralPath $taskNpmStamp -Value $taskNpmHash -Encoding ASCII
        }
        $taskInputs = @(Get-ChildItem -LiteralPath (Join-Path $taskFrontend 'src') -Recurse -File) + @(Get-Item 'package.json','package-lock.json','index.html','vite.config.ts','tsconfig.json')
        $taskSignature = ($taskInputs | Sort-Object FullName | ForEach-Object { $_.FullName.Substring($taskFrontend.Length) + ':' + (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }) -join "`n"
        $taskBuildStamp = Join-Path $taskRuntime 'frontend-build.txt'
        $taskNeedBuild = -not (Test-Path -LiteralPath $taskBuildStamp)
        if (-not $taskNeedBuild) { $taskNeedBuild = (Get-Content -LiteralPath $taskBuildStamp -Raw).TrimEnd() -ne $taskSignature }
        if (-not (Test-Path -LiteralPath (Join-Path $taskFrontend 'dist/index.html'))) { $taskNeedBuild = $true }
        if ($taskNeedBuild) {
            Write-Host 'Building the web app...'
            Invoke-Checked $taskNode @((Join-Path $taskNodeDir 'node_modules/npm/bin/npm-cli.js'), 'run', 'build')
            Set-Content -LiteralPath $taskBuildStamp -Value $taskSignature -Encoding UTF8
        }
    } finally { Pop-Location }
    Write-Host 'Source folder setup complete.'
} finally {
    $env:PATH = $taskOldPath; $env:TEMP = $taskOldTemp; $env:TMP = $taskOldTmp; $env:npm_config_cache = $taskOldNpmCache
    if ($taskHeld) { $taskMutex.ReleaseMutex() }
    $taskMutex.Dispose()
}
