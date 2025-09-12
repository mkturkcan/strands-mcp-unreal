# Persona Agent Runner

PowerShell script to easily run the Strands MCP Persona Agent in Unreal Engine.

## Quick Start

```powershell
.\run_persona.ps1
```

### Multi-Agent Demo

To launch three simultaneous personas controlling separate Unreal agents:

```powershell
./run_multi_agent_demo.ps1
```

This spawns Explorer, Guardian, and Dreamer personas targeting agent IDs `agent-1`, `agent-2`, and `agent-3` respectively.

## Commands

### Basic Usage
```powershell
# Run with default Explorer persona for 60 seconds
.\run_persona.ps1

# Run specific persona for 2 minutes  
.\run_persona.ps1 -Persona "Dreamer" -Duration 120

# Show help
.\run_persona.ps1 -Help
```

### Advanced Usage
```powershell
# Custom personality traits
.\run_persona.ps1 -Persona "Guardian" -Archetype "cautious" -BaseEmotion "protective" -Goals @("protect", "watch", "defend")

# Continue previous session
.\run_persona.ps1 -SessionId "my-session-123" -LoadState "path\to\state.json"

# Enable cloud persistence
.\run_persona.ps1 -UseS3
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `-Persona` | String | "Explorer" | Persona name |
| `-Duration` | Int | 60 | Runtime in seconds |
| `-Archetype` | String | "explorer" | Personality type (explorer, cautious, social, wanderer) |
| `-BaseEmotion` | String | "excited" | Starting emotion |
| `-Personality` | String | "Adventurous spirit..." | Personality description |
| `-Goals` | Array | @("explore", "climb", "discover secrets") | Character goals |
| `-SessionId` | String | "" | Session ID for continuity |
| `-LoadState` | String | "" | Path to previous state file |
| `-UseS3` | Switch | False | Enable S3 state persistence |

## Preset Personas

### Explorer
```powershell
.\run_persona.ps1 -Persona "Explorer" -Archetype "explorer" -BaseEmotion "excited"
```

### Dreamer  
```powershell
.\run_persona.ps1 -Persona "Dreamer" -Archetype "wanderer" -BaseEmotion "whimsical" -Goals @("find beauty", "contemplate existence", "follow butterflies")
```

### Guardian
```powershell
.\run_persona.ps1 -Persona "Guardian" -Archetype "cautious" -BaseEmotion "protective" -Goals @("protect", "watch", "defend")
```

## Output

- Console: Real-time thoughts and actions
- OBS File: `CitySample/Saved/OBS/persona_thoughts.txt` (for streaming)
- State Files: `CitySample/Saved/PersonaStates/[PersonaName]/`

## Requirements

- Unreal Engine project with Strands MCP tools
- Python environment in `MyProject/Intermediate/PipInstall/`
- PowerShell execution policy allowing scripts

## External Tools

To keep this repository lightweight, binary packages such as
`win-acme` (for certificate management) and `nginx` are not
included. Download and install them separately if your workflow
requires them.
