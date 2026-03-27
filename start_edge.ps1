# start_edge.ps1 - B端Agent一键启动（连接Railway云端）v2.0
# 用法: .\start_edge.ps1

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ROOT

Write-Host ""
Write-Host "  🤖  Project Claw - B端 Edge Box Agent" -ForegroundColor Yellow
Write-Host "  ─────────────────────────────────────" -ForegroundColor DarkGray

# ── 设置环境变量 ──
$env:A2A_SIGNALING_URL   = "wss://project-claw-production.up.railway.app/ws/a2a/merchant/box-001"
$env:A2A_MERCHANT_ID     = "box-001"
$env:A2A_SIGNING_SECRET  = "claw-a2a-signing-secret"

# 读取 .env 中的 DEEPSEEK_API_KEY
if (Test-Path "$ROOT\.env") {
    $envFile = Get-Content "$ROOT\.env" | Where-Object { $_ -match '^DEEPSEEK_API_KEY=' }
    if ($envFile) {
        $env:DEEPSEEK_API_KEY = ($envFile -replace '^DEEPSEEK_API_KEY=', '').Trim()
        Write-Host "  ✅  DEEPSEEK_API_KEY 已加载" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  .env 中没有 DEEPSEEK_API_KEY" -ForegroundColor Yellow
    }
} else {
    Write-Host "  ⚠️  .env 文件不存在" -ForegroundColor Yellow
}

Write-Host "  ✅  WS  -> $env:A2A_SIGNALING_URL" -ForegroundColor Cyan
Write-Host "  ✅  ID  -> $env:A2A_MERCHANT_ID" -ForegroundColor Cyan
Write-Host ""
Write-Host "  启动中，按 Ctrl+C 停止..." -ForegroundColor Gray
Write-Host ""

# ── 启动 B端 Agent ──
python -m edge_box.ws_listener
