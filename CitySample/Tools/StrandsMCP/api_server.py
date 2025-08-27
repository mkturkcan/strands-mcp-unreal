#!/usr/bin/env python3
"""
API Server for Turn-Based Strands Agent System
Provides REST API and WebSocket streaming for CloudFront frontend integration
"""

import os
import sys
import json
import uuid
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from dataclasses import asdict

# Add Python path for UE dependencies
_project_root = Path(__file__).resolve().parents[2]
_site = _project_root / "Intermediate" / "PipInstall" / "Lib" / "site-packages"
if str(_site) not in sys.path:
    sys.path.insert(0, str(_site))

try:
    from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    print("FastAPI not found. Installing...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "fastapi", "uvicorn", "websockets"])
    from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    import uvicorn

from turn_based_agent import TurnBasedAgent

# Pydantic models for API requests
class TurnRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = None
    persona_traits: Optional[Dict[str, Any]] = None
    s3_bucket: Optional[str] = None

class PersonaTraits(BaseModel):
    archetype: str = "explorer"
    base_emotion: str = "excited"
    personality: str = "Adventurous spirit who loves discovering new places"
    goals: List[str] = ["explore", "discover", "interact"]

# Global state management
class AgentManager:
    def __init__(self):
        self.active_agents: Dict[str, TurnBasedAgent] = {}
        self.websocket_connections: List[WebSocket] = []
    
    def get_or_create_agent(self, session_id: str, s3_bucket: Optional[str] = None) -> TurnBasedAgent:
        """Get existing agent or create new one"""
        if session_id not in self.active_agents:
            self.active_agents[session_id] = TurnBasedAgent(
                session_id=session_id,
                s3_bucket=s3_bucket or os.getenv("STRANDS_S3_BUCKET")
            )
        return self.active_agents[session_id]
    
    async def broadcast_update(self, session_id: str, update_data: Dict):
        """Broadcast update to all connected WebSocket clients"""
        message = {
            "type": "turn_update",
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": update_data
        }
        
        disconnected = []
        for websocket in self.websocket_connections:
            try:
                await websocket.send_text(json.dumps(message))
            except:
                disconnected.append(websocket)
        
        # Remove disconnected clients
        for ws in disconnected:
            if ws in self.websocket_connections:
                self.websocket_connections.remove(ws)

# Create FastAPI app
app = FastAPI(
    title="Strands Turn-Based Agent API",
    description="API for controlling turn-based Strands agents in Unreal Engine",
    version="1.0.0"
)

# Add CORS middleware for CloudFront integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your CloudFront domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global agent manager
agent_manager = AgentManager()

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "Strands Turn-Based Agent API",
        "status": "running",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "active_sessions": len(agent_manager.active_agents)
    }

