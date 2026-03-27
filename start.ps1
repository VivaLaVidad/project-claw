# start.ps1 - Project Claw 一键启动脚本 v3.0
# 用法: .\start.ps1 [local|cloud|dashboard|edge|all]
# 示例: .\start.ps1 all

param(
    [string]$Mode = "all"
)

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ROOT

$RAILWAY_URL = "https://project-claw-production.up.railway.app"
$RAILWAY_WSS  = "wss://project-claw-production.up.railway.app"

function Write-Header {
    Clear-Host
    Write-Host "" 
    Write-Host "  ╔══════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║   🦞  Project Claw  ·  A2A 智能买手系统     ║" -ForegroundColor Cyan
    Write-Host "  ║        工业级商业版 v3.0  by VivaLaVidad     ║" -ForegroundColor Cyan
    Write-Host "  ╚══════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Test-Backend {
    try {
        $res = Invoke-WebRequest -Uri "$RAILWAY_URL/health" -TimeoutSec 5 -UseBasicParsing
        $json = $res.Content | ConvertFrom-Json
        return $json.online_merchants
    } catch { return -1 }
}

function Start-Dashboard {
    Write-Host "  [3] 启动上帝视角大屏..." -ForegroundColor Green
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$ROOT'; Write-Host '🖥️  Streamlit 大屏 → http://localhost:8501' -ForegroundColor Green; streamlit run god_mode_dashboard.py --server.headless false"
    )
    Start-Sleep 3
}

function Start-Edge {
    Write-Host "  [2] 启动 B端 Edge Box Agent..." -ForegroundColor Yellow
    $envBlock = @"
\$env:A2A_SIGNALING_URL = '$RAILWAY_WSS/ws/a2a/merchant/box-001'
\$env:A2A_MERCHANT_ID   = 'box-001'
\$env:A2A_SIGNING_SECRET = 'claw-a2a-signing-secret'
"
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$ROOT'; `$env:A2A_SIGNALING_URL='$RAILWAY_WSS/ws/a2a/merchant/box-001'; `$env:A2A_MERCHANT_ID='box-001'; `$env:A2A_SIGNING_SECRET='claw-a2a-signing-secret'; Write-Host '🤖  B端Agent 连接中...' -ForegroundColor Yellow; python -m edge_box.ws_listener"
    )
    Start-Sleep 2
}

function Start-LocalHub {
    Write-Host "  [1] 启动本地 Hub (signaling server)..." -ForegroundColor Magenta
    Start-Process powershell -ArgumentList @(
        "-NoExit",
        "-Command",
        "Set-Location '$ROOT'; Write-Host '☁️  本地 Hub → http://localhost:8765' -ForegroundColor Magenta; python run_stack.py signaling"
    )
    Start-Sleep 3
}

function Open-Client {
    Write-Host "  [4] 打开 C端演示页..." -ForegroundColor Blue
    Start-Process "$ROOT\mock_client.html"
    Start-Sleep 1
}

function Show-Summary {
    param([int]$OnlineMerchants)
    Write-Host ""
    Write-Host "  ┌─────────────────────────────────────────────┐" -ForegroundColor DarkGray
    Write-Host "  │  ✅  所有服务已启动                          │" -ForegroundColor Green
    Write-Host "  ├─────────────────────────────────────────────┤" -ForegroundColor DarkGray
    Write-Host "  │  ☁️  Railway Hub   $RAILWAY_URL" -ForegroundColor Cyan
    Write-Host "  │  🖥️  上帝视角      http://localhost:8501" -ForegroundColor Cyan
    Write-Host "  │  🌐  Streamlit云  https://project-claw-fh4zqu77uvcyrmqx8tsr7u.streamlit.app" -ForegroundColor Cyan
    if ($OnlineMerchants -ge 0) {
        Write-Host "  │  🤖  在线商家     $OnlineMerchants 个" -ForegroundColor $(if ($OnlineMerchants -gt 0) {'Green'} else {'Red'})
    }
    Write-Host "  └─────────────────────────────────────────────┘" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  路演提示：" -ForegroundColor Yellow
    Write-Host "  1. 双击 mock_client.html → 召唤龙虾买手" -ForegroundColor White
    Write-Host "  2. 查看上帝视角大屏 http://localhost:8501" -ForegroundColor White
    Write-Host "  3. 扫码体验微信小程序（需审核后上线）" -ForegroundColor White
    Write-Host ""
}

# ── 主流程 ──
Write-Header

switch ($Mode.ToLower()) {
    "local" {
        Write-Host "  模式: 纯本地（不依赖 Railway）" -ForegroundColor Magenta
        Start-LocalHub
        Start-Edge
        Start-Dashboard
        Open-Client
        Show-Summary -OnlineMerchants 0
    }
    "edge" {
        Write-Host "  模式: 仅启动 B端Agent（连接 Railway）" -ForegroundColor Yellow
        Start-Edge
        Write-Host "  B端Agent 已启动，等待 C端发起请求..." -ForegroundColor Green
    }
    "dashboard" {
        Write-Host "  模式: 仅启动上帝视角大屏" -ForegroundColor Green
        Start-Dashboard
        Write-Host "  大屏已启动 → http://localhost:8501" -ForegroundColor Green
    }
    "cloud" {
        Write-Host "  模式: 云端模式（Railway Hub + 本地 B端 + 大屏）" -ForegroundColor Cyan
        Write-Host "  [0] 检查 Railway 后端..." -ForegroundColor Gray
        $merchants = Test-Backend
        if ($merchants -eq -1) {
            Write-Host "  ⚠️  Railway 后端不可达，请检查部署" -ForegroundColor Red
        } else {
            Write-Host "  ✅  Railway 在线，当前商家: $merchants" -ForegroundColor Green
        }
        Start-Edge
        Start-Dashboard
        Open-Client
        Start-Sleep 3
        $merchants2 = Test-Backend
        Show-Summary -OnlineMerchants $merchants2
    }
    default {
        # all = 完整启动
        Write-Host "  模式: 完整启动（推荐路演用）" -ForegroundColor Cyan
        Write-Host "  [0] 检查 Railway 后端..." -ForegroundColor Gray
        $merchants = Test-Backend
        if ($merchants -ge 0) {
            Write-Host "  ✅  Railway 在线，在线商家: $merchants" -ForegroundColor Green
        } else {
            Write-Host "  ⚠️  Railway 不可达，切换本地 Hub" -ForegroundColor Yellow
            Start-LocalHub
        }
        Start-Edge
        Start-Dashboard
        Open-Client
        Start-Sleep 5
        $merchants2 = if ($merchants -ge 0) { Test-Backend } else { 0 }
        Show-Summary -OnlineMerchants $merchants2
    }
}
