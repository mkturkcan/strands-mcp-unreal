@echo off
echo ========================================
echo Strands System Status
echo ========================================
echo.

echo Checking ports...
netstat -ano | findstr ":8000 " | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo ✓ Port 8000 ^(MCP Server^) is listening
) else (
    echo ✗ Port 8000 ^(MCP Server^) is NOT listening
)

netstat -ano | findstr ":8002 " | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo ✓ Port 8002 ^(HTTP Agent^) is listening  
) else (
    echo ✗ Port 8002 ^(HTTP Agent^) is NOT listening
)

netstat -ano | findstr ":8443 " | findstr "LISTENING" >nul
if %errorlevel%==0 (
    echo ✓ Port 8443 ^(HTTPS Agent^) is listening
) else (
    echo ✗ Port 8443 ^(HTTPS Agent^) is NOT listening
)

echo.
echo URLs:
echo - Local HTTP:  http://localhost:8002/
echo - Local HTTPS: https://localhost:8443/
echo - Public API:  https://api.thedimessquare.com/
echo - Frontend:    https://d1u690gz6k82jo.cloudfront.net/
echo.
pause