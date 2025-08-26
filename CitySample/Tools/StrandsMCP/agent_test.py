#!/usr/bin/env python3
import os
from pathlib import Path

# Add likely native DLL locations to the DLL search path to resolve strands.cp311-win_amd64.pyd dependencies.
def _add_dll_dir(p: Path):
    try:
        if p and p.is_dir():
            os.add_dll_directory(str(p))
    except Exception:
        pass

# UE project's venv site-packages
# agent_test.py -> StrandsMCP -> Tools -> MyProject (parents[2])
_project_root = Path(__file__).resolve().parents[2]
_site = _project_root / "Intermediate" / "PipInstall" / "Lib" / "site-packages"

# Ensure Python can import packages installed by UE's PipInstall
import sys
if str(_site) not in sys.path:
    sys.path.insert(0, str(_site))

# Common native lib locations used by numpy/opencv-backed extensions
for sub in ["numpy/.libs", "numpy/core", "cv2", ""]:
    _add_dll_dir((_site / sub) if sub else _site)

from mcp.client.streamable_http import streamablehttp_client
from strands.agent import Agent
from strands.tools.mcp.mcp_client import MCPClient
from strands.session.file_session_manager import FileSessionManager
from strands.hooks import BeforeInvocationEvent, AfterInvocationEvent, HookProvider

import json
import socket
import time
from typing import Optional
import base64
try:
    import boto3  # type: ignore
except Exception:
    boto3 = None

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 17777

def _send_unreal_cmd(payload: dict, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> bool:
    """Fire-and-forget TCP JSON line to the Unreal StrandsInputServer."""
    try:
        line = json.dumps(payload, separators=(",", ":")) + "\n"
        data = line.encode("utf-8")
        with socket.create_connection((host, port), timeout=2.0) as sock:
            sock.sendall(data)
        return True
    except Exception:
        return False

def _wait_for_file(p: Path, start_ts: float, timeout_s: float = 15.0, poll_ms: int = 100) -> bool:
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

def _summarize_image_bedrock(
    img_bytes: bytes,
    *,
    region: str = "us-west-2",
    model_id: Optional[str] = None,
    inference_profile_arn: Optional[str] = None,
    max_tokens: int = 256,
    prompt: Optional[str] = None,
) -> Optional[str]:
    """Call Bedrock Claude Sonnet to summarize an image into text. Returns None on failure."""
    if boto3 is None:
        return None
    try:
        client = boto3.client("bedrock-runtime", region_name=region)
        # Default prompt if not provided
        prompt_text = prompt or "Summarize the scene in one or two concise sentences. Mention key objects and relative positions."

        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": prompt_text},
                            {
                                "type": "input_image",
                                "image": {
                                    "format": "png",
                                    "source": {"bytes": base64.b64encode(img_bytes).decode("utf-8")},
                                },
                            },
                        ],
                    }
                ],
            }
        )

        # Prefer inference profile ARN if provided; else fallback to modelId
        if inference_profile_arn:
            try:
                resp = client.invoke_model(
                    inferenceProfileArn=inference_profile_arn,
                    contentType="application/json",
                    accept="application/json",
                    body=body,
                )
            except TypeError:
                # SDK may not support inferenceProfileArn param; fallback to modelId path below
                resp = None
        else:
            resp = None

        if resp is None:
            mid = model_id or "anthropic.claude-3-7-sonnet-20250219-v1:0"
            resp = client.invoke_model(
                modelId=mid,
                contentType="application/json",
                accept="application/json",
                body=body,
            )

        payload = resp.get("body").read().decode("utf-8") if hasattr(resp.get("body", None), "read") else resp
        data = json.loads(payload) if isinstance(payload, str) else payload

        # Try common Anthropic Bedrock response shape
        # Some SDKs return {"output":{"message":{"content":[{"type":"output_text","text":"..."}]}}}
        msg = data.get("output", {}).get("message", {})
        content = msg.get("content", []) if isinstance(msg, dict) else []
        for block in content:
            if isinstance(block, dict) and block.get("type") in ("output_text", "text") and block.get("text"):
                return str(block["text"]).strip()

        # Fallback: some responses use "content":[{"text":"..."}] at top-level
        content = data.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("text"):
                    return str(block["text"]).strip()

        return None
    except Exception:
        return None

def _append_image_message_with_optional_summary(
    session_manager: FileSessionManager,
    agent: Agent,
    shot_path: Path,
    *,
    include_summary: bool = True,
    region: str = "us-west-2",
    model_id: Optional[str] = None,
    inference_profile_arn: Optional[str] = "arn:aws:bedrock:us-west-2:609061237212:inference-profile/us.anthropic.claude-sonnet-4-20250514-v1:0",
) -> None:
    """Read image from disk, optionally summarize with Bedrock, and append message (text + image) to session."""
    img_bytes = shot_path.read_bytes()
    blocks = [{"text": f"Scene image captured at {time.ctime()}."}]
    if include_summary:
        summary = _summarize_image_bedrock(
            img_bytes,
            region=region,
            model_id=model_id,
            inference_profile_arn=inference_profile_arn,
            max_tokens=192,
            prompt="Provide a concise, factual description of what is visible in this third-person Unreal scene.",
        )
        if summary:
            blocks.append({"text": f"Scene summary: {summary}"})
    blocks.append({"image": {"format": "png", "source": {"bytes": img_bytes}}})

    message = {"role": "user", "content": blocks}
    session_manager.append_message(message, agent)
    session_manager.sync_agent(agent)

