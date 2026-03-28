# start_edge.ps1 - B端 Edge Box 一键启动脚本
# 在本地终端运行此脚本以启动 B端 Agent

Write-Host '[Edge] Project Claw B端 Agent 启动器' -ForegroundColor Cyan
Write-Host '[Edge] 连接信令服务器...' -ForegroundColor Yellow

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$PYTHON = 'D:\Python1\python.exe'

# 检查 Python
if (-not (Test-Path $PYTHON)) {
    $PYTHON = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $PYTHON) {
        Write-Host '[Edge] 未找到 Python，请先安装 Python 3.11+' -ForegroundColor Red
        exit 1
    }
}

Write-Host "[Edge] 使用 Python: $PYTHON" -ForegroundColor Green

# 启动 Edge Box WebSocket 监听器
$env:PYTHONUNBUFFERED = '1'
try {
    & $PYTHON -c "import sys; sys.path.insert(0, '$ROOT'); from edge_box.ws_listener import EdgeBoxWSListener; import asyncio; asyncio.run(EdgeBoxWSListener().run_forever())"
} catch {
    Write-Host "[Edge] 启动失败: $_" -ForegroundColor Red
    Write-Host '[Edge] 尝试直接运行 ws_listener.py...' -ForegroundColor Yellow
    & $PYTHON "$ROOT\edge_box\ws_listener.py"
}
