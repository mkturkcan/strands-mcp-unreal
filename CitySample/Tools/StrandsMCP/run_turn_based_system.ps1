# Turn-Based Strands Agent System Launcher
# Starts the complete system: MCP server, API server, and connects to Unreal Engine

param(
    [string]$S3Bucket = "",
    [int]$ApiPort = 8001,
    [int]$McpPort = 8000,
    [string]$UnrealHost = "127.0.0.1",
    [int]$UnrealPort = 17777,
    [switch]$Help
)

if ($Help) {
    Write-Host "Turn-Based Strands Agent System Launcher"
    Write-Host "Usage: .\run_turn_based_system.ps1 [options]"
    Write-Host ""
    Write-Host "Parameters:"
    Write-Host "  -S3Bucket <bucket>     S3 bucket for storing agent outputs"
    Write-Host "  -ApiPort <port>        Port for the API server (default: 8001)"
    Write-Host "  -McpPort <port>        Port for the MCP server (default: 8000)"
    Write-Host "  -UnrealHost <host>     Unreal Engine host (default: 127.0.0.1)"
    Write-Host "  -UnrealPort <port>     Unreal Engine port (default: 17777)"
    Write-Host "  -Help                  Show this help"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\run_turn_based_system.ps1"
    Write-Host "  .\run_turn_based_system.ps1 -S3Bucket 'my-strands-bucket'"
    Write-Host "  .\run_turn_based_system.ps1 -S3Bucket 'my-bucket' -ApiPort 8002"
    exit 0
}

$pythonPath = "MyProject\Intermediate\PipInstall\Scripts\python.exe"
$scriptDir = "CitySample\Tools\StrandsMCP"

Write-Host "Starting Turn-Based Strands Agent System..." -ForegroundColor Green
Write-Host "API Server Port: $ApiPort" -ForegroundColor Yellow
Write-Host "MCP Server Port: $McpPort" -ForegroundColor Yellow
Write-Host "Unreal Engine: ${UnrealHost}:${UnrealPort}" -ForegroundColor Yellow
if ($S3Bucket) {
    Write-Host "S3 Bucket: $S3Bucket" -ForegroundColor Cyan
}
Write-Host ""

# Function to check if a port is available
function Test-Port {
    param([int]$Port)
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Any, $Port)
        $listener.Start()
        $listener.Stop()
        return $true
    }
    catch {
        return $false
    }
}

# Check if ports are available
if (-not (Test-Port $ApiPort)) {
    Write-Host "ERROR: Port $ApiPort is already in use!" -ForegroundColor Red
    exit 1
}

if (-not (Test-Port $McpPort)) {
    Write-Host "ERROR: Port $McpPort is already in use!" -ForegroundColor Red
    exit 1
}

# Start MCP Server in background
Write-Host "Starting MCP Server on port $McpPort..." -ForegroundColor Green
$mcpArgs = @(
    "$scriptDir\server.py"
    "--port", $McpPort
)
$mcpProcess = Start-Process -FilePath $pythonPath -ArgumentList $mcpArgs -PassThru -NoNewWindow

# Wait a moment for MCP server to start
Start-Sleep -Seconds 2

# Check if MCP server started successfully
if ($mcpProcess.HasExited) {
    Write-Host "ERROR: MCP Server failed to start!" -ForegroundColor Red
    exit 1
}

Write-Host "MCP Server started successfully (PID: $($mcpProcess.Id))" -ForegroundColor Green

# Build API server arguments
$apiArgs = @(
    "$scriptDir\api_server.py"
    "--host", "0.0.0.0"
    "--port", $ApiPort
)

if ($S3Bucket) {
    $apiArgs += "--s3-bucket", $S3Bucket
}

# Start API Server
Write-Host "Starting API Server on port $ApiPort..." -ForegroundColor Green
try {
    & $pythonPath @apiArgs
}
catch {
    Write-Host "ERROR: API Server failed to start: $_" -ForegroundColor Red
    # Clean up MCP server
    if (!$mcpProcess.HasExited) {
        Write-Host "Stopping MCP Server..." -ForegroundColor Yellow
        $mcpProcess.Kill()
    }
    exit 1
}

# Cleanup on exit
Write-Host "Shutting down..." -ForegroundColor Yellow
if (!$mcpProcess.HasExited) {
    Write-Host "Stopping MCP Server..." -ForegroundColor Yellow
    $mcpProcess.Kill()
}