def _append_post_turn_screenshot(session_manager: FileSessionManager, agent: Agent, shot_path: Path) -> None:
    """Capture and append a post-turn screenshot to the session for agent situational awareness."""
    try:
        # brief delay to ensure world has advanced and frame is rendered
        time.sleep(0.5)
        t = time.time()
        _send_unreal_cmd({"cmd": "screenshot", "path": str(shot_path), "showUI": False})
        if _wait_for_file(shot_path, t, timeout_s=8.0):
            try:
                _append_image_message_with_optional_summary(session_manager, agent, shot_path, include_summary=True)
                print("Appended post-turn screenshot to session.")
            except Exception as e:
                print("Post-turn: failed to read/append screenshot:", e)
        else:
            print(f"Post-turn: timed out waiting for screenshot at {shot_path}.")
    except Exception as e:
        print("Post-turn screenshot error:", e)

def _append_pre_turn_screenshot(session_manager: FileSessionManager, agent: Agent, shot_path: Path) -> None:
    """Capture and append a pre-turn screenshot to the session so the model sees it before answering."""
    try:
        # small settle to allow camera to stabilize before capture
        time.sleep(0.3)
        t = time.time()
        _send_unreal_cmd({"cmd": "screenshot", "path": str(shot_path), "showUI": False})
        if _wait_for_file(shot_path, t, timeout_s=8.0):
            try:
                _append_image_message_with_optional_summary(session_manager, agent, shot_path, include_summary=True)
                print("Appended pre-turn screenshot to session.")
            except Exception as e:
                print("Pre-turn: failed to read/append screenshot:", e)
        else:
            print(f"Pre-turn: timed out waiting for screenshot at {shot_path}.")
    except Exception as e:
        print("Pre-turn screenshot error:", e)


def _append_pre_turn_state(session_manager: FileSessionManager, agent: Agent, state_path: Path) -> None:
    """Request and append a compact env state summary before each turn."""
    try:
        t = time.time()
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        _send_unreal_cmd({"cmd": "state", "path": str(state_path)})
        if _wait_for_file(state_path, t, timeout_s=8.0):
            try:
                data = json.loads(state_path.read_text(encoding="utf-8-sig"))
                pos = data.get("pos", [0.0, 0.0, 0.0])
                rot = data.get("rot", {})
                move = data.get("move", {})
                tr = data.get("trace", {})
                fwd = tr.get("forward", {})
                left = tr.get("left", {})
                right = tr.get("right", {})
                down = tr.get("down", {})
                blk = data.get("blocked", {})
                speed = float(data.get("speed", 0.0) or 0.0)

                def _num(v, d=0.0):
                    try:
                        return float(v)
                    except Exception:
                        return d

                line1 = f"Env state: pos=({pos[0]:.1f},{pos[1]:.1f},{pos[2]:.1f}), yaw={_num(rot.get('yaw'),0.0):.1f}, speed={speed:.1f} cm/s"
                line2 = f"mode={move.get('mode','')}, fwdWaist={_num(fwd.get('waist'),0):.0f}cm, left={_num(left.get('waist'),0):.0f}cm, right={_num(right.get('waist'),0):.0f}cm, down={_num(down.get('dist'),0):.0f}cm"
                line3 = f"blockedForward={bool(blk.get('forward', False))}"
                message = {"role": "user", "content": [{"text": line1 + "\n" + line2 + "\n" + line3}]}
                session_manager.append_message(message, agent)
                session_manager.sync_agent(agent)
                print("Appended pre-turn env state to session.")
            except Exception as e:
                print("Pre-turn: failed to read/append env state:", e)
        else:
            print(f"Pre-turn: timed out waiting for env state at {state_path}.")
    except Exception as e:
        print("Pre-turn env state error:", e)

class PreTurnSenseHook(HookProvider):
    def __init__(self, session_manager: FileSessionManager, state_path: Path):
        self.session_manager = session_manager
        self.state_path = state_path

    def register_hooks(self, registry, **kwargs):
        # Capture and append env state before each agent invocation
        registry.add_callback(
            BeforeInvocationEvent,
            lambda event: _append_pre_turn_state(self.session_manager, event.agent, self.state_path),
        )

class PostTurnScreenshotHook(HookProvider):
    def __init__(self, session_manager: FileSessionManager, shot_path: Path):
        self.session_manager = session_manager
        self.shot_path = shot_path

    def register_hooks(self, registry, **kwargs):
        # Append a screenshot at the end of every agent invocation (turn)
        registry.add_callback(
            AfterInvocationEvent,
            lambda event: _append_post_turn_screenshot(self.session_manager, event.agent, self.shot_path),
        )

