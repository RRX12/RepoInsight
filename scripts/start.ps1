param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
if (-not (Test-Path -LiteralPath "$taskRoot\.venv\Scripts\python.exe")) { throw '请先按 README 创建 .venv 并安装后端依赖。' }
if (-not (Test-Path -LiteralPath "$taskRoot\frontend\dist\index.html")) { throw '请先进入 frontend 运行 pnpm run build（或 npm run build）。' }
Write-Host "RepoCareer: http://127.0.0.1:$Port （Ctrl+C 停止）"
& "$taskRoot\.venv\Scripts\python.exe" -m uvicorn backend.app.main:app --host 127.0.0.1 --port $Port
