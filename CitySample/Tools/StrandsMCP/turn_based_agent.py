#!/usr/bin/env python3
"""
Turn-based Strands Agent System with S3 Integration
Bridges CloudFront frontend to Unreal Engine Strands agents with persistent state
"""

import os
import sys
import json
import time
import socket
import uuid
import asyncio
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor

# Add likely native DLL locations to the DLL search path
def _add_dll_dir(p: Path):
    try:
        if p and p.is_dir():
            os.add_dll_directory(str(p))
    except Exception:
        pass

# UE project's venv site-packages
_project_root = Path(__file__).resolve().parents[2]
_site = _project_root / "Intermediate" / "PipInstall" / "Lib" / "site-packages"

if str(_site) not in sys.path:
    sys.path.insert(0, str(_site))

# Common native lib locations
for sub in ["numpy/.libs", "numpy/core", "cv2", ""]:
    _add_dll_dir((_site / sub) if sub else _site)

from mcp.client.streamable_http import streamablehttp_client
from strands.agent import Agent
from strands.tools.mcp.mcp_client import MCPClient
from strands.session.file_session_manager import FileSessionManager
from strands.hooks import BeforeInvocationEvent, AfterInvocationEvent, HookProvider

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None
    ClientError = Exception

@dataclass
class TurnState:
    """Represents the state of a single turn"""
    turn_id: str
    session_id: str
    timestamp: str
    prompt: str
    status: str  # "pending", "running", "completed", "error"
    agent_response: Optional[str] = None
    screenshot_path: Optional[str] = None
    env_state: Optional[Dict] = None
    thoughts: List[str] = None
    error_message: Optional[str] = None
    s3_urls: Dict[str, str] = None  # screenshot, state, logs
    
    def __post_init__(self):
        if self.thoughts is None:
            self.thoughts = []
        if self.s3_urls is None:
            self.s3_urls = {}

class S3Manager:
    """Handles S3 operations for storing Strands outputs"""
    
    def __init__(self, bucket_name: str, region: str = "us-west-2"):
        self.bucket_name = bucket_name
        self.region = region
        self.s3_client = None
        if boto3:
            try:
                self.s3_client = boto3.client('s3', region_name=region)
            except Exception as e:
                print(f"Failed to initialize S3 client: {e}")
    
    def upload_file(self, local_path: Path, s3_key: str) -> Optional[str]:
        """Upload a file to S3 and return the URL"""
        if not self.s3_client or not local_path.exists():
            return None
            
        try:
            self.s3_client.upload_file(
                str(local_path),
                self.bucket_name,
                s3_key,
                ExtraArgs={'ContentType': self._get_content_type(local_path)}
            )
            return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"
        except Exception as e:
            print(f"Failed to upload {local_path} to S3: {e}")
            return None
    
    def upload_json(self, data: Dict, s3_key: str) -> Optional[str]:
        """Upload JSON data directly to S3"""
        if not self.s3_client:
            return None
            
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=json.dumps(data, indent=2),
                ContentType='application/json'
            )
            return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"
        except Exception as e:
            print(f"Failed to upload JSON to S3: {e}")
            return None
    
    def _get_content_type(self, file_path: Path) -> str:
        """Determine content type based on file extension"""
        suffix = file_path.suffix.lower()
        content_types = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.json': 'application/json',
            '.txt': 'text/plain',
            '.log': 'text/plain'
        }
        return content_types.get(suffix, 'application/octet-stream')

