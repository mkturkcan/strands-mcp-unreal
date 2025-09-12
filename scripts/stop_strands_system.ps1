# Strands Agent System Stop Script (PowerShell)
# This script stops all Strands-related services

Write-Host "========================================"
Write-Host "Stopping Strands Agent System" -ForegroundColor Red
Write-Host "========================================"
Write-Host ""

# Try to load saved process IDs
$processFile = "strands_processes.json"
if (Test-Path $processFile) {
    try {
        $processInfo = Get-Content $processFile | ConvertFrom-Json
        Write-Host "Found saved process IDs from: $($processInfo.StartTime)" -ForegroundColor Yellow
        
        # Try to stop by saved PIDs first
        @($processInfo.MCP, $processInfo.HTTP, $processInfo.HTTPS) | ForEach-Object {
            if ($_ -and (Get-Process -Id $_ -ErrorAction SilentlyContinue)) {
                Write-Host "Stopping process PID: $_" -ForegroundColor Yellow
                Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
            }
        }
        
        # Remove the process file
        Remove-Item $processFile -ErrorAction SilentlyContinue
    } catch {
        Write-Host "Could not read process file, falling back to process name search" -ForegroundColor Yellow
    }
}

# Kill any remaining Python processes running our servers
Write-Host "Stopping any remaining Strands services..." -ForegroundColor Yellow

# Find and kill processes by port
$ports = @(8000, 8002, 8443)
foreach ($port in $ports) {
    $process = netstat -ano | Select-String ":$port " | Select-Object -First 1
    if ($process) {
        $pid = ($process.ToString() -split '\s+')[-1]
        if ($pid -match '^\d+$') {
            Write-Host "Stopping process on port $port (PID: $pid)" -ForegroundColor Yellow
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        }
    }
}

# Kill any Python processes running our specific scripts
Get-Process python -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*server.py*" -or 
    $_.CommandLine -like "*shared_agent_server.py*"
} | ForEach-Object {
    Write-Host "Stopping Python process: $($_.ProcessName) (PID: $($_.Id))" -ForegroundColor Yellow
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "========================================"
Write-Host "All Strands services stopped!" -ForegroundColor Green
Write-Host "========================================"
Write-Host ""

# Verify ports are free
Start-Sleep -Seconds 2
$portsInUse = @()
foreach ($port in $ports) {
    $check = netstat -ano | Select-String ":$port "
    if ($check) {
        $portsInUse += $port
    }
}

if ($portsInUse.Count -eq 0) {
    Write-Host "✓ All ports are now free" -ForegroundColor Green
} else {
    Write-Host "⚠ Some ports are still in use: $($portsInUse -join ', ')" -ForegroundColor Yellow
    Write-Host "You may need to restart the EC2 instance if processes won't stop" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Press any key to continue..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")