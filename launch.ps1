$ErrorActionPreference = 'Stop'

$appPath = Join-Path $PSScriptRoot 'app.py'
if (-not (Test-Path -LiteralPath $appPath -PathType Leaf)) {
    Write-Error 'app.py was not found next to this launcher.'
    exit 1
}

$launcher = Get-Command py.exe -ErrorAction SilentlyContinue
$pythonArgs = @('-3', $appPath)
if (-not $launcher) {
    $launcher = Get-Command python.exe -ErrorAction SilentlyContinue
    $pythonArgs = @($appPath)
}
if (-not $launcher) {
    Write-Error 'Python 3.10 or newer is required. Install Python and try again.'
    exit 1
}

Push-Location -LiteralPath $PSScriptRoot
try {
    & $launcher.Source @pythonArgs
    $appExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $appExitCode
