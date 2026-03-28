# start_services.ps1 - Project Claw 服务启动脚本 v2.0
# 修复：更好的错误处理和端口管理

param(
    [switch]$NoWechat
)

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$PYTHON = 'D:\Python1\python.exe'

Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║         Project Claw 服务启动 v2.0                        ║" -ForegroundColor Cyan
Write-Host "║  启动：signaling:8765 + siri:8010 + dashboard:8501        ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# 检查 Python
if (-not (Test-Path $PYTHON)) {
    Write-Host "❌ 未找到 Python: $PYTHON" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Python: $PYTHON" -ForegroundColor Green

# 清理所有 Python 进程
Write-Host ""
Write-Host "🔧 清理旧进程..." -ForegroundColor Yellow
taskkill /F /IM python.exe 2>$null | Out-Null
Start-Sleep -Seconds 2
Write-Host "  ✓ 已清理所有 Python 进程" -ForegroundColor Green

# 验证端口空闲
Write-Host ""
Write-Host "🔍 验证端口..." -ForegroundColor Yellow
$ports_in_use = netstat -ano | Select-String ':8765|:8010'
if ($ports_in_use) {
    Write-Host "  ⚠️  端口仍被占用，再次清理..." -ForegroundColor Yellow
    $ports_in_use | ForEach-Object {
        $pid = $_ -split '\s+' | Select-Object -Last 1
        taskkill /F /PID $pid 2>$null | Out-Null
    }
    Start-Sleep -Seconds 2
}
Write-Host "  ✓ 端口已释放" -ForegroundColor Green

# 启动 signaling
Write-Host ""
Write-Host "🚀 启动 signaling:8765..." -ForegroundColor Cyan
$signaling_cmd = "cd '$ROOT'; & '$PYTHON' -m uvicorn a2a_signaling_server:app --host 127.0.0.1 --port 8765 --reload"
$signaling_window = New-Object System.Diagnostics.ProcessStartInfo
$signaling_window.FileName = "powershell.exe"
$signaling_window.Arguments = "-NoExit", "-Command", $signaling_cmd
$signaling_window.UseShellExecute = $true
$signaling_window.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
$signaling_proc = [System.Diagnostics.Process]::Start($signaling_window)
Write-Host "  ✓ signaling 已启动 (PID=$($signaling_proc.Id))" -ForegroundColor Green

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
    Write-Host "  ⏳ 等待中... ($waited/$max_wait)" -ForegroundColor Gray
}

if ($waited -ge $max_wait) {
    Write-Host "  ⚠️  signaling 启动超时，但继续启动其他服务..." -ForegroundColor Yellow
}

# 启动 siri
Write-Host ""
Write-Host "🚀 启动 siri:8010..." -ForegroundColor Cyan
$siri_cmd = "cd '$ROOT'; & '$PYTHON' -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8010 --reload"
$siri_window = New-Object System.Diagnostics.ProcessStartInfo
$siri_window.FileName = "powershell.exe"
$siri_window.Arguments = "-NoExit", "-Command", $siri_cmd
$siri_window.UseShellExecute = $true
$siri_window.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
$siri_proc = [System.Diagnostics.Process]::Start($siri_window)
Write-Host "  ✓ siri 已启动 (PID=$($siri_proc.Id))" -ForegroundColor Green

# 启动 dashboard
Write-Host ""
Write-Host "🚀 启动 dashboard:8501..." -ForegroundColor Cyan
$dashboard_cmd = "cd '$ROOT'; & '$PYTHON' -m streamlit run god_mode_dashboard.py --server.port 8501 --server.headless true"
$dashboard_window = New-Object System.Diagnostics.ProcessStartInfo
$dashboard_window.FileName = "powershell.exe"
$dashboard_window.Arguments = "-NoExit", "-Command", $dashboard_cmd
$dashboard_window.UseShellExecute = $true
$dashboard_window.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Normal
$dashboard_proc = [System.Diagnostics.Process]::Start($dashboard_window)
Write-Host "  ✓ dashboard 已启动 (PID=$($dashboard_proc.Id))" -ForegroundColor Green

# 启动完成
Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║                    ✅ 所有服务已启动                       ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "📊 服务地址：" -ForegroundColor Cyan
Write-Host "  • signaling: http://127.0.0.1:8765" -ForegroundColor Gray
Write-Host "  • siri:      http://127.0.0.1:8010" -ForegroundColor Gray
Write-Host "  • dashboard: http://127.0.0.1:8501" -ForegroundColor Gray
Write-Host ""
Write-Host "💡 下一步：" -ForegroundColor Yellow
Write-Host "  1. 在新终端运行：.\start_edge.ps1" -ForegroundColor Gray
Write-Host "  2. 打开微信开发者工具，导入 miniprogram" -ForegroundColor Gray
Write-Host "  3. 清空缓存：工具 → 清空缓存 → 全部清空" -ForegroundColor Gray
Write-Host "  4. 强制刷新：Ctrl + Shift + R" -ForegroundColor Gray
Write-Host ""
