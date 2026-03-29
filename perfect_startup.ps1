# Project Claw 完美一键启动脚本 v3.0
# 功能：一键启动所有服务（后端 + 大屏 + Redis + 小程序）
# 用法：.\perfect_startup.ps1

param(
    [switch]$All,
    [switch]$Backend,
    [switch]$Dashboard,
    [switch]$Redis,
    [switch]$MiniProgram,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$projectPath = "d:\桌面\Project Claw"

# ═══════════════════════════════════════════════════════════════
# 显示帮助
# ═══════════════════════════════════════════════════════════════

if ($Help) {
    Write-Host ""
    Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║     🚀 Project Claw 完美一键启动脚本 v3.0                 ║" -ForegroundColor Cyan
    Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "用法：" -ForegroundColor Yellow
    Write-Host "  .\perfect_startup.ps1              # 显示菜单" -ForegroundColor White
    Write-Host "  .\perfect_startup.ps1 -All         # 启动所有服务" -ForegroundColor White
    Write-Host "  .\perfect_startup.ps1 -Backend     # 仅启动后端 API" -ForegroundColor White
    Write-Host "  .\perfect_startup.ps1 -Dashboard   # 仅启动融资路演大屏" -ForegroundColor White
    Write-Host "  .\perfect_startup.ps1 -Redis       # 仅启动 Redis" -ForegroundColor White
    Write-Host "  .\perfect_startup.ps1 -MiniProgram # 仅启动小程序" -ForegroundColor White
    Write-Host ""
    exit 0
}

# ═══════════════════════════════════════════════════════════════
# 显示菜单
# ═══════════════════════════════════════════════════════════════

function Show-Menu {
    Write-Host ""
    Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║     🚀 Project Claw 完美一键启动脚本 v3.0                 ║" -ForegroundColor Cyan
    Write-Host "║     启动所有服务：后端 + 大屏 + Redis + 小程序            ║" -ForegroundColor Cyan
    Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "选择启动模式：" -ForegroundColor Yellow
    Write-Host "  1. 🚀 启动所有服务（推荐）" -ForegroundColor Green
    Write-Host "  2. 🔧 仅启动后端 API" -ForegroundColor Green
    Write-Host "  3. 📊 仅启动融资路演大屏" -ForegroundColor Green
    Write-Host "  4. 💾 仅启动 Redis" -ForegroundColor Green
    Write-Host "  5. 📱 仅启动小程序" -ForegroundColor Green
    Write-Host "  6. 🔄 启动后端 + 大屏 + Redis" -ForegroundColor Green
    Write-Host "  0. ❌ 退出" -ForegroundColor Red
    Write-Host ""
}

# ═══════════════════════════════════════════════════════════════
# 验证环境
# ═══════════════════════════════════════════════════════════════

function Verify-Environment {
    Write-Host "[验证] 检查项目环境..." -ForegroundColor Yellow
    
    if (-not (Test-Path $projectPath)) {
        Write-Host "✗ 项目目录不存在: $projectPath" -ForegroundColor Red
        exit 1
    }
    Write-Host "✓ 项目目录存在" -ForegroundColor Green
    
    if (-not (Test-Path "$projectPath\venv")) {
        Write-Host "✗ 虚拟环境不存在" -ForegroundColor Red
        exit 1
    }
    Write-Host "✓ 虚拟环境存在" -ForegroundColor Green
    
    Write-Host ""
}

# ═══════════════════════════════════════════════════════════════
# 启动后端 API
# ═══════════════════════════════════════════════════════════════

function Start-Backend {
    Write-Host "[启动] 后端 API 服务..." -ForegroundColor Yellow
    Write-Host "命令：python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload" -ForegroundColor Cyan
    Write-Host ""
    
    Start-Process cmd -ArgumentList "/k cd /d $projectPath && venv\Scripts\activate.bat && python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload" -WindowStyle Normal
    
    Start-Sleep -Seconds 3
    Write-Host "✓ 后端 API 已启动（端口 8765）" -ForegroundColor Green
    Write-Host "  访问：http://localhost:8765/docs" -ForegroundColor Gray
    Write-Host ""
}

# ═══════════════════════════════════════════════════════════════
# 启动融资路演大屏
# ═══════════════════════════════════════════════════════════════

function Start-Dashboard {
    Write-Host "[启动] 融资路演大屏..." -ForegroundColor Yellow
    Write-Host "命令：streamlit run cloud_server/god_dashboard.py --server.port 8501" -ForegroundColor Cyan
    Write-Host ""
    
    Start-Process cmd -ArgumentList "/k cd /d $projectPath && venv\Scripts\activate.bat && streamlit run cloud_server/god_dashboard.py --server.port 8501" -WindowStyle Normal
    
    Start-Sleep -Seconds 3
    Write-Host "✓ 融资路演大屏已启动（端口 8501）" -ForegroundColor Green
    Write-Host "  访问：http://localhost:8501" -ForegroundColor Gray
    Write-Host ""
}

# ═══════════════════════════════════════════════════════════════
# 启动 Redis
# ═══════════════════════════════════════════════════════════════

function Start-Redis {
    Write-Host "[启动] Redis..." -ForegroundColor Yellow
    Write-Host "命令：docker run -d -p 6379:6379 redis:latest" -ForegroundColor Cyan
    Write-Host ""
    
    try {
        $dockerVersion = docker --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            $redisRunning = docker ps --format "table {{.Names}}" | Select-String "redis"
            
            if ($redisRunning) {
                Write-Host "✓ Redis 容器已在运行" -ForegroundColor Green
            } else {
                docker run -d -p 6379:6379 redis:latest | Out-Null
                Start-Sleep -Seconds 2
                Write-Host "✓ Redis 容器已启动（端口 6379）" -ForegroundColor Green
            }
        }
    } catch {
        Write-Host "✗ Docker 未安装或未运行" -ForegroundColor Red
        Write-Host "  提示：请先安装 Docker Desktop" -ForegroundColor Yellow
    }
    Write-Host ""
}

