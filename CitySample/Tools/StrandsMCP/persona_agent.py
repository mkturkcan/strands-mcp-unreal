#!/usr/bin/env python3
"""
Persona-based Strands Agent with Inner Monologue
Simulates consciousness in Unreal Engine with streaming thoughts to OBS
"""

import os
import sys
import json
import time
import socket
import random
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import threading
import queue

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

# Ensure Python can import packages installed by UE's PipInstall
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
    import boto3  # type: ignore
except Exception:
    boto3 = None

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 17777
OBS_OUTPUT_FILE = "persona_thoughts.txt"

class PersonaAgent:
    """An AI agent with personality, inner monologue, and continuous consciousness"""
    
    def __init__(self, persona_name: str, persona_traits: Dict[str, Any], 
                 session_id: Optional[str] = None, use_s3: bool = False):
        self.persona_name = persona_name
        self.persona_traits = persona_traits
        self.session_id = session_id or f"persona-{persona_name.lower()}-{int(time.time())}"
        self.use_s3 = use_s3 and boto3 is not None
        
        # Inner monologue queue for OBS streaming
        self.thought_queue = queue.Queue()
        self.obs_writer_thread = None
        self.running = True
        
        # Memory and state persistence
        self.memories = []
        self.emotional_state = persona_traits.get("base_emotion", "curious")
        self.energy_level = 100.0  # 0-100 energy simulation
        self.goals = persona_traits.get("goals", ["explore", "understand", "survive"])
        
        # OBS output directory
        self.obs_dir = _project_root / "Saved" / "OBS"
        self.obs_dir.mkdir(parents=True, exist_ok=True)
        self.obs_file = self.obs_dir / OBS_OUTPUT_FILE
        
        # Session persistence paths
        self.saved_dir = _project_root / "Saved"
        self.state_dir = self.saved_dir / "PersonaStates" / self.persona_name
        self.state_dir.mkdir(parents=True, exist_ok=True)
        
        # Start OBS writer thread
        self._start_obs_writer()
    
    def _start_obs_writer(self):
        """Start background thread to write thoughts to OBS file"""
        def writer():
            while self.running:
                try:
                    thought = self.thought_queue.get(timeout=0.5)
                    # Write to OBS file with timestamp
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    formatted = f"[{timestamp}] {self.persona_name}: {thought}\n"
                    
                    # Append to file for OBS text source
                    with open(self.obs_file, 'a', encoding='utf-8') as f:
                        f.write(formatted)
                    
                    # Keep only last 20 lines for readability
                    lines = self.obs_file.read_text(encoding='utf-8').splitlines()
                    if len(lines) > 20:
                        self.obs_file.write_text('\n'.join(lines[-20:]) + '\n', encoding='utf-8')
                        
                except queue.Empty:
                    continue
                except Exception as e:
                    print(f"OBS writer error: {e}")
        
        self.obs_writer_thread = threading.Thread(target=writer, daemon=True)
        self.obs_writer_thread.start()
    
    def think(self, thought: str):
        """Generate an inner monologue thought"""
        # Add personality flavor to thoughts
        if self.emotional_state == "excited":
            thought = f"*excitedly* {thought}"
        elif self.emotional_state == "cautious":
            thought = f"*carefully* {thought}"
        elif self.emotional_state == "tired":
            thought = f"*wearily* {thought}"
        
        self.thought_queue.put(thought)
        try:
            print(f"[THOUGHT] {self.persona_name}: {thought}")
        except UnicodeEncodeError:
            print(f"[THOUGHT] {self.persona_name}: {thought.encode('ascii', 'ignore').decode()}")
        return thought
    
    def update_emotion(self, event: str):
        """Update emotional state based on events"""
        emotion_triggers = {
            "blocked": "frustrated",
            "clear_path": "excited",
            "stuck": "anxious",
            "success": "happy",
            "failure": "disappointed",
            "low_energy": "tired",
            "high_energy": "energetic"
        }
        
        for trigger, emotion in emotion_triggers.items():
            if trigger in event.lower():
                self.emotional_state = emotion
                self.think(f"Feeling {emotion} now...")
                break
    
    def decide_action(self) -> str:
        """Decide what to do next based on personality and state"""
        # Energy affects decision making
        if self.energy_level < 20:
            self.think("I'm getting tired... maybe I should rest")
            return "rest"
        
        # Personality-driven decisions
        if "explorer" in self.persona_traits.get("archetype", ""):
            actions = ["explore_forward", "look_around", "investigate", "climb"]
            weights = [0.4, 0.3, 0.2, 0.1]
        elif "cautious" in self.persona_traits.get("archetype", ""):
            actions = ["sense_environment", "look_carefully", "move_slowly", "wait"]
            weights = [0.4, 0.3, 0.2, 0.1]
        elif "social" in self.persona_traits.get("archetype", ""):
            actions = ["wave", "dance", "look_for_others", "communicate"]
            weights = [.3, 0.3, 0.3, 0.1]
        else:
            actions = ["wander", "observe", "interact", "rest"]
            weights = [0.3, 0.3, 0.3, 0.1]
        
        return random.choices(actions, weights=weights)[0]
    
    def generate_persona_prompt(self) -> str:
        """Generate a contextual prompt based on persona and current state"""
        base_prompt = f"""You are {self.persona_name}, with these traits: {json.dumps(self.persona_traits)}.
        
Your current emotional state is '{self.emotional_state}' and energy level is {self.energy_level:.0f}%.
Your goals are: {', '.join(self.goals)}.

Recent memories: {'; '.join(self.memories[-5:]) if self.memories else 'None yet'}

Based on your personality and current state, express your thoughts as you explore.
Before each action, share your inner monologue about what you're thinking and feeling.
Describe what catches your attention and why, based on your personality traits."""
        
        # Add specific behavioral guidance based on energy and emotion
        if self.energy_level < 30:
            base_prompt += "\nYou're feeling tired. Consider resting or moving more slowly."
        
        if self.emotional_state == "excited":
            base_prompt += "\nYou're excited! Be more adventurous in your exploration."
        elif self.emotional_state == "cautious":
            base_prompt += "\nYou're being cautious. Check your surroundings carefully before moving."
        
        return base_prompt
    
    def save_state(self):
        """Save persona state to disk (and optionally S3)"""
        state = {
            "persona_name": self.persona_name,
            "persona_traits": self.persona_traits,
            "session_id": self.session_id,
            "memories": self.memories,
            "emotional_state": self.emotional_state,
            "energy_level": self.energy_level,
            "goals": self.goals,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Save locally
        state_file = self.state_dir / f"state_{int(time.time())}.json"
        state_file.write_text(json.dumps(state, indent=2), encoding='utf-8')
        
        # Save to S3 if enabled
        if self.use_s3:
            try:
                s3 = boto3.client('s3')
                bucket = os.getenv('S3_PERSONA_BUCKET', 'strands-personas')
                key = f"{self.persona_name}/{self.session_id}/state_{int(time.time())}.json"
                s3.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=json.dumps(state),
                    ContentType='application/json'
                )
                self.think(f"Saved my memories to the cloud...")
            except Exception as e:
                print(f"S3 save failed: {e}")
        
        return state
    
    def load_state(self, state_file: Optional[Path] = None):
        """Load previous persona state"""
        if state_file and state_file.exists():
            state = json.loads(state_file.read_text(encoding='utf-8'))
            self.memories = state.get('memories', [])
            self.emotional_state = state.get('emotional_state', 'curious')
            self.energy_level = state.get('energy_level', 100.0)
            self.goals = state.get('goals', self.goals)
            self.think(f"Remembering... {len(self.memories)} previous experiences")
    
    def run_lifecycle(self, agent: Agent, duration_seconds: int = 300):
        """Run the persona's life cycle for a specified duration"""
        start_time = time.time()
        action_count = 0
        
        self.think(f"Awakening... I am {self.persona_name}")
        self.think(f"My purpose: {', '.join(self.goals)}")
        
        while time.time() - start_time < duration_seconds:
            # Decide what to do
            action = self.decide_action()
            self.think(f"I should {action.replace('_', ' ')}")
            
            # Generate contextual prompt
            prompt = self.generate_persona_prompt()
            action_prompt = self._action_to_prompt(action)
            full_prompt = f"{prompt}\n\nNow: {action_prompt}"
            
            # Execute through agent
            try:
                self.think(f"Attempting to {action_prompt}")
                result = agent(full_prompt)
                
                # Process result and update state
                self.memories.append(f"I tried to {action} and {self._interpret_result(result)}")
                self.update_emotion("success")
                
                # Energy depletes with actions
                self.energy_level = max(0, self.energy_level - random.uniform(2, 5))
                
            except Exception as e:
                self.think(f"Something went wrong: {str(e)[:50]}")
                self.memories.append(f"Failed to {action}")
                self.update_emotion("failure")
                self.energy_level = max(0, self.energy_level - 1)
            
            # Rest if tired
            if self.energy_level < 20:
                self.think("I need to rest and recover energy")
                time.sleep(5)
                self.energy_level = min(100, self.energy_level + 20)
                self.think("Feeling refreshed!")
            
            # Save state periodically
            action_count += 1
            if action_count % 5 == 0:
                self.save_state()
            
            # Brief pause between actions
            time.sleep(random.uniform(2, 5))
        
        self.think(f"My exploration session is complete. I learned {len(self.memories)} new things.")
        self.save_state()
    
    def _action_to_prompt(self, action: str) -> str:
        """Convert action decision to natural language prompt"""
        prompts = {
            "explore_forward": "Move forward and explore what's ahead",
            "look_around": "Look around 360 degrees to observe the environment",
            "investigate": "Investigate something interesting nearby",
            "climb": "Try to climb or jump over any obstacles",
            "sense_environment": "Carefully sense the environment for hazards",
            "look_carefully": "Look very carefully at the surroundings",
            "move_slowly": "Move forward slowly and cautiously",
            "wait": "Wait and observe for a moment",
            "wave": "Wave in a friendly manner",
            "dance": "Do a little dance to express yourself",
            "look_for_others": "Look around for other characters or people",
            "communicate": "Try to communicate or make gestures",
            "wander": "Wander around aimlessly",
            "observe": "Stop and observe the details of the scene",
            "interact": "Try to interact with objects nearby",
            "rest": "Rest and recover energy"
        }
        return prompts.get(action, "Explore the environment")
    
    def _interpret_result(self, result: Any) -> str:
        """Interpret agent result for memory"""
        if result is None:
            return "completed the action"
        elif isinstance(result, str):
            return f"observed: {result[:100]}"
        else:
            return "experienced something new"
    
    def cleanup(self):
        """Clean up resources"""
        self.running = False
        if self.obs_writer_thread:
            self.obs_writer_thread.join(timeout=2)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Run a Persona-based Strands Agent")
    parser.add_argument("--persona", default="Explorer", help="Persona name")
    parser.add_argument("--traits", type=json.loads, 
                       default='{"archetype": "explorer", "base_emotion": "curious", "goals": ["explore", "discover", "learn"]}',
                       help="Persona traits as JSON")
    parser.add_argument("--duration", type=int, default=300, help="Lifecycle duration in seconds")
    parser.add_argument("--session-id", help="Session ID for continuity")
    parser.add_argument("--load-state", help="Path to previous state file to load")
    parser.add_argument("--use-s3", action="store_true", help="Use S3 for state persistence")
    parser.add_argument("--mcp-url", default=os.environ.get("MCP_URL", "http://localhost:8000/mcp"))
    
    args = parser.parse_args()
    
    # Create persona
    persona = PersonaAgent(
        persona_name=args.persona,
        persona_traits=args.traits,
        session_id=args.session_id,
        use_s3=args.use_s3
    )
    
    # Load previous state if provided
    if args.load_state:
        persona.load_state(Path(args.load_state))
    
    # Setup MCP client and agent
    try:
        streamable_http_mcp_client = MCPClient(lambda: streamablehttp_client(args.mcp_url))
        
        with streamable_http_mcp_client:
            tools = streamable_http_mcp_client.list_tools_sync()
            filtered_tools = [t for t in tools if getattr(t, "name", "").lower() != "screenshot"]
            
            # Create session manager
            session_manager = FileSessionManager(session_id=persona.session_id)
            
            # Create agent with persona's prompt
            agent = Agent(
                tools=filtered_tools,
                session_manager=session_manager,
system_prompt="You've just been instantiated into this reality. Do whatever you want.",
                hooks=[]
            )
            
            print(f"Starting {persona.persona_name}'s lifecycle for {args.duration} seconds...")
            print(f"OBS output: {persona.obs_file}")
            
            # Run the persona's lifecycle
            persona.run_lifecycle(agent, args.duration)
            
    except Exception as e:
        print(f"Error: {e}")
        persona.think(f"Critical error: {str(e)[:100]}")
    finally:
        persona.cleanup()
        print(f"Persona {persona.persona_name} has completed their journey.")


if __name__ == "__main__":
    main()