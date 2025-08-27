# Quick Strands System Status Check
Write-Host "Strands System Status:" -ForegroundColor Cyan

# Check ports
$ports = @(8000, 8002, 8443)
foreach ($port in $ports) {
    $check = netstat -ano | Select-String ":$port " | Select-String "LISTENING"
    if ($check) {
        Write-Host "✓ Port $port is listening" -ForegroundColor Green
    } else {
        Write-Host "✗ Port $port is NOT listening" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "URLs:"
Write-Host "- Local HTTP: http://localhost:8002/" -ForegroundColor Cyan  
Write-Host "- Local HTTPS: https://localhost:8443/" -ForegroundColor Cyan
Write-Host "- Public API: https://api.thedimessquare.com/" -ForegroundColor Magenta
Write-Host "- Frontend: https://d1u690gz6k82jo.cloudfront.net/" -ForegroundColor Magenta