# ═══════════════════════════════════════════════════════════════
# 启动小程序
# ═══════════════════════════════════════════════════════════════

function Start-MiniProgram {
    Write-Host "[启动] 微信小程序..." -ForegroundColor Yellow
    Write-Host "命令：打开微信开发者工具" -ForegroundColor Cyan
    Write-Host ""
    
    Write-Host "请手动执行以下步骤：" -ForegroundColor Yellow
    Write-Host "  1. 打开微信开发者工具" -ForegroundColor White
    Write-Host "  2. 打开项目：$projectPath\miniprogram" -ForegroundColor White
    Write-Host "  3. 点击'编译'或按 Ctrl+Shift+R" -ForegroundColor White
    Write-Host "  4. 在模拟器中预览" -ForegroundColor White
    Write-Host ""
    Write-Host "✓ 小程序启动说明已显示" -ForegroundColor Green
    Write-Host ""
}

# ═══════════════════════════════════════════════════════════════
# 显示启动完成信息
# ═══════════════════════════════════════════════════════════════

function Show-Completion {
    param(
        [string[]]$Services
    )
    
    Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "║     ✅ 服务启动完成！                                     ║" -ForegroundColor Green
    Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green
    Write-Host ""
    
    Write-Host "📍 已启动的服务：" -ForegroundColor Cyan
    foreach ($service in $Services) {
        Write-Host "  ✓ $service" -ForegroundColor Green
    }
    Write-Host ""
    
    Write-Host "📍 访问地址：" -ForegroundColor Cyan
    if ($Services -contains "后端 API") {
        Write-Host "  • 后端 API: http://localhost:8765" -ForegroundColor White
        Write-Host "  • API 文档: http://localhost:8765/docs" -ForegroundColor White
    }
    if ($Services -contains "融资路演大屏") {
        Write-Host "  • 融资路演大屏: http://localhost:8501" -ForegroundColor White
    }
    if ($Services -contains "Redis") {
        Write-Host "  • Redis: localhost:6379" -ForegroundColor White
    }
    if ($Services -contains "小程序") {
        Write-Host "  • 小程序: 微信开发者工具模拟器" -ForegroundColor White
    }
    Write-Host ""
    
    Write-Host "🛑 停止服务：" -ForegroundColor Cyan
    Write-Host "  • 关闭对应的命令行窗口" -ForegroundColor Gray
    Write-Host "  • 或在 PowerShell 中运行：Stop-Process -Name python -Force" -ForegroundColor Gray
    Write-Host ""
}

# ═══════════════════════════════════════════════════════════════
# 主程序
# ═══════════════════════════════════════════════════════════════

function Main {
    # 验证环境
    Verify-Environment
    
    # 如果指定了参数，直接启动
    if ($All) {
        Write-Host "启动所有服务..." -ForegroundColor Green
        Start-Backend
        Start-Dashboard
        Start-Redis
        Start-MiniProgram
        Show-Completion @("后端 API", "融资路演大屏", "Redis", "小程序")
        return
    }
    
    if ($Backend -or $Dashboard -or $Redis -or $MiniProgram) {
        $services = @()
        if ($Backend) { Start-Backend; $services += "后端 API" }
        if ($Dashboard) { Start-Dashboard; $services += "融资路演大屏" }
        if ($Redis) { Start-Redis; $services += "Redis" }
        if ($MiniProgram) { Start-MiniProgram; $services += "小程序" }
        Show-Completion $services
        return
    }
    
    # 显示菜单
    while ($true) {
        Show-Menu
        $choice = Read-Host "请选择 (0-6)"
        
        $services = @()
        
        switch ($choice) {
            "1" {
                Write-Host ""
                Start-Backend
                Start-Dashboard
                Start-Redis
                Start-MiniProgram
                $services = @("后端 API", "融资路演大屏", "Redis", "小程序")
                Show-Completion $services
                break
            }
            "2" {
                Write-Host ""
                Start-Backend
                $services = @("后端 API")
                Show-Completion $services
                break
            }
            "3" {
                Write-Host ""
                Start-Dashboard
                $services = @("融资路演大屏")
                Show-Completion $services
                break
            }
            "4" {
                Write-Host ""
                Start-Redis
                $services = @("Redis")
                Show-Completion $services
                break
            }
            "5" {
                Write-Host ""
                Start-MiniProgram
                $services = @("小程序")
                Show-Completion $services
                break
            }
            "6" {
                Write-Host ""
                Start-Backend
                Start-Dashboard
                Start-Redis
                $services = @("后端 API", "融资路演大屏", "Redis")
                Show-Completion $services
                break
            }
            "0" {
                Write-Host "退出脚本" -ForegroundColor Yellow
                exit 0
            }
            default {
                Write-Host "无效的选择，请重试" -ForegroundColor Red
                continue
            }
        }
        
        break
    }
}

# 运行主程序
Main
