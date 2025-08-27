# Strands Agent System Status Check Script
# This script checks the status of all Strands services

Write-Host "========================================"
Write-Host "Strands Agent System Status" -ForegroundColor Cyan
Write-Host "========================================"
Write-Host ""

$services = @(
    @{Name="MCP Server"; URL="http://localhost:8000/"; Port=8000},
    @{Name="HTTP Agent Server"; URL="http://localhost:8002/"; Port=8002},
    @{Name="HTTPS Agent Server"; URL="https://localhost:8443/"; Port=8443}
)

foreach ($service in $services) {
    Write-Host "Checking $($service.Name) on port $($service.Port)..." -ForegroundColor Yellow
    
    # Check if port is listening
    $portCheck = netstat -ano | Select-String ":$($service.Port) " | Select-String "LISTENING"
    
    if ($portCheck) {
        $pid = ($portCheck.ToString() -split '\s+')[-1]
        Write-Host "  ✓ Port $($service.Port) is listening (PID: $pid)" -ForegroundColor Green
        
        # Try to make HTTP request
        try {
            if ($service.URL -like "https:*") {
                $response = Invoke-WebRequest -Uri $service.URL -UseBasicParsing -TimeoutSec 5 -SkipCertificateCheck
            } else {
                $response = Invoke-WebRequest -Uri $service.URL -UseBasicParsing -TimeoutSec 5
            }
            
            if ($response.StatusCode -eq 200) {
                Write-Host "  ✓ Service is responding (HTTP 200)" -ForegroundColor Green
                
                # Try to parse JSON response
                try {
                    $json = $response.Content | ConvertFrom-Json
                    if ($json.service) {
                        Write-Host "  ✓ Service: $($json.service)" -ForegroundColor Green
                        if ($json.agent_status -and $json.agent_status.total_commands_processed -ne $null) {
                            Write-Host "  ✓ Commands processed: $($json.agent_status.total_commands_processed)" -ForegroundColor Green
                        }
                    }
                } catch {
                    Write-Host "  ✓ Service responding (non-JSON response)" -ForegroundColor Green
                }
            }
        } catch {
            Write-Host "  ⚠ Port is listening but service not responding: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  ✗ Port $($service.Port) is not listening" -ForegroundColor Red
    }
    Write-Host ""
}

# Check external API
Write-Host "Checking external API..." -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "https://api.thedimessquare.com/" -UseBasicParsing -TimeoutSec 10
    if ($response.StatusCode -eq 200) {
        Write-Host "  ✓ https://api.thedimessquare.com/ is responding" -ForegroundColor Green
    }
} catch {
    Write-Host "  ⚠ External API not responding: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "    (This may be normal if DNS/ALB is still propagating)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "CloudFront Frontend: https://d1u690gz6k82jo.cloudfront.net/" -ForegroundColor Magenta
Write-Host ""

# Show recent log entries if available
if (Test-Path "strands_processes.json") {
    $processInfo = Get-Content "strands_processes.json" | ConvertFrom-Json
    Write-Host "System started at: $($processInfo.StartTime)" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "Press any key to continue..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")