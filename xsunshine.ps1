#Requires -Version 7.6
$ErrorActionPreference = 'Stop'
$pythonCommand = if ($env:XSUNSHINE_PYTHON) { $env:XSUNSHINE_PYTHON } else { 'python' }
& $pythonCommand -c 'import sys; sys.exit(0 if sys.version_info >= (3, 15) and sys.version_info.releaselevel == "final" else 1)'
if ($LASTEXITCODE -ne 0) {
    Write-Error 'Install the latest stable Python (3.15.1 or newer) or set XSUNSHINE_PYTHON to its executable.'
    exit 1
}
& $pythonCommand (Join-Path $PSScriptRoot 'run.py') @args
exit $LASTEXITCODE
