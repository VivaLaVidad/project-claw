# diagnose.ps1 - Project Claw 故障诊断脚本

Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║         Project Claw 故障诊断 v1.0                        ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# 1. 检查 Python
Write-Host "1️⃣  检查 Python..." -ForegroundColor Yellow
$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    Write-Host "  ✓ Python 已安装: $($python.Source)" -ForegroundColor Green
    & python --version
} else {
    Write-Host "  ❌ Python 未安装" -ForegroundColor Red
}
Write-Host ""

# 2. 检查依赖
Write-Host "2️⃣  检查依赖..." -ForegroundColor Yellow
$deps = @('fastapi', 'uvicorn', 'pydantic', 'tenacity', 'cryptography')
foreach ($dep in $deps) {
    $result = & python -c "import $dep" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ $dep" -ForegroundColor Green
    } else {
        Write-Host "  ❌ $dep 未安装" -ForegroundColor Red
    }
}
Write-Host ""

# 3. 检查端口
Write-Host "3️⃣  检查端口..." -ForegroundColor Yellow
$ports = @(8765, 8010, 8501)
foreach ($port in $ports) {
    $result = netstat -ano | Select-String ":$port "
    if ($result) {
        Write-Host "  ⚠️  端口 $port 被占用" -ForegroundColor Yellow
    } else {
        Write-Host "  ✓ 端口 $port 空闲" -ForegroundColor Green
    }
}
Write-Host ""

# 4. 检查文件
Write-Host "4️⃣  检查关键文件..." -ForegroundColor Yellow
$files = @(
    '.env',
    'a2a_signaling_server.py',
    'cloud_server/api_server_pro.py',
    'edge_box/ws_listener.py',
    'miniprogram/app.js',
    'config.py'
)
foreach ($file in $files) {
    if (Test-Path $file) {
        Write-Host "  ✓ $file" -ForegroundColor Green
    } else {
        Write-Host "  ❌ $file 不存在" -ForegroundColor Red
    }
}
Write-Host ""

# 5. 检查 .env 配置
Write-Host "5️⃣  检查 .env 配置..." -ForegroundColor Yellow
if (Test-Path .env) {
    $env_content = Get-Content .env
    if ($env_content -match 'DEEPSEEK_API_KEY') {
        Write-Host "  ✓ DEEPSEEK_API_KEY 已配置" -ForegroundColor Green
    } else {
        Write-Host "  ❌ DEEPSEEK_API_KEY 未配置" -ForegroundColor Red
    }
    if ($env_content -match 'SIGNALING_HOST') {
        Write-Host "  ✓ SIGNALING_HOST 已配置" -ForegroundColor Green
    } else {
        Write-Host "  ❌ SIGNALING_HOST 未配置" -ForegroundColor Red
    }
} else {
    Write-Host "  ❌ .env 文件不存在" -ForegroundColor Red
}
Write-Host ""

# 6. 测试连接
Write-Host "6️⃣  测试服务连接..." -ForegroundColor Yellow
try {
    $health = Invoke-WebRequest -Uri "http://127.0.0.1:8765/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
    if ($health.StatusCode -eq 200) {
        Write-Host "  ✓ signaling:8765 可访问" -ForegroundColor Green
    }
} catch {
    Write-Host "  ❌ signaling:8765 无法访问（服务未启动）" -ForegroundColor Red
}

try {
    $health = Invoke-WebRequest -Uri "http://127.0.0.1:8010/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
    if ($health.StatusCode -eq 200) {
        Write-Host "  ✓ siri:8010 可访问" -ForegroundColor Green
    }
} catch {
    Write-Host "  ❌ siri:8010 无法访问（服务未启动）" -ForegroundColor Red
}
Write-Host ""

# 7. 检查小程序配置
Write-Host "7️⃣  检查小程序配置..." -ForegroundColor Yellow
$app_js = Get-Content miniprogram/app.js
if ($app_js -match "const ENV = 'dev'") {
    Write-Host "  ✓ 小程序环境: dev (本地)" -ForegroundColor Green
} elseif ($app_js -match "const ENV = 'prod'") {
    Write-Host "  ⚠️  小程序环境: prod (生产)" -ForegroundColor Yellow
} else {
    Write-Host "  ❌ 小程序环境配置错误" -ForegroundColor Red
}
Write-Host ""

# 8. 建议
Write-Host "📋 诊断建议：" -ForegroundColor Cyan
Write-Host ""
Write-Host "如果出现「0 在线商家」问题，请按以下步骤排查：" -ForegroundColor Gray
Write-Host ""
Write-Host "1. 清理所有 Python 进程：" -ForegroundColor Gray
Write-Host "   taskkill /F /IM python.exe" -ForegroundColor White
Write-Host ""
Write-Host "2. 启动服务：" -ForegroundColor Gray
Write-Host "   .\start_services.ps1" -ForegroundColor White
Write-Host ""
Write-Host "3. 启动 B端 Agent（新终端）：" -ForegroundColor Gray
Write-Host "   .\start_edge.ps1" -ForegroundColor White
Write-Host ""
Write-Host "4. 清空小程序缓存：" -ForegroundColor Gray
Write-Host "   微信开发者工具 → 工具 → 清空缓存 → 全部清空" -ForegroundColor White
Write-Host ""
Write-Host "5. 强制刷新小程序：" -ForegroundColor Gray
Write-Host "   Ctrl + Shift + R" -ForegroundColor White
Write-Host ""
