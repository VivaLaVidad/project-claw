param(
  [ValidateSet("local", "railway")]
  [string]$Mode = "railway",

  [switch]$StartCpolar,

  [string]$RailwayUrl = "https://project-claw-production.up.railway.app"
)

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Project Claw - 一键启动 ($Mode)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$python = "d:\桌面\Project Claw\maic_env\Scripts\python.exe"
$root   = "d:\桌面\Project_Claw_v14"
$edgeEnv = Join-Path $root "edge_box\.env"
$miniCfg = Join-Path $root "mini_program_app\utils\config.js"

function FailAndExit($msg) {
  Write-Host "[ERROR] $msg" -ForegroundColor Red
  exit 1
}

function Warn($msg) {
  Write-Host "[WARN]  $msg" -ForegroundColor Yellow
}

# ── 0) 前置检查 ─────────────────────────────────────────────────────
if (-not (Test-Path $root)) { FailAndExit "项目目录不存在: $root" }
if (-not (Test-Path $python)) { FailAndExit "Python 不存在: $python" }
if (-not (Test-Path $edgeEnv)) { FailAndExit "缺少 edge_box/.env，请先从 .env.example 复制并填写" }
if (-not (Test-Path $miniCfg)) { FailAndExit "缺少 mini_program_app/utils/config.js" }

$edgeText = Get-Content $edgeEnv -Raw
if ($edgeText -notmatch "MERCHANT_ID=box-001") {
  Warn "edge_box/.env 中 MERCHANT_ID 不是 box-001，建议核对。"
}
if ($edgeText -notmatch "DEEPSEEK_API_KEY=sk-") {
  Warn "edge_box/.env 中 DEEPSEEK_API_KEY 似乎未配置。"
}

$miniText = Get-Content $miniCfg -Raw
if ($Mode -eq "railway" -and $miniText -notmatch [regex]::Escape($RailwayUrl)) {
  Warn "小程序 BASE_URL 不是 $RailwayUrl，真机可能请求到旧地址。"
}

Write-Host "[OK] 前置检查通过" -ForegroundColor Green

# ── 1) 清理旧进程 ──────────────────────────────────────────────────
Write-Host "[...] 清理旧进程" -ForegroundColor Yellow
Get-Process python, uvicorn -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Write-Host "[OK] 旧进程已清理" -ForegroundColor Green

# ── 2) Hub 检查/启动 ───────────────────────────────────────────────
if ($Mode -eq "local") {
  Write-Host "[...] 启动本地 Hub :8765" -ForegroundColor Yellow
  Start-Process -FilePath $python `
    -ArgumentList "-m uvicorn cloud_server.signaling_hub:app --host 0.0.0.0 --port 8765 --log-level info" `
    -WorkingDirectory $root `
    -WindowStyle Normal
  Start-Sleep -Seconds 4

  try {
    $h = Invoke-RestMethod -Uri "http://127.0.0.1:8765/health" -TimeoutSec 8
    Write-Host "[OK] 本地 Hub 正常 merchants=$($h.merchants)" -ForegroundColor Green
  } catch {
    FailAndExit "本地 Hub 启动失败（端口占用或依赖异常）"
  }

  if ($StartCpolar) {
    Write-Host "[...] 启动 cpolar 隧道" -ForegroundColor Yellow
    Start-Process -FilePath "cpolar" -ArgumentList "http 8765" -WindowStyle Normal
    Write-Host "[OK] cpolar 已启动（请确认公网地址）" -ForegroundColor Green
  }
}
else {
  Write-Host "[...] 检查 Railway Hub" -ForegroundColor Yellow
  try {
    $h = Invoke-RestMethod -Uri "$RailwayUrl/health" -TimeoutSec 10
    Write-Host "[OK] Railway Hub 正常 merchants=$($h.merchants)" -ForegroundColor Green
  } catch {
    FailAndExit "Railway Hub 不可达：$RailwayUrl"
  }
}

# ── 3) 启动 box-001 ────────────────────────────────────────────────
Write-Host "[...] 启动 box-001" -ForegroundColor Yellow
$env:SKIP_SEMANTIC_RAG = "1"
Start-Process -FilePath $python `
  -ArgumentList "-m edge_box.main" `
  -WorkingDirectory $root `
  -WindowStyle Normal
Start-Sleep -Seconds 8
Write-Host "[OK] box-001 已启动" -ForegroundColor Green

# ── 4) 启动虚拟商家 ────────────────────────────────────────────────
Write-Host "[...] 启动虚拟商家 box-002~box-008" -ForegroundColor Yellow
Start-Process -FilePath $python `
  -ArgumentList "mock_merchants/multi_merchant_simulator.py" `
  -WorkingDirectory $root `
  -WindowStyle Normal
Start-Sleep -Seconds 6
Write-Host "[OK] 虚拟商家已启动" -ForegroundColor Green

# ── 5) 等待商家上线（最多 30 秒） ─────────────────────────────────
$healthUrl = if ($Mode -eq "local") { "http://127.0.0.1:8765/health" } else { "$RailwayUrl/health" }
$target = 8
$online = 0
for ($i = 1; $i -le 15; $i++) {
  try {
    $state = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 8
    $online = [int]$state.merchants
    Write-Host "[...] 商家上线中：$online/$target" -ForegroundColor DarkGray
    if ($online -ge $target) { break }
  } catch {}
  Start-Sleep -Seconds 2
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
if ($online -ge $target) {
  Write-Host "  启动完成，在线商家: $online" -ForegroundColor Green
} else {
  Write-Host "  启动完成，当前在线商家: $online（目标 $target）" -ForegroundColor Yellow
}
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

if ($Mode -eq "railway") {
  Write-Host "  Railway Hub: $RailwayUrl" -ForegroundColor White
} else {
  Write-Host "  本地 Hub: http://127.0.0.1:8765" -ForegroundColor White
}

Write-Host "  小程序请执行：清缓存并编译 -> 上传体验版" -ForegroundColor White
Write-Host ""