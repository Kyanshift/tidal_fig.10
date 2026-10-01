$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$sourceRoot = Join-Path $projectRoot 'vendor\reboundx'
$wheelRoot = Join-Path $projectRoot 'artifacts\wheels'

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Existing .venv Python was not found: $venvPython"
}
& $venvPython -c 'import rebound, setuptools, wheel; print("Building against REBOUND", rebound.__version__)'
if ($LASTEXITCODE -ne 0) { throw 'Install setuptools and wheel in .venv first.' }
New-Item -ItemType Directory -Force -Path $wheelRoot | Out-Null

# Recompile every C source against the current REBOUND headers and DLL.
$previousForceBuild = $env:REBX_FORCE_BUILD
try {
    $env:REBX_FORCE_BUILD = '1'
    & $venvPython -m pip wheel $sourceRoot --no-build-isolation --no-deps --no-cache-dir --wheel-dir $wheelRoot
    if ($LASTEXITCODE -ne 0) { throw 'MSVC wheel build failed.' }
} finally {
    $env:REBX_FORCE_BUILD = $previousForceBuild
}
$wheelFile = Join-Path $wheelRoot 'reboundx-5.1.0-cp312-cp312-win_amd64.whl'
if (-not (Test-Path -LiteralPath $wheelFile)) { throw 'Expected Python 3.12 x64 wheel was not created.' }
& $venvPython -m pip install --no-index --no-deps --force-reinstall $wheelFile
if ($LASTEXITCODE -ne 0) { throw 'Wheel installation failed.' }
& $venvPython (Join-Path $PSScriptRoot 'verify_reboundx_msvc.py')
if ($LASTEXITCODE -ne 0) { throw 'REBOUNDx verification failed.' }
& $venvPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency validation failed.' }
