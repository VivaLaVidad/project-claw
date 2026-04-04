param(
  [switch]$NoStartHub
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$ConfigFile = Join-Path $Root "mini_program_app\utils\config.js"

function Wait-Health {
  param([string]$Url, [int]$MaxSeconds = 45)
  $deadline = (Get-Date).AddSeconds($MaxSeconds)
  while ((Get-Date) -lt $deadline) {
    try {
      return Invoke-RestMethod -Uri $Url -TimeoutSec 3
    } catch {
      Start-Sleep -Seconds 1
    }
  }
  return $null
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Project Claw MiniApp 本地一键启动" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-Path $Python)) {
  Write-Host "[ERROR] 未找到虚拟环境 Python: $Python" -ForegroundColor Red
  Write-Host "请先执行: python -m venv .venv" -ForegroundColor Yellow
  exit 1
}

if (-not (Test-Path $ConfigFile)) {
  Write-Host "[ERROR] 未找到配置文件: $ConfigFile" -ForegroundColor Red
  exit 1
}

# 1) 固定小程序 BASE_URL 为本地
$config = Get-Content $ConfigFile -Raw -Encoding UTF8
$newConfig = [regex]::Replace($config, "const\s+BASE_URL\s*=\s*'[^']*';", "const BASE_URL = 'http://127.0.0.1:8765';")
Set-Content -Path $ConfigFile -Value $newConfig -Encoding UTF8
Write-Host "[OK ] 小程序 BASE_URL 已切到 http://127.0.0.1:8765" -ForegroundColor Green

if (-not $NoStartHub) {
  # 2) 重启本地 Hub（避免旧进程残留）
  Get-Process python, uvicorn -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  Start-Sleep -Seconds 1

  $hubCmd = "`$env:LEDGER_ENABLED='0'; `$env:CLEARING_ENABLED='0'; `$env:SEMANTIC_CACHE_ENABLED='0'; `$env:DATABASE_URL='sqlite+aiosqlite:///./project_claw_local.db'; cd '$Root'; & '$Python' -m uvicorn cloud_server.signaling_hub:app --host 127.0.0.1 --port 8765"
  Start-Process powershell -ArgumentList "-NoExit", "-Command", $hubCmd | Out-Null

  Write-Host "[... ] 等待 Hub 就绪" -ForegroundColor Yellow
  $health = Wait-Health -Url "http://127.0.0.1:8765/health" -MaxSeconds 90
  if (-not $health) {
    Write-Host "[ERROR] Hub 未就绪，请查看新打开的 Hub 窗口日志" -ForegroundColor Red
    exit 1
  }
  Write-Host "[OK ] Hub 已就绪 merchants=$($health.merchants)" -ForegroundColor Green
}

Write-Host ""
Write-Host "✅ MiniApp 本地联调准备完成" -ForegroundColor Green
Write-Host "1) 微信开发者工具中重新编译小程序" -ForegroundColor White
Write-Host "2) 控制台执行（清旧缓存）：" -ForegroundColor White
Write-Host "   wx.removeStorageSync('claw_base_url_override')" -ForegroundColor Gray
Write-Host "   wx.removeStorageSync('claw_token')" -ForegroundColor Gray
Write-Host "3) 确认接口基址为: http://127.0.0.1:8765" -ForegroundColor White
Write-Host ""
Write-Host "快速检查: iwr http://127.0.0.1:8765/health" -ForegroundColor Cyan
Write-Host ""