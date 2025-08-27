# Turn-Based Strands Agent System - Frontend Integration Guide

This document explains how to integrate the turn-based Strands agent system with your CloudFront frontend.

## System Overview

The turn-based system consists of:

1. **Turn-Based Agent** (`turn_based_agent.py`) - Core agent logic with S3 integration
2. **API Server** (`api_server.py`) - REST API and WebSocket streaming
3. **MCP Server** (`server.py`) - Provides tools for Unreal Engine interaction
4. **Frontend Integration** - Your CloudFront frontend at `https://d1u690gz6k82jo.cloudfront.net/`

## Architecture Flow

```
CloudFront Frontend → API Server → Turn-Based Agent → Strands MCP → Unreal Engine
                          ↓
                     S3 Storage (Screenshots, States, Logs)
                          ↓
                  WebSocket Streaming (Real-time updates)
```

## Starting the System

### Quick Start
```powershell
# Basic setup (local development)
.\run_turn_based_system.ps1

# With S3 integration
.\run_turn_based_system.ps1 -S3Bucket "your-strands-bucket"

# Custom ports
.\run_turn_based_system.ps1 -S3Bucket "your-bucket" -ApiPort 8002 -McpPort 8001
```

### Manual Start
```bash
# Start MCP server
python CitySample/Tools/StrandsMCP/server.py --port 8000

# Start API server (in another terminal)
python CitySample/Tools/StrandsMCP/api_server.py --port 8001 --s3-bucket "your-bucket"
```

## API Endpoints

### 1. Start a Turn
```http
POST /api/start_turn
Content-Type: application/json

{
  "prompt": "Explore the area and look for interesting objects",
  "session_id": "player-123",
  "persona_traits": {
    "archetype": "explorer",
    "base_emotion": "excited",
    "personality": "Adventurous spirit who loves discovering new places",
    "goals": ["explore", "climb", "discover secrets"]
  },
  "s3_bucket": "optional-bucket-override"
}
```

Response:
```json
{
  "success": true,
  "turn_id": "abc12345",
  "session_id": "player-123",
  "status": "started",
  "timestamp": "2025-08-27T10:30:00Z"
}
```

### 2. Get Turn Status
```http
GET /api/turn_status/{turn_id}
```

Response:
```json
{
  "turn_id": "abc12345",
  "session_id": "player-123",
  "timestamp": "2025-08-27T10:30:00Z",
  "prompt": "Explore the area...",
  "status": "completed",
  "agent_response": "I'm moving forward to explore...",
  "screenshot_path": "/path/to/screenshot.png",
  "env_state": {
    "pos": [1234.5, 5678.9, 90.1],
    "rot": {"yaw": 45.0},
    "speed": 150.0
  },
  "thoughts": ["I should look around", "Moving forward carefully"],
  "s3_urls": {
    "screenshot": "https://bucket.s3.region.amazonaws.com/screenshot.png",
    "env_state": "https://bucket.s3.region.amazonaws.com/env_state.json",
    "turn_data": "https://bucket.s3.region.amazonaws.com/turn_data.json"
  }
}
```

### 3. Compatibility Endpoint (for existing frontend)
```http
POST /api/interact
Content-Type: application/json

{
  "action": "set_goal",
  "characterId": "player-1",
  "goal": "Find the nearest building",
  "persona": {
    "archetype": "explorer",
    "mood": "curious"
  }
}
```

## WebSocket Integration

### Connect to WebSocket
```javascript
const ws = new WebSocket('ws://localhost:8001/ws/player-123');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    switch(data.type) {
        case 'turn_update':
            updateTurnDisplay(data.data);
            break;
        case 'status_update':
            updateAgentStatus(data.data);
            break;
    }
};

// Send ping to keep connection alive
setInterval(() => {
    ws.send(JSON.stringify({type: 'ping'}));
}, 30000);
```

## Frontend Integration Example

### JavaScript Integration
```javascript
class StrandsAgentClient {
    constructor(apiUrl = 'http://localhost:8001') {
        this.apiUrl = apiUrl;
        this.websocket = null;
        this.sessionId = `session-${Date.now()}`;
    }
    
    async startTurn(prompt, personaTraits = null) {
        const response = await fetch(`${this.apiUrl}/api/start_turn`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                prompt: prompt,
                session_id: this.sessionId,
                persona_traits: personaTraits
            })
        });
        
        return await response.json();
    }
    
    async getTurnStatus(turnId) {
        const response = await fetch(`${this.apiUrl}/api/turn_status/${turnId}`);
        return await response.json();
    }
    
    connectWebSocket() {
        this.websocket = new WebSocket(`ws://localhost:8001/ws/${this.sessionId}`);
        
        this.websocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleWebSocketMessage(data);
        };
    }
    
    handleWebSocketMessage(data) {
        // Handle real-time updates
        console.log('Agent update:', data);
    }
}

// Usage example
const agent = new StrandsAgentClient();
agent.connectWebSocket();

// Start a turn when "Run Turn" button is clicked
async function runTurn() {
    const prompt = "Look around and describe what you see";
    const persona = {
        archetype: "explorer",
        base_emotion: "excited",
        personality: "Curious explorer",
        goals: ["explore", "observe", "describe"]
    };
    
    const result = await agent.startTurn(prompt, persona);
    console.log('Turn started:', result.turn_id);
}
```

## S3 Storage Structure

When S3 integration is enabled, files are stored with this structure:

```
s3://your-bucket/
└── strands-turns/
    └── {session_id}/
        └── {turn_id}/
            ├── screenshot.png          # Environment screenshot
            ├── env_state.json         # Environment state data
            └── turn_data.json         # Complete turn information
```

## Environment Variables

Set these environment variables for production:

```bash
export STRANDS_S3_BUCKET="your-strands-bucket"
export AWS_REGION="us-west-2"
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
```

## Troubleshooting

### Common Issues

1. **Port conflicts**: Use different ports if 8000/8001 are taken
2. **Unreal Engine not responding**: Make sure StrandsInputServer plugin is active
3. **S3 upload failures**: Check AWS credentials and bucket permissions
4. **WebSocket disconnections**: Implement reconnection logic in frontend

### Debug Mode

Start with debug logging:
```bash
python api_server.py --port 8001 --s3-bucket "your-bucket" --log-level debug
```

### Testing the API

Test with curl:
```bash
# Start a turn
curl -X POST http://localhost:8001/api/start_turn \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Look around", "session_id": "test-123"}'

# Check status
curl http://localhost:8001/api/turn_status/abc12345
```

## Production Deployment

For production deployment:

1. **Use HTTPS**: Configure SSL certificates
2. **Set CORS origins**: Restrict to your CloudFront domain
3. **Use environment variables**: Don't hardcode sensitive values
4. **Monitor S3 costs**: Implement lifecycle policies for old data
5. **Scale with load balancer**: Use multiple API server instances if needed

## Integration with Your Frontend

To integrate with your existing CloudFront frontend at `https://d1u690gz6k82jo.cloudfront.net/`:

1. Update the API endpoint URLs to point to your deployed API server
2. Modify the "Run Turn" button to call `/api/start_turn`
3. Use WebSocket connection for real-time updates
4. Display agent responses and S3-hosted screenshots/data
5. Implement persona selection UI that maps to the `persona_traits` parameter

The system is designed to be compatible with your existing `/api/interact` endpoint structure while providing enhanced turn-based functionality.