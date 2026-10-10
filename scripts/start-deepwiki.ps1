param([int]$Port=8002)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$sidecar=Join-Path $taskRoot 'data\deepwiki-open'
$python=Join-Path $taskRoot 'data\deepwiki-venv\Scripts\python.exe'
if(-not(Test-Path -LiteralPath $python)){throw 'DeepWiki environment is missing.'}
Copy-Item -LiteralPath (Join-Path $taskRoot 'scripts\deepwiki_archive_fallback.py') -Destination (Join-Path $sidecar 'api\archive_fallback.py') -Force
Set-Location -LiteralPath $sidecar
$env:OLLAMA_HOST='http://127.0.0.1:11434'
Remove-Item Env:DEEPWIKI_EMBEDDER_TYPE -ErrorAction SilentlyContinue
$env:NODE_ENV='production'
Write-Host "DeepWiki-Open: http://127.0.0.1:$Port / Ollama: $env:OLLAMA_HOST"
& $python -m uvicorn api.main:app --host 127.0.0.1 --port $Port