class TurnBasedAgent:
    """Main turn-based agent system"""
    
    def __init__(self, 
                 session_id: Optional[str] = None,
                 mcp_url: str = "http://localhost:8000/mcp",
                 s3_bucket: Optional[str] = None,
                 unreal_host: str = "127.0.0.1",
                 unreal_port: int = 17777):
        self.session_id = session_id or f"session-{int(time.time())}"
        self.mcp_url = mcp_url
        self.unreal_host = unreal_host
        self.unreal_port = unreal_port
        self.current_turn: Optional[TurnState] = None
        
        # S3 integration
        self.s3_manager = S3Manager(s3_bucket) if s3_bucket else None
        
        # File paths
        self.saved_dir = _project_root / "Saved"
        self.saved_dir.mkdir(parents=True, exist_ok=True)
        
        # State storage
        self.turns_history: List[TurnState] = []
        self.agent_instance: Optional[Agent] = None
        self.session_manager: Optional[FileSessionManager] = None
        
        # Threading for non-blocking operations
        self.executor = ThreadPoolExecutor(max_workers=2)
        
    def _send_unreal_command(self, payload: Dict) -> bool:
        """Send command to Unreal Engine"""
        try:
            line = json.dumps(payload, separators=(",", ":")) + "\n"
            data = line.encode("utf-8")
            with socket.create_connection((self.unreal_host, self.unreal_port), timeout=2.0) as sock:
                sock.sendall(data)
            return True
        except Exception as e:
            print(f"Failed to send Unreal command: {e}")
            return False
    
    def _wait_for_file(self, path: Path, start_time: float, timeout: float = 15.0) -> bool:
        """Wait for file to appear with newer timestamp"""
        deadline = start_time + timeout
        while time.time() < deadline:
            try:
                if path.exists() and path.stat().st_mtime > start_time and path.stat().st_size > 0:
                    return True
            except FileNotFoundError:
                pass
            time.sleep(0.1)
        return False
    
    def _capture_screenshot(self, turn_id: str) -> Optional[Path]:
        """Capture screenshot from Unreal Engine"""
        screenshot_path = self.saved_dir / f"turn_{turn_id}_screenshot.png"
        start_time = time.time()
        
        if self._send_unreal_command({
            "cmd": "screenshot", 
            "path": str(screenshot_path), 
            "showUI": False
        }):
            if self._wait_for_file(screenshot_path, start_time):
                return screenshot_path
        return None
    
    def _capture_env_state(self, turn_id: str) -> Optional[Dict]:
        """Capture environment state from Unreal Engine"""
        state_path = self.saved_dir / f"turn_{turn_id}_state.json"
        start_time = time.time()
        
        if self._send_unreal_command({
            "cmd": "state", 
            "path": str(state_path)
        }):
            if self._wait_for_file(state_path, start_time):
                try:
                    return json.loads(state_path.read_text(encoding="utf-8-sig"))
                except Exception as e:
                    print(f"Failed to parse state file: {e}")
        return None
    
    def _setup_agent(self) -> bool:
        """Initialize the Strands agent with MCP tools"""
        try:
            self.streamable_http_mcp_client = MCPClient(lambda: streamablehttp_client(self.mcp_url))
            self.streamable_http_mcp_client.__enter__()
            
            # Get tools from MCP server
            tools = self.streamable_http_mcp_client.list_tools_sync()
            filtered_tools = []
            
            for tool in tools:
                name = getattr(tool, "name", "")
                # Filter out screenshot tool as we handle it manually
                if isinstance(name, str) and name.lower() != "screenshot":
                    filtered_tools.append(tool)
            
            # Create session manager
            self.session_manager = FileSessionManager(session_id=self.session_id)
            
            # System prompt for turn-based gameplay
            system_prompt = (
                "You control a character in a turn-based Unreal Engine environment. "
                "Each turn, you receive the current environment state and a screenshot. "
                "Take one meaningful action per turn. Be thoughtful and strategic. "
                "Always review the environment state before acting. "
                "Keep actions safe and avoid getting stuck. "
                "You are embodying a persona - act according to your character traits."
            )
            
            # Create agent
            self.agent_instance = Agent(
                tools=filtered_tools,
                session_manager=self.session_manager,
                system_prompt=system_prompt
            )
            
            return True
            
        except Exception as e:
            print(f"Failed to setup agent: {e}")
            return False
    
    def start_turn(self, prompt: str, persona_traits: Optional[Dict] = None) -> str:
        """Start a new turn with the given prompt"""
        turn_id = str(uuid.uuid4())[:8]
        
        self.current_turn = TurnState(
            turn_id=turn_id,
            session_id=self.session_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            prompt=prompt,
            status="pending"
        )
        
        self.turns_history.append(self.current_turn)
        
        # Start turn processing in background
        self.executor.submit(self._process_turn, persona_traits)
        
        return turn_id
    
    def _process_turn(self, persona_traits: Optional[Dict] = None):
        """Process a turn in the background"""
        if not self.current_turn:
            return
            
        try:
            self.current_turn.status = "running"
            
            # Setup agent if not already done
            if not self.agent_instance and not self._setup_agent():
                raise Exception("Failed to setup agent")
            
            # Capture pre-turn state
            self.current_turn.env_state = self._capture_env_state(self.current_turn.turn_id)
            screenshot_path = self._capture_screenshot(self.current_turn.turn_id)
            self.current_turn.screenshot_path = str(screenshot_path) if screenshot_path else None
            
            # Add persona context if provided
            context_prompt = self.current_turn.prompt
            if persona_traits:
                persona_context = f"You are embodying this persona: {json.dumps(persona_traits)}. "
                context_prompt = persona_context + context_prompt
            
            # Add environment context
            if self.current_turn.env_state:
                pos = self.current_turn.env_state.get("pos", [0, 0, 0])
                context_prompt += f"\nCurrent position: ({pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f})"
            
            # Run agent
            response = self.agent_instance(context_prompt)
            self.current_turn.agent_response = str(response)
            
            # Upload to S3 if configured
            if self.s3_manager:
                s3_prefix = f"strands-turns/{self.session_id}/{self.current_turn.turn_id}"
                
                # Upload screenshot
                if screenshot_path and screenshot_path.exists():
                    screenshot_url = self.s3_manager.upload_file(
                        screenshot_path, 
                        f"{s3_prefix}/screenshot.png"
                    )
                    if screenshot_url:
                        self.current_turn.s3_urls["screenshot"] = screenshot_url
                
                # Upload state
                if self.current_turn.env_state:
                    state_url = self.s3_manager.upload_json(
                        self.current_turn.env_state,
                        f"{s3_prefix}/env_state.json"
                    )
                    if state_url:
                        self.current_turn.s3_urls["env_state"] = state_url
                
                # Upload turn data
                turn_data_url = self.s3_manager.upload_json(
                    asdict(self.current_turn),
                    f"{s3_prefix}/turn_data.json"
                )
                if turn_data_url:
                    self.current_turn.s3_urls["turn_data"] = turn_data_url
            
            self.current_turn.status = "completed"
            
        except Exception as e:
            self.current_turn.status = "error"
            self.current_turn.error_message = str(e)
            print(f"Turn processing error: {e}")
    
    def get_turn_status(self, turn_id: str) -> Optional[Dict]:
        """Get the status of a specific turn"""
        for turn in self.turns_history:
            if turn.turn_id == turn_id:
                return asdict(turn)
        return None
    
    def get_current_turn_status(self) -> Optional[Dict]:
        """Get the status of the current turn"""
        if self.current_turn:
            return asdict(self.current_turn)
        return None
    
    def get_session_history(self) -> List[Dict]:
        """Get all turns in the current session"""
        return [asdict(turn) for turn in self.turns_history]
    
    def cleanup(self):
        """Cleanup resources"""
        if hasattr(self, 'streamable_http_mcp_client'):
            try:
                self.streamable_http_mcp_client.__exit__(None, None, None)
            except:
                pass
        self.executor.shutdown(wait=False)

