# start_all.ps1 - Project Claw 一键启动脚本 v1.0
# 启动所有服务：signaling + siri + edge_box + 微信开发者工具

param(
    [switch]$NoWechat  # 不启动微信开发者工具
)

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$PYTHON = 'D:\Python1\python.exe'

Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║         Project Claw 一键启动 v1.0                        ║" -ForegroundColor Cyan
Write-Host "║  启动服务：signaling + siri + edge_box + 微信开发者工具   ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# 检查 Python
if (-not (Test-Path $PYTHON)) {
    $PYTHON = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $PYTHON) {
        Write-Host "❌ 未找到 Python，请先安装 Python 3.11+" -ForegroundColor Red
        exit 1
    }
}
Write-Host "✓ Python: $PYTHON" -ForegroundColor Green

# 清理占用端口
Write-Host ""
Write-Host "🔧 清理占用端口..." -ForegroundColor Yellow
$ports = @(8765, 8010)
foreach ($port in $ports) {
    $result = netstat -ano | Select-String ":$port " | Select-Object -First 1
    if ($result) {
        $pid = $result -split '\s+' | Select-Object -Last 1
        taskkill /F /PID $pid 2>$null | Out-Null
        Write-Host "  ✓ 已释放端口 $port (PID=$pid)" -ForegroundColor Green
    }
}
Start-Sleep -Seconds 1

# 启动 signaling + siri
Write-Host ""
Write-Host "🚀 启动 signaling + siri..." -ForegroundColor Cyan
$signaling_cmd = "cd '$ROOT'; python run_stack.py signaling siri"
$signaling_window = New-Object System.Diagnostics.ProcessStartInfo
$signaling_window.FileName = "powershell.exe"
$signaling_window.Arguments = "-NoExit", "-Command", $signaling_cmd
$signaling_window.UseShellExecute = $true
$signaling_window.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
$signaling_proc = [System.Diagnostics.Process]::Start($signaling_window)
Write-Host "  ✓ signaling + siri 已启动 (PID=$($signaling_proc.Id))" -ForegroundColor Green
Write-Host "  📍 signaling: http://127.0.0.1:8765" -ForegroundColor Gray
Write-Host "  📍 siri:      http://127.0.0.1:8010" -ForegroundColor Gray

# 等待 signaling 就绪
Write-Host ""
Write-Host "⏳ 等待 signaling 就绪..." -ForegroundColor Yellow
$max_wait = 30
$waited = 0
while ($waited -lt $max_wait) {
    try {
        $health = Invoke-WebRequest -Uri "http://127.0.0.1:8765/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($health.StatusCode -eq 200) {
            Write-Host "  ✓ signaling 已就绪" -ForegroundColor Green
            break
        }
    } catch {}
    Start-Sleep -Seconds 1
    $waited++
}
if ($waited -ge $max_wait) {
    Write-Host "  ⚠️  signaling 启动超时，继续启动其他服务..." -ForegroundColor Yellow
}

# 启动 edge_box (B端 Agent)
Write-Host ""
Write-Host "🤖 启动 B端 Agent (edge_box)..." -ForegroundColor Cyan
$edge_cmd = "cd '$ROOT'; .\start_edge.ps1"
$edge_window = New-Object System.Diagnostics.ProcessStartInfo
$edge_window.FileName = "powershell.exe"
$edge_window.Arguments = "-NoExit", "-Command", $edge_cmd
$edge_window.UseShellExecute = $true
$edge_window.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
$edge_proc = [System.Diagnostics.Process]::Start($edge_window)
Write-Host "  ✓ B端 Agent 已启动 (PID=$($edge_proc.Id))" -ForegroundColor Green
Write-Host "  📍 WS: ws://127.0.0.1:8765/ws/a2a/merchant/box-001" -ForegroundColor Gray

# 启动微信开发者工具
if (-not $NoWechat) {
    Write-Host ""
    Write-Host "📱 启动微信开发者工具..." -ForegroundColor Cyan
    $wechat_path = "C:\Program Files (x86)\Tencent\微信web开发者工具\cli.exe"
    if (Test-Path $wechat_path) {
        & $wechat_path open --project "$ROOT\miniprogram" 2>$null
        Write-Host "  ✓ 微信开发者工具已启动" -ForegroundColor Green
        Write-Host "  📍 小程序: $ROOT\miniprogram" -ForegroundColor Gray
    } else {
        Write-Host "  ⚠️  未找到微信开发者工具，请手动打开" -ForegroundColor Yellow
        Write-Host "  📍 下载: https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html" -ForegroundColor Gray
        Write-Host "  📍 导入项目: $ROOT\miniprogram" -ForegroundColor Gray
    }
}

# 启动完成
Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║                    ✅ 全部服务已启动                       ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "📊 服务状态：" -ForegroundColor Cyan
Write-Host "  • signaling (信令服务器)  → http://127.0.0.1:8765" -ForegroundColor Gray
Write-Host "  • siri (LLM API)          → http://127.0.0.1:8010" -ForegroundColor Gray
Write-Host "  • edge_box (B端Agent)     → ws://127.0.0.1:8765/ws/a2a/merchant/box-001" -ForegroundColor Gray
Write-Host "  • 小程序 (C端/B端UI)      → 微信开发者工具" -ForegroundColor Gray
Write-Host ""
Write-Host "🔗 逻辑链路：" -ForegroundColor Cyan
Write-Host "  C端小程序 → POST /intent → signaling:8765" -ForegroundColor Gray
Write-Host "                              ↓ WS广播" -ForegroundColor Gray
Write-Host "  B端Agent ← ws://127.0.0.1:8765/ws/a2a/merchant/box-001" -ForegroundColor Gray
Write-Host "  B端Agent → LLM谈判 → siri:8010 (DeepSeek)" -ForegroundColor Gray
Write-Host "  B端Agent → 报价 → signaling → C端小程序" -ForegroundColor Gray
Write-Host ""
Write-Host "💡 提示：" -ForegroundColor Yellow
Write-Host "  • 微信开发者工具需勾选「不校验合法域名」" -ForegroundColor Gray
Write-Host "  • 所有终端窗口保持打开，按 Ctrl+C 停止服务" -ForegroundColor Gray
Write-Host "  • 查看日志：logs/claw.log" -ForegroundColor Gray
Write-Host ""
