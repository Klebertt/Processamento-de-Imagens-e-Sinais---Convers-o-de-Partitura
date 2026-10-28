$pythonProjeto = Join-Path (Split-Path $PSScriptRoot -Parent) '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonProjeto)) {
    $pythonProjeto = 'python'
}
& $pythonProjeto (Join-Path $PSScriptRoot 'main.py') @args
exit $LASTEXITCODE