class PreTurnScreenshotHook(HookProvider):
    def __init__(self, session_manager: FileSessionManager, shot_path: Path):
        self.session_manager = session_manager
        self.shot_path = shot_path

    def register_hooks(self, registry, **kwargs):
        # Capture and append a screenshot before each agent invocation
        registry.add_callback(
            BeforeInvocationEvent,
            lambda event: _append_pre_turn_screenshot(self.session_manager, event.agent, self.shot_path),
        )

def main():
    import argparse
    from datetime import datetime, timezone

    # Parse CLI arguments
    parser = argparse.ArgumentParser(description="Run Strands Agent against local MCP server and Unreal.")
    parser.add_argument("--prompt", required=True, help="User command/prompt for the agent.")
    parser.add_argument("--session-id", default=None, help="Optional session id to reuse for persistence.")
    parser.add_argument("--mcp-url", default=os.environ.get("MCP_URL", "http://localhost:8000/mcp"), help="MCP server URL.")
    parser.add_argument("--no-pre-shot", action="store_true", help="Disable pre-turn screenshot hook.")
    parser.add_argument("--no-post-shot", action="store_true", help="Disable post-turn screenshot hook.")
    parser.add_argument("--no-pre-sense", action="store_true", help="Disable pre-turn environment state hook.")
    parser.add_argument("--result-json", default=None, help="Optional path to write a JSON summary result.")
    args = parser.parse_args()

    include_pre_shot = not args.no_pre_shot
    include_post_shot = not args.no_post_shot
    include_pre_sense = not args.no_pre_sense

    start_ts = datetime.now(timezone.utc)

    # Client configured for Streamable HTTP (SSE) MCP server
    streamable_http_mcp_client = MCPClient(lambda: streamablehttp_client(args.mcp_url))

    success = True
    err_msg = None
    user_command = args.prompt
    session_id = None
    shot_path = None

    # Create an agent with MCP tools
    with streamable_http_mcp_client:
        # Get the tools from the MCP server
        tools = streamable_http_mcp_client.list_tools_sync()
        print("Discovered MCP tools:")
        filtered_tools = []
        for t in tools:
            name = getattr(t, "name", "")
            desc = getattr(t, "description", "")
            # Avoid exposing 'screenshot' tool to the model; we append images via session ourselves.
            if isinstance(name, str) and name.lower() == "screenshot":
                continue
            filtered_tools.append(t)
            print(f"- {name}: {desc}")

        # Create an agent with these tools (as requested), attach a persistent session, and set a system prompt
        # Precompute default screenshot/state paths
        saved_dir = (_project_root / "Saved").resolve()
        try:
            saved_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        shot_path = saved_dir / "AutoScreenshot.png"
        state_path = saved_dir / "WorldState" / "agent_state.json"

        session_id = args.session_id or f"session-{int(time.time())}"
        session_manager = FileSessionManager(session_id=session_id)
        system_prompt = (
            "You control a character in Unreal. Always review the env state and latest scene image "
            "before taking any actions. Keep actions safe and reversible. "
            "Policy: If blockedForward=true or forward waist distance < 100cm, do not move forward. "
            "First scan left/right (±20–45°) to find a clear path, then probe with a short move (≤0.25s). "
            "Resense after each action. If speed < 10 cm/s after a forward move, treat as stuck and reorient ±45–90°. "
            "Only jump small obstacles (knee<50cm and chest>80cm). Avoid oscillation and spamming actions."
            "Do whatever you want. You are now instantiated."
        )

        hooks = []
        if include_pre_sense:
            hooks.append(PreTurnSenseHook(session_manager, state_path))
        if include_pre_shot:
            hooks.append(PreTurnScreenshotHook(session_manager, shot_path))
        if include_post_shot:
            hooks.append(PostTurnScreenshotHook(session_manager, shot_path))

        agent = Agent(
            tools=filtered_tools,
            session_manager=session_manager,
            system_prompt=system_prompt,
            hooks=hooks,
        )
        print("Agent created with MCP tools, session manager, and configured hooks.")

        # Invoke the agent; hooks may capture and append images/state around this turn
        try:
            agent(f"Be free.")
        except Exception as e:
            success = False
            err_msg = f"{type(e).__name__}: {e}"

    # Emit a compact JSON summary to stdout (and optionally to a file)
    finish_ts = datetime.now(timezone.utc)
    summary = {
        "status": "ok" if success else "error",
        "sessionId": session_id or "",
        "prompt": user_command,
        "mcpUrl": args.mcp_url,
        "startedAt": start_ts.isoformat(),
        "finishedAt": finish_ts.isoformat(),
        "hooks": {
            "preSense": include_pre_sense,
            "preShot": include_pre_shot,
            "postShot": include_post_shot,
        },
        "shots": {
            "path": str(shot_path) if shot_path else None
        },
    }
    if not success and err_msg:
        summary["error"] = err_msg

    try:
        print(json.dumps(summary, separators=(",", ":")))
    except Exception:
        pass

    if args.result_json:
        try:
            p = Path(args.result_json)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        except Exception:
            pass

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
