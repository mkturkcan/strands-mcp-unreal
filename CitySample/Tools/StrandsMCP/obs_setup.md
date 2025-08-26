# OBS Setup for AI Consciousness Streaming

## Overview
This system streams AI persona thoughts and actions to OBS, creating a live view into the simulated consciousness of AI agents in Unreal Engine.

## File Locations
All OBS text source files are created in:
```
C:\Users\Administrator\Documents\Unreal Projects\CitySample\Saved\OBS\
```

## OBS Text Sources to Configure

### 1. **Persona Thoughts** (Inner Monologue)
- **File**: `persona_thoughts.txt`
- **Purpose**: Shows the current AI's inner thoughts and emotional state
- **Format**: Timestamped thoughts with personality indicators
- **Update Rate**: Real-time as thoughts are generated
- **OBS Settings**:
  - Add Text (GDI+) source
  - Check "Read from file"
  - Point to: `CitySample\Saved\OBS\persona_thoughts.txt`
  - Font: Consolas or other monospace, size 16-20
  - Color: Light blue or white with slight transparency
  - Position: Bottom left corner of stream

### 2. **Consciousness Dashboard** (System Status)
- **File**: `consciousness_dashboard.txt`
- **Purpose**: Shows which AI persona is active and system status
- **Format**: ASCII-art dashboard with current persona info
- **Update Rate**: On persona switches and major events
- **OBS Settings**:
  - Add Text (GDI+) source
  - Check "Read from file"
  - Point to: `CitySample\Saved\OBS\consciousness_dashboard.txt`
  - Font: Consolas or Courier New, size 14-16
  - Color: Green or cyan
  - Position: Top right corner

### 3. **Activity Log** (Historical Actions)
- **File**: `activity_log.txt`
- **Purpose**: Rolling log of all persona activities
- **Format**: Timestamped entries of major actions
- **Update Rate**: After each significant event
- **OBS Settings**:
  - Add Text (GDI+) source
  - Check "Read from file"
  - Point to: `CitySample\Saved\OBS\activity_log.txt`
  - Font: Small monospace, size 12-14
  - Color: Semi-transparent white
  - Position: Right side panel
  - Consider using scroll filter to show last N lines

## Recommended OBS Scene Layout

```
┌─────────────────────────────────────────────────┐
│  [Dashboard]                    [Activity Log]   │
│  ┌─────────────┐               ┌──────────────┐ │
│  │ CONSCIOUSNESS│               │ 14:23 Explor │ │
│  │ Persona: Bob │               │ 14:24 Jump 3x│ │
│  │ Cycle: #5    │               │ 14:25 Wave.. │ │
│  └─────────────┘               └──────────────┘ │
│                                                  │
│         [Unreal Engine Game Capture]            │
│                                                  │
│                                                  │
│                                                  │
│ ┌──────────────────────────────────────────┐    │
│ │ 💭 Bob thinks: "Wow, this view is amazing!"│   │
│ │ 💭 Bob thinks: "I should explore that area"│   │
│ └──────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

## Stream Filters & Effects

### For Persona Thoughts:
- **Fade In/Out**: Add fade transition for thought updates
- **Outline**: Add subtle outline for readability over game footage
- **Chat Log Mode**: Consider using Chat Log Mode filter to auto-scroll

### For Dashboard:
- **Color Key**: Make background transparent if desired
- **Glow**: Add subtle glow effect for "tech" look

## Advanced Setup

### Browser Source Alternative
Instead of Text (GDI+), you can create an HTML overlay:

1. Create `overlay.html` that reads the text files via JavaScript
2. Add custom CSS for better styling and animations
3. Use Browser Source in OBS pointing to local HTML file

### Example HTML Template:
```html
<!DOCTYPE html>
<html>
<head>
<style>
  body { 
    font-family: 'Consolas', monospace;
    background: transparent;
  }
  
  #thoughts {
    position: absolute;
    bottom: 20px;
    left: 20px;
    background: rgba(0,0,0,0.7);
    color: #00ffff;
    padding: 15px;
    border-radius: 10px;
    border: 2px solid #00ffff;
    max-width: 600px;
    animation: pulse 2s infinite;
  }
  
  @keyframes pulse {
    0% { box-shadow: 0 0 5px #00ffff; }
    50% { box-shadow: 0 0 20px #00ffff; }
    100% { box-shadow: 0 0 5px #00ffff; }
  }
</style>
</head>
<body>
  <div id="thoughts"></div>
  <script>
    // Auto-reload thoughts from file
    setInterval(() => {
      fetch('file:///C:/Users/Administrator/Documents/Unreal%20Projects/CitySample/Saved/OBS/persona_thoughts.txt')
        .then(r => r.text())
        .then(text => {
          document.getElementById('thoughts').innerText = text.split('\n').slice(-3).join('\n');
        });
    }, 1000);
  </script>
</body>
</html>
```

## Running the System

1. **Start MCP Server** (if not already running):
   ```bash
   python CitySample\Tools\StrandsMCP\server.py
   ```

2. **Run Single Persona**:
   ```bash
   python CitySample\Tools\StrandsMCP\persona_agent.py --persona "Explorer" --duration 300
   ```

3. **Run Continuous Consciousness Loop**:
   ```bash
   python CitySample\Tools\StrandsMCP\continuous_consciousness.py --cycle-duration 300
   ```

## Customizing Personas

Edit `default_personas.json` to create custom AI personalities:

```json
{
  "name": "CustomPersona",
  "traits": {
    "archetype": "your_type",
    "base_emotion": "starting_emotion",
    "personality": "Description of personality",
    "goals": ["goal1", "goal2", "goal3"],
    "behaviors": ["behavior1", "behavior2"]
  }
}
```

## Tips for Streaming

1. **Narrative Arc**: Design personas with conflicting goals for interesting emergent stories
2. **Emotional Variety**: Mix different emotional base states for variety
3. **Memory Persistence**: Use S3 to maintain long-term memories across sessions
4. **Viewer Interaction**: Consider adding Twitch/YouTube chat integration to influence persona decisions
5. **Time of Day**: Adjust persona behavior based on in-game time for realism

## Troubleshooting

- **Text not updating**: Ensure file paths are correct and OBS has read permissions
- **Thoughts too fast**: Adjust thought generation frequency in persona_agent.py
- **Memory issues**: Clear old state files periodically from PersonaStates folder
- **S3 errors**: Check AWS credentials and bucket permissions