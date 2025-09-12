@echo off
REM Strands Agent System Startup Script
REM This script starts all necessary services for the shared global agent system

echo ========================================
echo Starting Strands Agent System
echo ========================================
echo.

REM Change to the project directory
cd /d "C:\Users\Administrator\Documents\Unreal Projects"

echo [1/3] Starting MCP Server on port 8000...
start "MCP Server" cmd /c "cd CitySample\Tools\StrandsMCP && ..\..\..\MyProject\Intermediate\PipInstall\Scripts\python.exe server.py --port 8000"
echo     MCP Server started in background

REM Wait a moment for MCP to initialize
timeout /t 5 /nobreak >nul

echo.
echo [2/3] Starting Shared Agent Server on port 8002...
start "Shared Agent Server" cmd /c "cd CitySample\Tools\StrandsMCP && ..\..\..\MyProject\Intermediate\PipInstall\Scripts\python.exe shared_agent_server.py --port 8002"
echo     Shared Agent Server started in background

echo.
echo [3/3] Starting HTTPS Shared Agent Server on port 8443...
start "HTTPS Shared Agent Server" cmd /c "cd CitySample\Tools\StrandsMCP && ..\..\..\MyProject\Intermediate\PipInstall\Scripts\python.exe shared_agent_server.py --port 8443 --ssl"
echo     HTTPS Shared Agent Server started in background

echo.
echo ========================================
echo Startup Complete!
echo ========================================
echo.
echo Services running:
echo   - MCP Server:          http://localhost:8000/mcp
echo   - HTTP Agent Server:   http://localhost:8002
echo   - HTTPS Agent Server:  https://localhost:8443
echo   - Public API:          https://api.thedimessquare.com
echo.
echo CloudFront Frontend:     https://d1u690gz6k82jo.cloudfront.net/
echo.

REM Wait a bit more and check if services are responding
echo Checking services...
timeout /t 10 /nobreak >nul

curl -s http://localhost:8000/ >nul 2>&1
if %errorlevel%==0 (
    echo ✓ MCP Server is responding
) else (
    echo ⚠ MCP Server may still be starting...
)

curl -s http://localhost:8002/ >nul 2>&1
if %errorlevel%==0 (
    echo ✓ HTTP Agent Server is responding
) else (
    echo ⚠ HTTP Agent Server may still be starting...
)

curl -k -s https://localhost:8443/ >nul 2>&1
if %errorlevel%==0 (
    echo ✓ HTTPS Agent Server is responding
) else (
    echo ⚠ HTTPS Agent Server may still be starting...
)

echo.
echo All services have been started!
echo Press any key to continue or close this window...
pause >nul