param([int]$Port = 8000, [switch]$Install, [switch]$SetupOnly)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $Program (exit $LASTEXITCODE)" }
}
$python = Join-Path $taskRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Invoke-Checked -Program 'python' -Arguments @('-m','venv','.venv')
    $Install = $true
}
if ($Install) { Invoke-Checked -Program $python -Arguments @('-m','pip','install','-r','backend/requirements.lock.txt') }
if ($Install -or -not (Test-Path -LiteralPath 'frontend/node_modules')) {
    Invoke-Checked -Program 'pnpm' -Arguments @('--dir','frontend','install','--frozen-lockfile')
}
if ($Install -or -not (Test-Path -LiteralPath 'frontend/dist/index.html')) {
    Invoke-Checked -Program 'pnpm' -Arguments @('--dir','frontend','run','build')
}
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
    Write-Host 'Created .env. Configure models before running real analysis (see README).'
}
if ($SetupOnly) { Write-Host 'Application dependencies ready. Configure/start DeepWiki separately (README).'; exit 0 }
Write-Host "RepoInsight: http://127.0.0.1:$Port (Ctrl+C to stop)"
Invoke-Checked -Program $python -Arguments @('-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port',"$Port")
