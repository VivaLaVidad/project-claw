# Project Claw v14.3 - Railway 部署启动脚本
# 用法：.\startup_railway.ps1

Write-Host ''
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host '  Project Claw v14.3 - Railway 部署启动' -ForegroundColor Cyan
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host ''

$python = 'd:\桌面\Project Claw\maic_env\Scripts\python.exe'
$root   = 'd:\桌面\Project_Claw_v14'

# ── 检查 Python ──────────────────────────────────────────────────────
if (-not (Test-Path $python)) {
    Write-Host '[ERROR] Python 路径不存在: ' $python -ForegroundColor Red
    exit 1
}
Write-Host '[OK] Python 路径确认' -ForegroundColor Green

# ── 清理旧进程 ───────────────────────────────────────────────────────
Write-Host '[...] 清理旧进程...' -ForegroundColor Yellow
Get-Process python,uvicorn -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
Write-Host '[OK] 旧进程已清理' -ForegroundColor Green

# ── 启动 B端盒子 (box-001) ────────────────────────────────────────
Write-Host '[...] 启动 B端盒子 box-001...' -ForegroundColor Yellow
$env:SKIP_SEMANTIC_RAG = '1'
$boxPsi = New-Object System.Diagnostics.ProcessStartInfo
$boxPsi.FileName = $python
$boxPsi.Arguments = '-m edge_box.main'
$boxPsi.WorkingDirectory = $root
$boxPsi.UseShellExecute = $true
$boxPsi.CreateNoWindow = $false
[System.Diagnostics.Process]::Start($boxPsi) | Out-Null
Start-Sleep -Seconds 8
Write-Host '[OK] box-001 已启动' -ForegroundColor Green

# ── 启动虚拟商家模拟器 (box-002 ~ box-008) ─────────────────────────
Write-Host '[...] 启动 7 家虚拟商家模拟器...' -ForegroundColor Yellow
$mockPsi = New-Object System.Diagnostics.ProcessStartInfo
$mockPsi.FileName = $python
$mockPsi.Arguments = 'mock_merchants/multi_merchant_simulator.py'
$mockPsi.WorkingDirectory = $root
$mockPsi.UseShellExecute = $true
$mockPsi.CreateNoWindow = $false
[System.Diagnostics.Process]::Start($mockPsi) | Out-Null
Start-Sleep -Seconds 6
Write-Host '[OK] 虚拟商家已启动' -ForegroundColor Green

# ── 显示状态摘要 ─────────────────────────────────────────────────────
Write-Host ''
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host '  启动完成！' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host ''
Write-Host '  🌐 Railway Hub: https://project-claw-production.up.railway.app' -ForegroundColor White
Write-Host '  📱 小程序体验版二维码: 在微信公众平台获取' -ForegroundColor White
Write-Host ''
Write-Host '  在线商家:' -ForegroundColor White
Write-Host '    - box-001 (招牌面馆)' -ForegroundColor Gray
Write-Host '    - box-002 (成都麻辣烫)' -ForegroundColor Gray
Write-Host '    - box-003 (广式茶餐厅)' -ForegroundColor Gray
Write-Host '    - box-004 (家常小炒)' -ForegroundColor Gray
Write-Host '    - box-005 (北方饺子馆)' -ForegroundColor Gray
Write-Host '    - box-006 (陕西面馆)' -ForegroundColor Gray
Write-Host '    - box-007 (轻食咖啡)' -ForegroundColor Gray
Write-Host '    - box-008 (韩式料理)' -ForegroundColor Gray
Write-Host ''
Write-Host '  ✅ 手机小程序现在可以检测到所有在线商家！' -ForegroundColor Green
Write-Host ''
Write-Host '  按 Ctrl+C 停止所有服务' -ForegroundColor Yellow
Write-Host ''

# 保持窗口打开
while ($true) { Start-Sleep -Seconds 1 }
