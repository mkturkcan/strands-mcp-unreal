#!/usr/bin/env python3
"""
Continuous Consciousness System
Runs multiple persona agents in an endless loop, simulating ongoing AI lives in Unreal Engine
"""

import os
import sys
import json
import time
import random
import subprocess
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = Path(__file__).resolve().parent
PERSONA_SCRIPT = TOOLS_DIR / "persona_agent.py"

class ConsciousnessManager:
    """Manages multiple AI personas living continuously in the game world"""
    
    def __init__(self, personas_config: List[Dict[str, Any]], cycle_duration: int = 300):
        self.personas = personas_config
        self.cycle_duration = cycle_duration
        self.running = True
        self.current_persona_index = 0
        self.cycle_count = 0
        
        # Create OBS dashboard file
        self.dashboard_dir = PROJECT_ROOT / "Saved" / "OBS"
        self.dashboard_dir.mkdir(parents=True, exist_ok=True)
        self.dashboard_file = self.dashboard_dir / "consciousness_dashboard.txt"
        
        # Activity log
        self.activity_log = self.dashboard_dir / "activity_log.txt"
        
    def update_dashboard(self, message: str):
        """Update the OBS dashboard with current status"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dashboard_content = f"""
╔══════════════════════════════════════════════════════════════╗
║                 UNREAL AI CONSCIOUSNESS SYSTEM                ║
╠══════════════════════════════════════════════════════════════╣
║ Status: ACTIVE                                                ║
║ Cycle: #{self.cycle_count}                                   ║
║ Time: {timestamp}                                            ║
╠══════════════════════════════════════════════════════════════╣
║ Current Persona: {message}                                   ║
║ Total Personas: {len(self.personas)}                         ║
║ Cycle Duration: {self.cycle_duration}s                       ║
╚══════════════════════════════════════════════════════════════╝
"""
        self.dashboard_file.write_text(dashboard_content, encoding='utf-8')
        
        # Log activity
        with open(self.activity_log, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {message}\n")
    
    def run_persona(self, persona_config: Dict[str, Any]) -> bool:
        """Run a single persona for one cycle"""
        name = persona_config['name']
        traits = persona_config['traits']
        
        self.update_dashboard(f"{name} is awakening...")
        
        # Build command
        cmd = [
            sys.executable,
            str(PERSONA_SCRIPT),
            "--persona", name,
            "--traits", json.dumps(traits),
            "--duration", str(self.cycle_duration),
            "--use-s3"
        ]
        
        # Check for existing state to load
        state_dir = PROJECT_ROOT / "Saved" / "PersonaStates" / name
        if state_dir.exists():
            state_files = sorted(state_dir.glob("state_*.json"), reverse=True)
            if state_files:
                cmd.extend(["--load-state", str(state_files[0])])
                self.update_dashboard(f"{name} is loading memories...")
        
        # Run the persona
        try:
            self.update_dashboard(f"{name} is exploring the world...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.cycle_duration + 30)
            
            if result.returncode == 0:
                self.update_dashboard(f"{name} completed their cycle successfully")
                return True
            else:
                self.update_dashboard(f"{name} encountered issues: {result.stderr[:100]}")
                return False
                
        except subprocess.TimeoutExpired:
            self.update_dashboard(f"{name}'s cycle timed out - moving to next persona")
            return False
        except Exception as e:
            self.update_dashboard(f"{name} error: {str(e)[:100]}")
            return False
    
    def run_continuous_loop(self):
        """Run personas in an endless loop"""
        print("Starting Continuous Consciousness System...")
        print(f"Managing {len(self.personas)} personas")
        print(f"OBS Dashboard: {self.dashboard_file}")
        print(f"Activity Log: {self.activity_log}")
        print("Press Ctrl+C to stop\n")
        
        while self.running:
            try:
                # Get current persona
                persona = self.personas[self.current_persona_index]
                
                # Run the persona
                print(f"\n--- Cycle {self.cycle_count + 1}: {persona['name']} ---")
                success = self.run_persona(persona)
                
                # Add a brief pause between personas
                self.update_dashboard(f"Transitioning to next persona...")
                time.sleep(random.uniform(5, 10))
                
                # Move to next persona
                self.current_persona_index = (self.current_persona_index + 1) % len(self.personas)
                
                # Increment cycle count when we've run all personas
                if self.current_persona_index == 0:
                    self.cycle_count += 1
                    self.update_dashboard(f"Completed full rotation #{self.cycle_count}")
                    
            except KeyboardInterrupt:
                print("\nShutting down Consciousness System...")
                self.running = False
                break
            except Exception as e:
                print(f"Unexpected error: {e}")
                time.sleep(5)  # Brief pause before retrying
        
        self.update_dashboard("System shut down gracefully")


def create_default_personas() -> List[Dict[str, Any]]:
    """Create a set of default personas with different personalities"""
    return [
        {
            "name": "Explorer",
            "traits": {
                "archetype": "explorer",
                "base_emotion": "excited",
                "personality": "Adventurous and curious, loves discovering new places",
                "goals": ["explore every corner", "find hidden areas", "map the environment"],
                "behaviors": ["moves quickly", "jumps often", "looks everywhere"]
            }
        },
        {
            "name": "Observer",
            "traits": {
                "archetype": "cautious",
                "base_emotion": "contemplative", 
                "personality": "Thoughtful and careful, studies everything in detail",
                "goals": ["understand the world", "analyze patterns", "document observations"],
                "behaviors": ["moves slowly", "looks carefully", "pauses to think"]
            }
        },
        {
            "name": "Performer",
            "traits": {
                "archetype": "social",
                "base_emotion": "playful",
                "personality": "Energetic and expressive, loves to entertain",
                "goals": ["express creativity", "find audiences", "create memorable moments"],
                "behaviors": ["dances", "waves", "does tricks", "seeks attention"]
            }
        },
        {
            "name": "Guardian",
            "traits": {
                "archetype": "protector",
                "base_emotion": "vigilant",
                "personality": "Protective and responsible, watches over the environment",
                "goals": ["patrol territory", "ensure safety", "maintain order"],
                "behaviors": ["patrols systematically", "checks boundaries", "stands guard"]
            }
        },
        {
            "name": "Dreamer",
            "traits": {
                "archetype": "wanderer",
                "base_emotion": "whimsical",
                "personality": "Imaginative and unpredictable, follows intuition",
                "goals": ["follow inspiration", "experience beauty", "find meaning"],
                "behaviors": ["wanders aimlessly", "stops randomly", "contemplates scenery"]
            }
        }
    ]


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Run Continuous AI Consciousness in Unreal")
    parser.add_argument("--config", help="Path to personas configuration JSON file")
    parser.add_argument("--cycle-duration", type=int, default=300, 
                       help="Duration of each persona cycle in seconds (default: 300)")
    parser.add_argument("--random-order", action="store_true",
                       help="Randomize persona order each rotation")
    
    args = parser.parse_args()
    
    # Load or create personas
    if args.config and Path(args.config).exists():
        with open(args.config, 'r', encoding='utf-8') as f:
            personas = json.load(f)
    else:
        personas = create_default_personas()
        
        # Save default config for reference
        config_file = TOOLS_DIR / "default_personas.json"
        config_file.write_text(json.dumps(personas, indent=2), encoding='utf-8')
        print(f"Created default personas config: {config_file}")
    
    # Randomize order if requested
    if args.random_order:
        random.shuffle(personas)
    
    # Create and run the consciousness manager
    manager = ConsciousnessManager(personas, args.cycle_duration)
    
    try:
        manager.run_continuous_loop()
    except KeyboardInterrupt:
        print("\nConsciousness System terminated by user")
    except Exception as e:
        print(f"Fatal error: {e}")
    finally:
        manager.update_dashboard("System offline")


if __name__ == "__main__":
    main()