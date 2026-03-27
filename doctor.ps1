# doctor.ps1 - Project Claw 全局健康诊断工具
# 用法: .\doctor.ps1

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ROOT
$RAILWAY = "https://project-claw-production.up.railway.app"

function Write-Check([string]$label, [bool]$ok, [string]$detail="") {
    $icon  = if ($ok) { "✅" } else { "❌" }
    $color = if ($ok) { "Green" } else { "Red" }
    $msg   = "  $icon  $label"
    if ($detail) { $msg += "  ($detail)" }
    Write-Host $msg -ForegroundColor $color
}
function Write-Warn([string]$msg) { Write-Host "  ⚠️  $msg" -ForegroundColor Yellow }
function Write-Section([string]$title) {
    Write-Host ""
    Write-Host "  ── $title ──" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "  🦞  Project Claw · 环境诊断报告" -ForegroundColor Cyan
Write-Host "  " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
Write-Host ""

# 1. Python
Write-Section "Python 环境"
try {
    $pyver = python --version 2>&1
    Write-Check "Python" $true $pyver
} catch { Write-Check "Python" $false "未安装" }

# 2. 关键依赖
Write-Section "Python 依赖"
$deps = @("fastapi","uvicorn","websockets","pydantic","streamlit","cryptography","requests","websocket")
foreach ($dep in $deps) {
    try {
        $r = python -c "import $dep; print(getattr($dep,'__version__','ok'))" 2>&1
        Write-Check $dep ($r -notmatch "Error") $r
    } catch { Write-Check $dep $false }
}

# 3. 关键文件
Write-Section "项目文件"
$files = @(
    "a2a_signaling_server.py",
    "config.py",
    "audit_broadcaster.py",
    "god_mode_dashboard.py",
    "mock_client.html",
    "edge_box/ws_listener.py",
    "start.ps1",
    "start_edge.ps1",
    "Procfile",
    "requirements.txt",
    ".env"
)
foreach ($f in $files) {
    Write-Check $f (Test-Path "$ROOT\$f")
}

# 4. 环境变量
Write-Section ".env 配置"
try {
    $env_content = Get-Content "$ROOT\.env" -Raw
    Write-Check "DEEPSEEK_API_KEY"   ($env_content -match "DEEPSEEK_API_KEY=sk-")
    Write-Check "A2A_SIGNALING_URL"  ($env_content -match "A2A_SIGNALING_URL")
    Write-Check "A2A_SIGNING_SECRET" ($env_content -match "A2A_SIGNING_SECRET")
    Write-Check "FEISHU_BOT_WEBHOOK" ($env_content -match "FEISHU_BOT_WEBHOOK=https")
} catch { Write-Warn ".env 文件不存在" }

# 5. Railway 后端
Write-Section "Railway 云端"
try {
    $res = Invoke-WebRequest -Uri "$RAILWAY/health" -TimeoutSec 8 -UseBasicParsing
    $json = $res.Content | ConvertFrom-Json
    Write-Check "Railway /health" $true "online_merchants=$($json.online_merchants)"
    Write-Check "Railway /stats"  $true "intent_total=$($json.metrics.intent_total)"
} catch {
    Write-Check "Railway" $false "无法连接，请检查部署"
    Write-Warn "尝试访问: $RAILWAY/health"
}

# 6. Git 状态
Write-Section "Git 状态"
try {
    $branch = git rev-parse --abbrev-ref HEAD 2>&1
    $commit = git log -1 --format="%h %s" 2>&1
    $status = git status --short 2>&1
    Write-Check "Git 分支"  $true $branch
    Write-Check "最新提交"  $true $commit
    if ($status) {
        Write-Warn "有未提交的改动："
        $status -split "`n" | ForEach-Object { if ($_) { Write-Host "      $_" -ForegroundColor DarkYellow } }
    } else {
        Write-Check "工作区"  $true "干净"
    }
} catch { Write-Check "Git" $false }

Write-Host ""
Write-Host "  诊断完成。如有 ❌ 请按提示修复后重新运行。" -ForegroundColor Gray
Write-Host ""