# CLI interface for testing
def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Turn-based Strands Agent System")
    parser.add_argument("--prompt", required=True, help="Prompt for the agent")
    parser.add_argument("--session-id", help="Session ID for persistence")
    parser.add_argument("--mcp-url", default="http://localhost:8000/mcp", help="MCP server URL")
    parser.add_argument("--s3-bucket", help="S3 bucket for storing outputs")
    parser.add_argument("--persona", help="JSON string with persona traits")
    parser.add_argument("--wait", action="store_true", help="Wait for turn to complete")
    
    args = parser.parse_args()
    
    # Parse persona traits if provided
    persona_traits = None
    if args.persona:
        try:
            persona_traits = json.loads(args.persona)
        except Exception as e:
            print(f"Failed to parse persona: {e}")
            sys.exit(1)
    
    # Create agent system
    agent_system = TurnBasedAgent(
        session_id=args.session_id,
        mcp_url=args.mcp_url,
        s3_bucket=args.s3_bucket
    )
    
    try:
        # Start turn
        turn_id = agent_system.start_turn(args.prompt, persona_traits)
        print(f"Started turn: {turn_id}")
        
        if args.wait:
            # Wait for completion
            while True:
                status = agent_system.get_current_turn_status()
                if status and status["status"] in ["completed", "error"]:
                    print(json.dumps(status, indent=2))
                    break
                time.sleep(1)
        else:
            # Just return the turn ID
            print(json.dumps({"turn_id": turn_id, "status": "started"}))
            
    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        agent_system.cleanup()

if __name__ == "__main__":
    main()