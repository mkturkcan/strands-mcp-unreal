#!/usr/bin/env python3
from typing import Optional, Dict, Any
import json
import socket
import time
from pathlib import Path

from mcp.server import FastMCP

# Defaults for the Unreal StrandsInputServer plugin
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 17777

# Project root (Tools/StrandsMCP -> MyProject)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE_PATH = PROJECT_ROOT / "Saved" / "WorldState" / "agent_state.json"

def send_json(host: str, port: int, payload: Dict[str, Any]) -> None:
    line = json.dumps(payload, separators=(",", ":")) + "\n"
    data = line.encode("utf-8")
    with socket.create_connection((host, port), timeout=2.0) as sock:
        sock.sendall(data)

def safe_send(host: str, port: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        send_json(host, port, payload)
        return {"status": "ok"}
    except (ConnectionRefusedError, socket.timeout, OSError) as e:
        return {
            "status": "error",
            "error": f"{type(e).__name__}: {e}",
            "host": host,
            "port": port,
            "payload": payload,
        }

def _wait_for_file(p: Path, start_ts: float, timeout_s: float = 10.0, poll_ms: int = 100) -> bool:
    """Wait for file to appear and have mtime newer than start_ts."""
    deadline = start_ts + timeout_s
    while time.time() < deadline:
        try:
            if p.exists() and p.stat().st_mtime > start_ts and p.stat().st_size > 0:
                return True
        except FileNotFoundError:
            pass
        time.sleep(poll_ms / 1000.0)
    return False

# Create an MCP server
mcp = FastMCP("Strands Input MCP Server", json_response=True, host="0.0.0.0")

# Define tools mirroring Tools/StrandsInputClient/send_cmd.py

@mcp.tool(description="Move the character. forward/right in [-1..1]. Optional duration seconds and agent id.")
def move(
    forward: float = 0.0,
    right: float = 0.0,
    duration: Optional[float] = None,
    agent_id: Optional[str] = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"cmd": "move", "forward": forward, "right": right}
    if duration is not None:
        payload["duration"] = duration
    if agent_id is not None:
        payload["id"] = agent_id
    return safe_send(host, port, payload)

@mcp.tool(description="Look around. yawRate/pitchRate in deg/sec. Optional duration seconds and agent id.")
def look(
    yawRate: float = 0.0,
    pitchRate: float = 0.0,
    duration: Optional[float] = None,
    agent_id: Optional[str] = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"cmd": "look", "yawRate": yawRate, "pitchRate": pitchRate}
    if duration is not None:
        payload["duration"] = duration
    if agent_id is not None:
        payload["id"] = agent_id
    return safe_send(host, port, payload)

@mcp.tool(description="Jump once. Optional agent id.")
def jump(
    agent_id: Optional[str] = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"cmd": "jump"}
    if agent_id is not None:
        payload["id"] = agent_id
    return safe_send(host, port, payload)

@mcp.tool(description="Toggle sprint. Optional agent id.")
def sprint(
    enabled: bool,
    agent_id: Optional[str] = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"cmd": "sprint", "enabled": bool(enabled)}
    if agent_id is not None:
        payload["id"] = agent_id
    return safe_send(host, port, payload)

@mcp.tool(description="Request Unreal to save a screenshot to disk. Optional path, showUI, and agent id.")
def screenshot(
    path: Optional[str] = None,
    showUI: bool = False,
    agent_id: Optional[str] = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"cmd": "screenshot", "showUI": bool(showUI)}
    if path:
        payload["path"] = path
    if agent_id is not None:
        payload["id"] = agent_id
    return safe_send(host, port, payload)

@mcp.tool(description="Capture a compact world/agent state snapshot to JSON and return it. Optional agent id.")
def sense(
    path: Optional[str] = None,
    agent_id: Optional[str] = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> Dict[str, Any]:
    # Resolve output path
    out_path = Path(path) if path else DEFAULT_STATE_PATH
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    # Trigger state export in Unreal and wait for file
    t = time.time()
    payload: Dict[str, Any] = {"cmd": "state", "path": str(out_path)}
    if agent_id is not None:
        payload["id"] = agent_id

    res = safe_send(host, port, payload)
    if res.get("status") != "ok":
        return {"status": "error", "error": "send_failed", "detail": res}

    if not _wait_for_file(out_path, t, timeout_s=10.0):
        return {"status": "error", "error": "timeout_waiting_for_state", "path": str(out_path)}

    try:
        data = json.loads(out_path.read_text(encoding="utf-8"))
        return {"status": "ok", "path": str(out_path), "state": data}
    except Exception as e:
        return {"status": "error", "error": f"read_error: {type(e).__name__}: {e}", "path": str(out_path)}

# Run the server with SSE transport (defaults to http://localhost:8000/mcp)
if __name__ == "__main__":
    # The server will listen for clients using Streamable HTTP (SSE)
    mcp.run(transport="streamable-http")
