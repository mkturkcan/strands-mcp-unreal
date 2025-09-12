# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Structure

This repository contains multiple Unreal Engine 5.6 projects with integrated Strands MCP (Model Context Protocol) tools for AI agent development:

**PRIMARY WORKING BRANCH: CitySample** - This is the main project where active development occurs.

- **CitySample** - Main UE 5.6 working project with comprehensive city simulation, including Mass Entity crowd systems, vehicle traffic, and advanced rendering features. All Strands MCP development happens here.
- **MyProject** - Secondary UE 5.6 project with basic MetaHuman integration and Strands MCP support (used primarily for testing)
- **Tools/StrandsMCP** - Python-based AI agent system for controlling characters in Unreal Engine
- **Plugins/StrandsInputServer** - Custom UE plugin that enables MCP communication with Python agents

## Key Architecture Components

### Strands MCP System
The core AI agent system consists of:
Since 
**Turn-Based System (NEW - Production Ready):**
- **turn_based_agent.py** - Main turn-based agent system with S3 integration
- **api_server.py** - REST API and WebSocket server for CloudFront integration
- **run_turn_based_system.ps1** - Complete system launcher
- **frontend_integration.md** - Integration guide for CloudFront frontend

**Legacy Components:**
- **persona_agent.py** - Continuous persona-based agent with consciousness simulation
- **agent_test.py** - Single-turn agent testing framework
- **server.py** - MCP server for handling Unreal Engine communication

### Turn-Based System Architecture
```
CloudFront Frontend (https://d1u690gz6k82jo.cloudfront.net/)
         ↓
    API Server (port 8001)
         ↓
  Turn-Based Agent
         ↓
    MCP Client → MCP Server (port 8000) → Unreal Engine StrandsInputServer
         ↓
   S3 Storage (Screenshots, States, Logs)
```

### Unreal Engine Integration
Both projects use the **StrandsInputServer** plugin which enables:
- Real-time communication between Python agents and UE characters
- Remote control of character movement, actions, and behaviors
- State persistence and session management
- Turn-based gameplay with screenshot and state capture

## Common Development Commands

### Turn-Based Agent System (NEW - CloudFront Integration)
```powershell
# Start complete turn-based system with S3 integration
.\CitySample\Tools\StrandsMCP\run_turn_based_system.ps1 -S3Bucket "your-strands-bucket"

# Basic turn-based system (no S3)
.\CitySample\Tools\StrandsMCP\run_turn_based_system.ps1

# Custom ports for development
.\CitySample\Tools\StrandsMCP\run_turn_based_system.ps1 -ApiPort 8002 -McpPort 8001
```

**API Endpoints for CloudFront Frontend:**
- `POST /api/start_turn` - Start a new agent turn
- `GET /api/turn_status/{turn_id}` - Get turn status
- `POST /api/interact` - Compatibility with existing frontend
- `WebSocket /ws/{session_id}` - Real-time streaming

### Running Persona Agents (Legacy)
```powershell
# Basic usage - run Explorer persona for 60 seconds
.\run_persona.ps1

# Custom persona with specific traits
.\run_persona.ps1 -Persona "Dreamer" -Duration 120 -Archetype "wanderer" -BaseEmotion "whimsical"

# With session continuity and S3 persistence
.\run_persona.ps1 -SessionId "session-123" -LoadState "path\to\state.json" -UseS3
```

### Direct Python Agent Commands
```bash
# NEW: Run turn-based agent
"MyProject\Intermediate\PipInstall\Scripts\python.exe" "CitySample\Tools\StrandsMCP\turn_based_agent.py" --prompt "Look around" --s3-bucket "bucket-name"

# Run single-turn agent test
"MyProject\Intermediate\PipInstall\Scripts\python.exe" "CitySample\Tools\StrandsMCP\agent_test.py" --prompt "Run around."

# Start MCP server
"MyProject\Intermediate\PipInstall\Scripts\python.exe" "CitySample\Tools\StrandsMCP\server.py"

# Run persona agent directly (continuous)
"MyProject\Intermediate\PipInstall\Scripts\python.exe" "CitySample\Tools\StrandsMCP\persona_agent.py" --persona "Explorer" --duration 60
```

## Python Environment Setup

The projects use isolated Python environments located at:
- `MyProject\Intermediate\PipInstall\Scripts\python.exe` - Python executable
- `MyProject\Intermediate\PipInstall\Lib\site-packages\` - Installed packages

Dependencies are managed automatically by Unreal Engine's PipInstall system. The Strands library provides:
- MCP client/server communication
- Agent behavior management
- Session persistence
- Unreal Engine tool integration

## Output and Persistence

### OBS Integration
- Persona thoughts stream to: `CitySample\Saved\OBS\persona_thoughts.txt`
- Real-time consciousness simulation for streaming

### State Management
- Local states: `CitySample\Saved\PersonaStates\[PersonaName]\`
- Session continuity with JSON state files
- Optional S3 cloud persistence for distributed sessions

## Plugin Configuration

Both projects enable the **StrandsInputServer** plugin in their .uproject files, supporting Win64 and Linux platforms. The plugin handles:
- WebSocket/HTTP communication with Python agents
- Character control APIs
- Real-time state synchronization

## Development Notes

- Always use the provided Python environment in `MyProject\Intermediate\PipInstall\`
- Persona agents support customizable archetypes: explorer, cautious, social, wanderer
- Session IDs enable continuous character behaviors across runs
- The system supports multiple concurrent agents with different personas