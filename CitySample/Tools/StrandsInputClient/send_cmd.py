#!/usr/bin/env python3
import argparse
import json
import socket
import sys
import time
from typing import Any, Dict

def send_json(host: str, port: int, payload: Dict[str, Any]) -> None:
    line = json.dumps(payload, separators=(",", ":")) + "\n"
    data = line.encode("utf-8")
    with socket.create_connection((host, port), timeout=2.0) as sock:
        sock.sendall(data)

def main() -> int:
    p = argparse.ArgumentParser(description="Send JSON commands to StrandsInputServer over TCP.")
    p.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=17777, help="Server port (default: 17777)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_move = sub.add_parser("move", help="Move the character")
    sp_move.add_argument("--forward", type=float, default=0.0, help="Forward/back input (-1..1)")
    sp_move.add_argument("--right", type=float, default=0.0, help="Right/left input (-1..1)")
    sp_move.add_argument("--duration", type=float, default=None, help="Duration seconds")

    sp_look = sub.add_parser("look", help="Look around")
    sp_look.add_argument("--yawRate", type=float, default=0.0, help="Yaw rate deg/sec")
    sp_look.add_argument("--pitchRate", type=float, default=0.0, help="Pitch rate deg/sec")
    sp_look.add_argument("--duration", type=float, default=None, help="Duration seconds")

    sp_jump = sub.add_parser("jump", help="Jump once")

    sp_sprint = sub.add_parser("sprint", help="Toggle sprint")
    sp_sprint.add_argument("--enabled", type=str, choices=["true", "false"], required=True, help="Enable sprint or not")

    sp_screenshot = sub.add_parser("screenshot", help="Save a screenshot")
    sp_screenshot.add_argument("--path", type=str, default=None, help="Output path (default: Saved/AutoScreenshot.png)")
    sp_screenshot.add_argument("--showUI", action="store_true", help="Include editor UI in screenshot")

    sp_state = sub.add_parser("state", help="Write a world/agent state JSON snapshot to disk")
    sp_state.add_argument("--path", type=str, default=None, help="Output path (default: Saved/WorldState/agent_state.json)")

    args = p.parse_args()

    try:
        if args.cmd == "move":
            payload = {"cmd": "move", "forward": args.forward, "right": args.right}
            if args.duration is not None:
                payload["duration"] = args.duration
            send_json(args.host, args.port, payload)
        elif args.cmd == "look":
            payload = {"cmd": "look", "yawRate": args.yawRate, "pitchRate": args.pitchRate}
            if args.duration is not None:
                payload["duration"] = args.duration
            send_json(args.host, args.port, payload)
        elif args.cmd == "jump":
            send_json(args.host, args.port, {"cmd": "jump"})
        elif args.cmd == "sprint":
            enabled = args.enabled.lower() == "true"
            send_json(args.host, args.port, {"cmd": "sprint", "enabled": enabled})
        elif args.cmd == "screenshot":
            payload = {"cmd": "screenshot"}
            if getattr(args, "path", None):
                payload["path"] = args.path
            if getattr(args, "showUI", False):
                payload["showUI"] = True
            send_json(args.host, args.port, payload)
        elif args.cmd == "state":
            payload = {"cmd": "state"}
            if getattr(args, "path", None):
                payload["path"] = args.path
            send_json(args.host, args.port, payload)
        else:
            p.print_help()
            return 2
        return 0
    except (ConnectionRefusedError, socket.timeout) as e:
        sys.stderr.write(f"Error: could not connect to {args.host}:{args.port} ({e})\n")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
