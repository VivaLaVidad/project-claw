# Project Claw 一键启动脚本 (Windows PowerShell)
# 用法：.\one_click_startup.ps1

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║     🚀 Project Claw 一键启动脚本 v1.0                     ║" -ForegroundColor Cyan
Write-Host "║     启动所有服务：后端 + 大屏 + Redis + 小程序            ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

$projectPath = "d:\桌面\Project Claw"
$startTime = Get-Date

# ═══════════════════════════════════════════════════════════════
# 第一步：验证环境
# ═══════════════════════════════════════════════════════════════
Write-Host "[1/5] 验证环境..." -ForegroundColor Yellow

# 检查项目目录
if (-not (Test-Path $projectPath)) {
    Write-Host "✗ 项目目录不存在: $projectPath" -ForegroundColor Red
    exit 1
}
Write-Host "✓ 项目目录存在" -ForegroundColor Green

# 检查虚拟环境
if (-not (Test-Path "$projectPath\venv")) {
    Write-Host "✗ 虚拟环境不存在，正在创建..." -ForegroundColor Yellow
    cd $projectPath
    python -m venv venv
    Write-Host "✓ 虚拟环境已创建" -ForegroundColor Green
} else {
    Write-Host "✓ 虚拟环境已存在" -ForegroundColor Green
}

# 检查数据库
if (-not (Test-Path "$projectPath\audit.db")) {
    Write-Host "⚠ 审计数据库不存在，将在启动时创建" -ForegroundColor Yellow
}
if (-not (Test-Path "$projectPath\dlq.db")) {
    Write-Host "⚠ 死信队列数据库不存在，将在启动时创建" -ForegroundColor Yellow
}

Write-Host ""

# ═══════════════════════════════════════════════════════════════
# 第二步：激活虚拟环境
# ═══════════════════════════════════════════════════════════════
Write-Host "[2/5] 激活虚拟环境..." -ForegroundColor Yellow
cd $projectPath
& ".\venv\Scripts\Activate.ps1"
Write-Host "✓ 虚拟环境已激活" -ForegroundColor Green
Write-Host ""

# ═══════════════════════════════════════════════════════════════
# 第三步：启动 Redis
# ═══════════════════════════════════════════════════════════════
Write-Host "[3/5] 启动 Redis..." -ForegroundColor Yellow

# 检查 Docker
$dockerInstalled = $false
try {
    $dockerVersion = docker --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $dockerInstalled = $true
    }
} catch {
    $dockerInstalled = $false
}

if ($dockerInstalled) {
    # 检查 Redis 容器是否已运行
    $redisRunning = docker ps --format "table {{.Names}}" | Select-String "redis"
    
    if ($redisRunning) {
        Write-Host "✓ Redis 容器已在运行" -ForegroundColor Green
    } else {
        Write-Host "启动 Redis 容器..." -ForegroundColor Cyan
        docker run -d -p 6379:6379 redis:latest | Out-Null
        Start-Sleep -Seconds 2
        Write-Host "✓ Redis 容器已启动" -ForegroundColor Green
    }
} else {
    Write-Host "⚠ Docker 未安装，跳过 Redis 启动" -ForegroundColor Yellow
    Write-Host "  提示：可以手动运行 redis-server 或 docker run -d -p 6379:6379 redis:latest" -ForegroundColor Gray
}

Write-Host ""

# ═══════════════════════════════════════════════════════════════
# 第四步：启动后端服务
# ═══════════════════════════════════════════════════════════════
Write-Host "[4/5] 启动后端 API 服务..." -ForegroundColor Yellow
Write-Host "启动命令：python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload" -ForegroundColor Cyan

Start-Process cmd -ArgumentList "/k cd /d $projectPath && venv\Scripts\activate.bat && python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload" -WindowStyle Normal

Start-Sleep -Seconds 3
Write-Host "✓ 后端 API 服务已启动（端口 8765）" -ForegroundColor Green
Write-Host ""

# ═══════════════════════════════════════════════════════════════
# 第五步：启动融资路演大屏
# ═══════════════════════════════════════════════════════════════
Write-Host "[5/5] 启动融资路演大屏..." -ForegroundColor Yellow
Write-Host "启动命令：streamlit run cloud_server/god_dashboard.py --server.port 8501" -ForegroundColor Cyan

Start-Process cmd -ArgumentList "/k cd /d $projectPath && venv\Scripts\activate.bat && streamlit run cloud_server/god_dashboard.py --server.port 8501" -WindowStyle Normal

Start-Sleep -Seconds 3
Write-Host "✓ 融资路演大屏已启动（端口 8501）" -ForegroundColor Green
Write-Host ""

# ═══════════════════════════════════════════════════════════════
# 完成
# ═══════════════════════════════════════════════════════════════
$endTime = Get-Date
$duration = ($endTime - $startTime).TotalSeconds

Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║     ✅ 所有服务已启动！                                   ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""

Write-Host "📍 服务地址：" -ForegroundColor Cyan
Write-Host "  • 后端 API: http://localhost:8765" -ForegroundColor White
Write-Host "  • API 文档: http://localhost:8765/docs" -ForegroundColor White
Write-Host "  • 融资路演大屏: http://localhost:8501" -ForegroundColor White
Write-Host "  • Redis: localhost:6379" -ForegroundColor White
Write-Host ""

Write-Host "📝 后续步骤：" -ForegroundColor Cyan
Write-Host "  1. 在浏览器中打开 http://localhost:8765/docs 查看 API 文档" -ForegroundColor White
Write-Host "  2. 在浏览器中打开 http://localhost:8501 查看融资路演大屏" -ForegroundColor White
Write-Host "  3. 打开微信开发者工具，编译小程序项目" -ForegroundColor White
Write-Host ""

Write-Host "🛑 停止服务：" -ForegroundColor Cyan
Write-Host "  • 关闭对应的命令行窗口" -ForegroundColor Gray
Write-Host "  • 或在 PowerShell 中运行：Stop-Process -Name python -Force" -ForegroundColor Gray
Write-Host ""

Write-Host "⏱️  启动耗时：$([Math]::Round($duration, 2)) 秒" -ForegroundColor Gray
Write-Host ""

# 自动打开浏览器
Write-Host "正在打开浏览器..." -ForegroundColor Cyan
Start-Sleep -Seconds 2
Start-Process "http://localhost:8765/docs"
Start-Process "http://localhost:8501"

Write-Host ""
Write-Host "🎉 Project Claw 已完全启动！开始开发吧！" -ForegroundColor Green
Write-Host ""
