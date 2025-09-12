# Strands Agent System Startup Script (PowerShell)
# This script starts all necessary services for the shared global agent system

Write-Host "========================================"
Write-Host "Starting Strands Agent System" -ForegroundColor Green
Write-Host "========================================"
Write-Host ""

# Change to the project directory
Set-Location "C:\Users\Administrator\Documents\Unreal Projects"

Write-Host "[1/3] Starting MCP Server on port 8000..." -ForegroundColor Yellow
$mcpProcess = Start-Process -FilePath "MyProject\Intermediate\PipInstall\Scripts\python.exe" -ArgumentList "CitySample\Tools\StrandsMCP\server.py", "--port", "8000" -WorkingDirectory "CitySample\Tools\StrandsMCP" -PassThru -WindowStyle Minimized
Write-Host "    MCP Server started (PID: $($mcpProcess.Id))" -ForegroundColor Green

# Wait for MCP to initialize
Start-Sleep -Seconds 5

Write-Host ""
Write-Host "[2/3] Starting Shared Agent Server on port 8002..." -ForegroundColor Yellow
$httpProcess = Start-Process -FilePath "MyProject\Intermediate\PipInstall\Scripts\python.exe" -ArgumentList "CitySample\Tools\StrandsMCP\shared_agent_server.py", "--port", "8002" -WorkingDirectory "CitySample\Tools\StrandsMCP" -PassThru -WindowStyle Minimized
Write-Host "    HTTP Agent Server started (PID: $($httpProcess.Id))" -ForegroundColor Green

Write-Host ""
Write-Host "[3/3] Starting HTTPS Shared Agent Server on port 8443..." -ForegroundColor Yellow
$httpsProcess = Start-Process -FilePath "MyProject\Intermediate\PipInstall\Scripts\python.exe" -ArgumentList "CitySample\Tools\StrandsMCP\shared_agent_server.py", "--port", "8443", "--ssl" -WorkingDirectory "CitySample\Tools\StrandsMCP" -PassThru -WindowStyle Minimized
Write-Host "    HTTPS Agent Server started (PID: $($httpsProcess.Id))" -ForegroundColor Green

Write-Host ""
Write-Host "========================================"
Write-Host "Startup Complete!" -ForegroundColor Green
Write-Host "========================================"
Write-Host ""
Write-Host "Services running:"
Write-Host "  - MCP Server:          http://localhost:8000/mcp" -ForegroundColor Cyan
Write-Host "  - HTTP Agent Server:   http://localhost:8002" -ForegroundColor Cyan
Write-Host "  - HTTPS Agent Server:  https://localhost:8443" -ForegroundColor Cyan
Write-Host "  - Public API:          https://api.thedimessquare.com" -ForegroundColor Cyan
Write-Host ""
Write-Host "CloudFront Frontend:     https://d1u690gz6k82jo.cloudfront.net/" -ForegroundColor Magenta
Write-Host ""

# Save process IDs for later management
$processInfo = @{
    MCP = $mcpProcess.Id
    HTTP = $httpProcess.Id
    HTTPS = $httpsProcess.Id
    StartTime = Get-Date
}
$processInfo | ConvertTo-Json | Out-File "strands_processes.json" -Encoding UTF8

Write-Host "Process IDs saved to strands_processes.json"
Write-Host ""

# Wait and check services
Write-Host "Checking services..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

try {
    Invoke-WebRequest -Uri "http://localhost:8000/" -UseBasicParsing -TimeoutSec 5 | Out-Null
    Write-Host "✓ MCP Server is responding" -ForegroundColor Green
} catch {
    Write-Host "⚠ MCP Server may still be starting..." -ForegroundColor Yellow
}

try {
    Invoke-WebRequest -Uri "http://localhost:8002/" -UseBasicParsing -TimeoutSec 5 | Out-Null
    Write-Host "✓ HTTP Agent Server is responding" -ForegroundColor Green
} catch {
    Write-Host "⚠ HTTP Agent Server may still be starting..." -ForegroundColor Yellow
}

try {
    Invoke-WebRequest -Uri "https://localhost:8443/" -UseBasicParsing -TimeoutSec 5 -SkipCertificateCheck | Out-Null
    Write-Host "✓ HTTPS Agent Server is responding" -ForegroundColor Green
} catch {
    Write-Host "⚠ HTTPS Agent Server may still be starting..." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "All services have been started!" -ForegroundColor Green
Write-Host "Press any key to continue..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")