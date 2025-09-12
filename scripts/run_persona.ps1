# Persona Agent PowerShell Runner
# Easy way to run the Strands MCP Persona Agent

param(
    [string]$Persona = "Explorer",
    [int]$Duration = 60,
    [string]$Archetype = "explorer",
    [string]$BaseEmotion = "excited",
    [string]$Personality = "Adventurous spirit who loves discovering new places",
    [string[]]$Goals = @("explore", "climb", "discover secrets"),
    [string]$SessionId = "",
    [string]$LoadState = "",
    [switch]$UseS3,
    [switch]$Help
)

if ($Help) {
    Write-Host "Persona Agent PowerShell Runner"
    Write-Host "Usage: .\run_persona.ps1 [options]"
    Write-Host ""
    Write-Host "Parameters:"
    Write-Host "  -Persona <name>      Persona name (default: Explorer)"
    Write-Host "  -Duration <seconds>  How long to run (default: 60)"
    Write-Host "  -Archetype <type>    Personality archetype (explorer, cautious, social, wanderer)"
    Write-Host "  -BaseEmotion <mood>  Starting emotion (excited, curious, calm, etc.)"
    Write-Host "  -Personality <desc>  Personality description"
    Write-Host "  -Goals <array>       Array of goals (default: explore, climb, discover secrets)"
    Write-Host "  -SessionId <id>      Session ID for continuity"
    Write-Host "  -LoadState <path>    Path to previous state file"
    Write-Host "  -UseS3               Enable S3 state persistence"
    Write-Host "  -Help                Show this help"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\run_persona.ps1"
    Write-Host "  .\run_persona.ps1 -Persona 'Dreamer' -Duration 120 -Archetype 'wanderer'"
    Write-Host "  .\run_persona.ps1 -Persona 'Guardian' -BaseEmotion 'protective' -Goals @('protect', 'watch', 'defend')"
    exit 0
}

# Build the traits JSON
$traitsHash = @{
    archetype = $Archetype
    base_emotion = $BaseEmotion
    personality = $Personality
    goals = $Goals
}

$traitsJson = $traitsHash | ConvertTo-Json -Compress

# Build the Python command
$pythonPath = "MyProject\Intermediate\PipInstall\Scripts\python.exe"
$scriptPath = "CitySample\Tools\StrandsMCP\persona_agent.py"

$arguments = @(
    $scriptPath
    "--persona", $Persona
    "--duration", $Duration
    "--traits", $traitsJson
)

if ($SessionId) { $arguments += "--session-id", $SessionId }
if ($LoadState) { $arguments += "--load-state", $LoadState }
if ($UseS3) { $arguments += "--use-s3" }

Write-Host "Starting Persona Agent: $Persona" -ForegroundColor Green
Write-Host "Duration: $Duration seconds" -ForegroundColor Yellow
Write-Host "Archetype: $Archetype" -ForegroundColor Cyan
Write-Host "Base Emotion: $BaseEmotion" -ForegroundColor Magenta
Write-Host "Goals: $($Goals -join ', ')" -ForegroundColor Blue
Write-Host ""
Write-Host "Command: $pythonPath $($arguments -join ' ')" -ForegroundColor Gray
Write-Host ""

# Run the persona agent
& $pythonPath @arguments