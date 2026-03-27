# start_edge.ps1 - B端Agent一键启动（连接Railway云端）
# 用法: .\start_edge.ps1

Write-Host "[Project Claw] Starting B端 Edge Box Agent..." -ForegroundColor Green

$env:A2A_SIGNALING_URL = "wss://project-claw-production.up.railway.app/ws/a2a/merchant/box-001"
$env:A2A_MERCHANT_ID   = "box-001"
$env:A2A_SIGNING_SECRET = "claw-a2a-signing-secret"
$env:DEEPSEEK_API_KEY  = (Get-Content .env | Select-String 'DEEPSEEK_API_KEY' | ForEach-Object { $_ -replace 'DEEPSEEK_API_KEY=',''})

Write-Host "[Config] WS -> $env:A2A_SIGNALING_URL" -ForegroundColor Cyan
Write-Host "[Config] Merchant ID -> $env:A2A_MERCHANT_ID" -ForegroundColor Cyan

python -m edge_box.ws_listener
