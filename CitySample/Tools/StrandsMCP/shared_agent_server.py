#!/usr/bin/env python3
"""
Shared Global Agent Server with Command Queue and Broadcasting
All clients share one agent that processes commands sequentially from a queue.
All WebSocket clients receive the same broadcast messages simultaneously.
"""

import os
import sys
import json
import uuid
import asyncio
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty

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
    print("Installing FastAPI...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "fastapi", "uvicorn", "websockets"])
    from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    import uvicorn

from turn_based_agent import TurnBasedAgent

# Custom callback handler for streaming thoughts
class WebSocketCallbackHandler:
    """Custom callback handler that broadcasts agent thoughts via WebSocket"""
    
    def __init__(self, agent_manager):
        self.agent_manager = agent_manager
        self.tool_count = 0
        self.previous_tool_use = None
        
    def __call__(self, **kwargs):
        """Handle streaming events from the Strands agent"""
        try:
            reasoningText = kwargs.get("reasoningText", False)
            data = kwargs.get("data", "")
            complete = kwargs.get("complete", False)
            current_tool_use = kwargs.get("current_tool_use", {})
            
            print(f"WebSocketCallbackHandler called with: reasoningText={bool(reasoningText)}, data='{data[:50]}...', complete={complete}, tool_use={current_tool_use.get('name', 'None')}")
            
            # Broadcast reasoning text (agent's thoughts)
            if reasoningText:
                print(f"Broadcasting agent thought: {reasoningText[:100]}...")
                asyncio.create_task(self.agent_manager.broadcast_update({
                    "type": "agent_thought",
                    "content": reasoningText,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }))
            
            # Broadcast response data
            if data:
                print(f"Broadcasting agent response: {data[:100]}...")
                asyncio.create_task(self.agent_manager.broadcast_update({
                    "type": "agent_response",
                    "content": data,
                    "complete": complete,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }))
            
            # Broadcast tool usage
            if current_tool_use and current_tool_use.get("name"):
                tool_name = current_tool_use.get("name", "Unknown tool")
                if self.previous_tool_use != current_tool_use:
                    self.previous_tool_use = current_tool_use
                    self.tool_count += 1
                    print(f"Broadcasting tool use: {tool_name}")
                    asyncio.create_task(self.agent_manager.broadcast_update({
                        "type": "tool_use",
                        "tool_name": tool_name,
                        "tool_number": self.tool_count,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }))
                    
        except Exception as e:
            print(f"Error in WebSocketCallbackHandler: {e}")
            import traceback
            traceback.print_exc()

# Pydantic models
class CommandRequest(BaseModel):
    prompt: str
    persona_traits: Optional[Dict[str, Any]] = None
    priority: int = 0  # Higher numbers = higher priority
    submitted_by: Optional[str] = None

@dataclass
class QueuedCommand:
    command_id: str
    prompt: str
    persona_traits: Optional[Dict[str, Any]]
    priority: int
    submitted_by: Optional[str]
    timestamp: str
    status: str  # "queued", "processing", "completed", "failed"

@dataclass
class GlobalAgentStatus:
    current_command: Optional[QueuedCommand]
    queue_length: int
    is_processing: bool
    last_update: str
    total_commands_processed: int

class SharedAgentManager:
    """Manages the shared global agent and command queue"""
    
    def __init__(self):
        self.global_agent: Optional[TurnBasedAgent] = None
        self.command_queue: Queue = Queue()
        self.processing_lock = threading.Lock()
        self.is_processing = False
        self.current_command: Optional[QueuedCommand] = None
        self.websocket_connections: List[WebSocket] = []
        self.command_history: List[QueuedCommand] = []
        self.total_processed = 0
        
        # Start the command processor thread
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.processor_future = self.executor.submit(self._process_command_queue)
    
    def initialize_agent(self):
        """Initialize the shared global agent"""
        if not self.global_agent:
            # Create WebSocket callback handler for streaming thoughts
            websocket_callback = WebSocketCallbackHandler(self)
            
            self.global_agent = TurnBasedAgent(
                session_id="global-shared-agent",
                mcp_url="http://localhost:8000/mcp",
                s3_bucket=os.getenv("STRANDS_S3_BUCKET"),
                callback_handler=websocket_callback
            )
            print("Global shared agent initialized with WebSocket streaming")
    
    async def add_command(self, prompt: str, persona_traits: Optional[Dict] = None, 
                         priority: int = 0, submitted_by: Optional[str] = None) -> str:
        """Add a command to the queue"""
        command_id = str(uuid.uuid4())[:8]
        
        queued_command = QueuedCommand(
            command_id=command_id,
            prompt=prompt,
            persona_traits=persona_traits,
            priority=priority,
            submitted_by=submitted_by,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status="queued"
        )
        
        self.command_queue.put(queued_command)
        self.command_history.append(queued_command)
        
        # Broadcast queue update
        await self.broadcast_update({
            "type": "command_queued",
            "command": asdict(queued_command),
            "queue_length": self.command_queue.qsize()
        })
        
        print(f"Command queued: {command_id} - {prompt[:50]}...")
        return command_id
    
    def _process_command_queue(self):
        """Background thread to process commands from queue"""
        while True:
            try:
                # Get next command (blocks until available)
                command = self.command_queue.get(timeout=1.0)
                
                with self.processing_lock:
                    if self.is_processing:
                        # Should not happen, but safety check
                        self.command_queue.put(command)  # Put it back
                        continue
                    
                    self.is_processing = True
                    self.current_command = command
                
                print(f"Processing command: {command.command_id}")
                self._execute_command(command)
                
                with self.processing_lock:
                    self.is_processing = False
                    self.current_command = None
                    self.total_processed += 1
                
                self.command_queue.task_done()
                
            except Empty:
                continue  # No commands in queue, keep waiting
            except Exception as e:
                print(f"Error processing command: {e}")
                with self.processing_lock:
                    self.is_processing = False
                    self.current_command = None
    
    def _execute_command(self, command: QueuedCommand):
        """Execute a single command"""
        try:
            # Ensure agent is initialized
            if not self.global_agent:
                self.initialize_agent()
            
            # Update command status
            command.status = "processing"
            asyncio.run(self.broadcast_update({
                "type": "command_started",
                "command": asdict(command)
            }))
            
            # Execute the turn
            turn_id = self.global_agent.start_turn(
                command.prompt, 
                command.persona_traits
            )
            
            # Poll for completion (blocking)
            max_wait = 300  # 5 minutes max
            poll_count = 0
            while poll_count < max_wait:
                status = self.global_agent.get_turn_status(turn_id)
                
                if status:
                    # Broadcast status update
                    asyncio.run(self.broadcast_update({
                        "type": "turn_update",
                        "command_id": command.command_id,
                        "turn_data": status
                    }))
                    
                    if status["status"] in ["completed", "error"]:
                        command.status = "completed" if status["status"] == "completed" else "failed"
                        break
                
                poll_count += 1
                asyncio.run(asyncio.sleep(1))
            
            # Final broadcast
            asyncio.run(self.broadcast_update({
                "type": "command_completed",
                "command": asdict(command),
                "queue_length": self.command_queue.qsize()
            }))
            
        except Exception as e:
            command.status = "failed"
            print(f"Command execution failed: {e}")
            asyncio.run(self.broadcast_update({
                "type": "command_failed",
                "command": asdict(command),
                "error": str(e)
            }))
    
    async def broadcast_update(self, message: Dict):
        """Broadcast message to all connected WebSocket clients"""
        if not self.websocket_connections:
            return
            
        message["timestamp"] = datetime.now(timezone.utc).isoformat()
        message_text = json.dumps(message)
        
        disconnected = []
        for websocket in self.websocket_connections:
            try:
                await websocket.send_text(message_text)
            except Exception as e:
                print(f"WebSocket send failed: {e}")
                disconnected.append(websocket)
        
        # Remove disconnected clients
        for ws in disconnected:
            if ws in self.websocket_connections:
                self.websocket_connections.remove(ws)
    
    def add_websocket(self, websocket: WebSocket):
        """Add a WebSocket connection"""
        self.websocket_connections.append(websocket)
        print(f"WebSocket connected. Total connections: {len(self.websocket_connections)}")
    
    def remove_websocket(self, websocket: WebSocket):
        """Remove a WebSocket connection"""
        if websocket in self.websocket_connections:
            self.websocket_connections.remove(websocket)
        print(f"WebSocket disconnected. Total connections: {len(self.websocket_connections)}")
    
    def get_status(self) -> GlobalAgentStatus:
        """Get current global agent status"""
        with self.processing_lock:
            return GlobalAgentStatus(
                current_command=self.current_command,
                queue_length=self.command_queue.qsize(),
                is_processing=self.is_processing,
                last_update=datetime.now(timezone.utc).isoformat(),
                total_commands_processed=self.total_processed
            )
    
    def get_queue_status(self) -> List[Dict]:
        """Get current queue status"""
        queue_items = []
        temp_queue = Queue()
        
        # Extract items to view them
        while not self.command_queue.empty():
            try:
                item = self.command_queue.get_nowait()
                queue_items.append(asdict(item))
                temp_queue.put(item)
            except Empty:
                break
        
        # Put items back
        while not temp_queue.empty():
            self.command_queue.put(temp_queue.get_nowait())
        
        return queue_items
    
    def get_history(self) -> List[Dict]:
        """Get command history"""
        return [asdict(cmd) for cmd in self.command_history[-50:]]  # Last 50 commands

# Create FastAPI app
app = FastAPI(
    title="Shared Strands Agent Server",
    description="Global shared agent with command queue and broadcasting",
    version="1.0.0"
)

# Add CORS middleware with specific origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://d1u690gz6k82jo.cloudfront.net",
        "https://thedimessquare.com", 
        "https://www.thedimessquare.com",
        "https://api.thedimessquare.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global shared agent manager
shared_manager = SharedAgentManager()

@app.get("/")
async def root():
    """Health check and status"""
    status = shared_manager.get_status()
    return {
        "service": "Shared Strands Agent Server",
        "status": "running",
        "agent_status": asdict(status),
        "connected_clients": len(shared_manager.websocket_connections),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.post("/api/add_command")
async def add_command(request: CommandRequest):
    """Add a command to the global queue"""
    try:
        command_id = await shared_manager.add_command(
            prompt=request.prompt,
            persona_traits=request.persona_traits,
            priority=request.priority,
            submitted_by=request.submitted_by
        )
        
        return {
            "success": True,
            "command_id": command_id,
            "queue_position": shared_manager.command_queue.qsize(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/status")
async def get_status():
    """Get global agent status"""
    status = shared_manager.get_status()
    return asdict(status)

@app.get("/api/queue")
async def get_queue():
    """Get current queue status"""
    queue_status = shared_manager.get_queue_status()
    return {
        "queue": queue_status,
        "queue_length": len(queue_status),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/history")
async def get_history():
    """Get command history"""
    history = shared_manager.get_history()
    return {
        "history": history,
        "total_commands": len(history),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.websocket("/ws")
async def websocket_global_endpoint(websocket: WebSocket):
    """Global WebSocket endpoint - all clients get the same messages"""
    await websocket.accept()
    shared_manager.add_websocket(websocket)
    
    # Send initial status
    status = shared_manager.get_status()
    await websocket.send_text(json.dumps({
        "type": "initial_status",
        "agent_status": asdict(status),
        "connected_clients": len(shared_manager.websocket_connections),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }))
    
    try:
        while True:
            try:
                # Wait for client messages (ping, etc.)
                data = await websocket.receive_text()
                message = json.loads(data)
                
                if message.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                elif message.get("type") == "get_status":
                    status = shared_manager.get_status()
                    await websocket.send_text(json.dumps({
                        "type": "status_response",
                        "agent_status": asdict(status)
                    }))
                
            except asyncio.TimeoutError:
                # Send periodic heartbeat
                await websocket.send_text(json.dumps({
                    "type": "heartbeat",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "connected_clients": len(shared_manager.websocket_connections)
                }))
                
    except WebSocketDisconnect:
        pass
    finally:
        shared_manager.remove_websocket(websocket)

# Legacy compatibility endpoints
@app.post("/api/start_turn")
async def start_turn_legacy(request: Dict[str, Any]):
    """Legacy compatibility - maps to add_command"""
    command_id = await shared_manager.add_command(
        prompt=request.get("prompt", ""),
        persona_traits=request.get("persona_traits"),
        submitted_by="legacy_client"
    )
    
    return {
        "success": True,
        "turn_id": command_id,  # For compatibility
        "command_id": command_id,
        "status": "queued",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/turn_status/{turn_id}")
async def get_turn_status_legacy(turn_id: str):
    """Legacy compatibility - get command status"""
    # Find command in history
    for cmd in shared_manager.command_history:
        if cmd.command_id == turn_id:
            return {
                "turn_id": turn_id,
                "status": cmd.status,
                "prompt": cmd.prompt,
                "timestamp": cmd.timestamp,
                "command_id": cmd.command_id
            }
    
    raise HTTPException(status_code=404, detail="Command not found")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Shared Strands Agent Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8001, help="Port to bind to")
    parser.add_argument("--s3-bucket", help="S3 bucket for outputs")
    parser.add_argument("--ssl", action="store_true", help="Enable HTTPS with SSL certificates")
    
    args = parser.parse_args()
    
    if args.s3_bucket:
        os.environ["STRANDS_S3_BUCKET"] = args.s3_bucket
    
    print(f"Starting Shared Strands Agent Server on {args.host}:{args.port}")
    if args.ssl:
        print("HTTPS enabled with SSL certificates")
    print("All clients will share the same global agent")
    print("Commands are processed sequentially from a shared queue")
    
    # Configure SSL if requested
    ssl_keyfile = None
    ssl_certfile = None
    if args.ssl:
        ssl_keyfile = "key.pem"
        ssl_certfile = "cert.pem"
        if not (Path(ssl_keyfile).exists() and Path(ssl_certfile).exists()):
            print("SSL certificates not found! Please generate cert.pem and key.pem")
            sys.exit(1)
    
    uvicorn.run(
        "shared_agent_server:app",
        host=args.host,
        port=args.port,
        reload=False,  # Don't reload in shared mode
        log_level="info",
        ssl_keyfile=ssl_keyfile,
        ssl_certfile=ssl_certfile
    )