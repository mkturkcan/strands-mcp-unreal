# Multi-Agent Persona Demo
# Launches three persona agents, each targeting a unique Unreal agent id.

Write-Host "Starting three Strands personas..." -ForegroundColor Green

$pythonPath = "MyProject\Intermediate\PipInstall\Scripts\python.exe"
$agentScript = "CitySample\Tools\StrandsMCP\persona_agent.py"
$workDir = "CitySample\Tools\StrandsMCP"

$agents = @(
    @{ Id = "agent-1"; Persona = "Explorer" },
    @{ Id = "agent-2"; Persona = "Guardian" },
    @{ Id = "agent-3"; Persona = "Dreamer" }
)

foreach ($a in $agents) {
    Write-Host "Launching $($a.Persona) -> $($a.Id)" -ForegroundColor Yellow
    Start-Process -FilePath $pythonPath -ArgumentList $agentScript, "--persona", $a.Persona, "--agent-id", $a.Id, "--duration", "60" -WorkingDirectory $workDir -WindowStyle Minimized | Out-Null
}

Write-Host "Agents started. Check Unreal for three independent characters." -ForegroundColor Green