@app.post("/api/start_turn")
async def start_turn(request: TurnRequest):
    """Start a new turn for the agent"""
    try:
        session_id = request.session_id or f"session-{int(datetime.now().timestamp())}"
        
        # Get or create agent
        agent = agent_manager.get_or_create_agent(session_id, request.s3_bucket)
        
        # Start the turn
        turn_id = agent.start_turn(request.prompt, request.persona_traits)
        
        response = {
            "success": True,
            "turn_id": turn_id,
            "session_id": session_id,
            "status": "started",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Broadcast to WebSocket clients
        await agent_manager.broadcast_update(session_id, response)
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/turn_status/{turn_id}")
async def get_turn_status(turn_id: str, session_id: Optional[str] = None):
    """Get the status of a specific turn"""
    try:
        # Find the agent with this turn
        target_agent = None
        for agent in agent_manager.active_agents.values():
            status = agent.get_turn_status(turn_id)
            if status:
                target_agent = agent
                break
        
        if not target_agent:
            raise HTTPException(status_code=404, detail="Turn not found")
        
        status = target_agent.get_turn_status(turn_id)
        return status
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/session/{session_id}/status")
async def get_session_status(session_id: str):
    """Get the current status of a session"""
    try:
        if session_id not in agent_manager.active_agents:
            return {"session_id": session_id, "status": "not_found"}
        
        agent = agent_manager.active_agents[session_id]
        current_turn = agent.get_current_turn_status()
        
        return {
            "session_id": session_id,
            "status": "active",
            "current_turn": current_turn,
            "total_turns": len(agent.turns_history)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/session/{session_id}/history")
async def get_session_history(session_id: str):
    """Get the full history of turns for a session"""
    try:
        if session_id not in agent_manager.active_agents:
            raise HTTPException(status_code=404, detail="Session not found")
        
        agent = agent_manager.active_agents[session_id]
        history = agent.get_session_history()
        
        return {
            "session_id": session_id,
            "turns": history,
            "total_turns": len(history)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/interact")
async def interact_with_agent(request: Dict[str, Any]):
    """
    Compatibility endpoint for existing frontend /api/interact calls
    Maps to the turn-based system
    """
    try:
        # Extract relevant data from frontend request
        action = request.get("action", "run_turn")
        character_id = request.get("characterId", "default")
        session_id = f"frontend-{character_id}"
        
        # Handle different action types
        if action == "set_goal":
            prompt = f"Set new goal: {request.get('goal', 'explore the environment')}"
        elif action == "send_message":
            prompt = f"Respond to message: {request.get('message', 'Hello')}"
        elif action == "nudge_action":
            prompt = f"Perform action: {request.get('nudge', 'look around')}"
        else:
            prompt = request.get("prompt", "Continue your current activity")
        
        # Extract persona traits if available
        persona_traits = None
        if "persona" in request:
            persona_data = request["persona"]
            persona_traits = {
                "archetype": persona_data.get("archetype", "explorer"),
                "base_emotion": persona_data.get("mood", "excited"),
                "personality": persona_data.get("personality", "Curious and adventurous"),
                "goals": persona_data.get("goals", ["explore", "interact"])
            }
        
        # Start turn
        agent = agent_manager.get_or_create_agent(session_id)
        turn_id = agent.start_turn(prompt, persona_traits)
        
        response = {
            "success": True,
            "message": "Turn started",
            "turnId": turn_id,
            "sessionId": session_id,
            "characterId": character_id
        }
        
        # Broadcast update
        await agent_manager.broadcast_update(session_id, response)
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time turn updates"""
    await websocket.accept()
    agent_manager.websocket_connections.append(websocket)
    
    try:
        # Send initial session state
        if session_id in agent_manager.active_agents:
            agent = agent_manager.active_agents[session_id]
            current_status = agent.get_current_turn_status()
            if current_status:
                await websocket.send_text(json.dumps({
                    "type": "session_state",
                    "session_id": session_id,
                    "data": current_status
                }))
        
        # Keep connection alive and handle messages
        while True:
            try:
                # Wait for messages from client
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Handle client messages (ping, status requests, etc.)
                if message.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                elif message.get("type") == "get_status":
                    if session_id in agent_manager.active_agents:
                        agent = agent_manager.active_agents[session_id]
                        status = agent.get_current_turn_status()
                        await websocket.send_text(json.dumps({
                            "type": "status_response",
                            "data": status
                        }))
                
            except asyncio.TimeoutError:
                # Send periodic status updates
                if session_id in agent_manager.active_agents:
                    agent = agent_manager.active_agents[session_id]
                    status = agent.get_current_turn_status()
                    if status and status.get("status") in ["running", "completed"]:
                        await websocket.send_text(json.dumps({
                            "type": "status_update",
                            "session_id": session_id,
                            "data": status
                        }))
                
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in agent_manager.websocket_connections:
            agent_manager.websocket_connections.remove(websocket)

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    for agent in agent_manager.active_agents.values():
        agent.cleanup()

# Development server
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Strands API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8001, help="Port to bind to")
    parser.add_argument("--s3-bucket", help="Default S3 bucket for outputs")
    
    args = parser.parse_args()
    
    # Set environment variable for S3 bucket
    if args.s3_bucket:
        os.environ["STRANDS_S3_BUCKET"] = args.s3_bucket
    
    print(f"Starting Strands API Server on {args.host}:{args.port}")
    if args.s3_bucket:
        print(f"Using S3 bucket: {args.s3_bucket}")
    
    uvicorn.run(
        "api_server:app", 
        host=args.host, 
        port=args.port, 
        reload=True,
        log_level="info"
    )