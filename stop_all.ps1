$ErrorActionPreference = "SilentlyContinue"

Write-Host "[1/3] 停止 8765 端口 API 进程..." -ForegroundColor Cyan
$listenPids = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique
foreach ($procId in $listenPids) {
  taskkill /PID $procId /F | Out-Null
}

Write-Host "[2/3] 停止 8501 端口 Dashboard 进程..." -ForegroundColor Cyan
$dashPids = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique
foreach ($procId in $dashPids) {
  taskkill /PID $procId /F | Out-Null
}

Write-Host "[3/3] 停止 Redis 容器 claw-redis..." -ForegroundColor Cyan
docker stop claw-redis | Out-Null

Write-Host "完成。" -ForegroundColor Green
