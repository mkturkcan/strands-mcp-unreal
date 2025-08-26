#!/usr/bin/env python3
"""
Strands Agent Orchestrator (Option A):
- Long-polls an SQS FIFO queue for 'invoke-agent' messages
- Spawns the local Strands Agent (agent_test.py) with the provided prompt/session
- Captures logs and writes a JSON summary file
- Optionally uploads results to S3
- Deletes the SQS message on success; leaves for retry/ DLQ on failure

Configuration (env or .env in the same folder):
  AWS_REGION=us-west-2
  SQS_QUEUE_URL=https://sqs.us-west-2.amazonaws.com/123456789012/strands-agent.fifo
  S3_RESULTS_BUCKET=strands-agent-results-123456789012-us-west-2   (optional)
  MCP_URL=http://localhost:8000/mcp
  CONCURRENCY=1
  SQS_WAIT_TIME=20
  SQS_VISIBILITY_EXTENSION_SEC=30
  POLL_SLEEP=1.0
"""

import os
import sys
import json
import time
import signal
import threading
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

# Project root (Tools/StrandsMCP -> MyProject)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = Path(__file__).resolve().parent

def _load_dotenv():
    """Minimal .env loader (no external dependency)."""
    env_path = TOOLS_DIR / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k, v)
    except Exception:
        pass

_load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "us-west-2")
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL", "").strip()
S3_RESULTS_BUCKET = os.getenv("S3_RESULTS_BUCKET", "").strip() or None
MCP_URL = os.getenv("MCP_URL", "http://localhost:8000/mcp")
CONCURRENCY = max(1, int(os.getenv("CONCURRENCY", "1")))
SQS_WAIT_TIME = max(0, min(20, int(os.getenv("SQS_WAIT_TIME", "20"))))  # long poll
SQS_VISIBILITY_EXTENSION_SEC = max(10, int(os.getenv("SQS_VISIBILITY_EXTENSION_SEC", "30")))
POLL_SLEEP = float(os.getenv("POLL_SLEEP", "1.0"))

# Where to store local logs and results
LOG_DIR = (PROJECT_ROOT / "Saved" / "Logs" / "Agent").resolve()
RESULT_DIR = (PROJECT_ROOT / "Saved" / "AgentResults").resolve()
for p in (LOG_DIR, RESULT_DIR):
    p.mkdir(parents=True, exist_ok=True)

AGENT_SCRIPT = (TOOLS_DIR / "agent_test.py").resolve()

try:
    import boto3  # type: ignore
except Exception as e:
    boto3 = None

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _ensure_boto3():
    if boto3 is None:
        raise RuntimeError("boto3 is required. Please install it in the environment running orchestrator.py")

def _sqs_client():
    _ensure_boto3()
    return boto3.client("sqs", region_name=AWS_REGION)

def _s3_client():
    _ensure_boto3()
    return boto3.client("s3", region_name=AWS_REGION)

def _safe_json_loads(s: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(s)
    except Exception:
        return None

def _upload_file_s3(bucket: str, key: str, path: Path) -> Optional[str]:
    try:
        if not path.exists() or not path.is_file():
            return None
        s3 = _s3_client()
        s3.upload_file(str(path), bucket, key)
        return f"s3://{bucket}/{key}"
    except Exception as e:
        print(f"[WARN] Failed to upload {path} to s3://{bucket}/{key}: {e}", flush=True)
        return None

def _extend_visibility_loop(stop_event: threading.Event, sqs, receipt_handle: str):
    """Periodically extend SQS visibility timeout while the agent is running."""
    try:
        while not stop_event.wait(timeout=SQS_VISIBILITY_EXTENSION_SEC / 2):
            try:
                sqs.change_message_visibility(
                    QueueUrl=SQS_QUEUE_URL,
                    ReceiptHandle=receipt_handle,
                    VisibilityTimeout=SQS_VISIBILITY_EXTENSION_SEC,
                )
                # print("[DEBUG] Extended message visibility", flush=True)
            except Exception as e:
                print(f"[WARN] change_message_visibility failed: {e}", flush=True)
    except Exception:
        pass

def _run_agent_subprocess(prompt: str, session_id: Optional[str], request_id: str, mcp_url: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run agent_test.py with arguments, capture logs, and ensure a result json is written."""
    log_path = LOG_DIR / f"{request_id}.log"
    result_json_path = RESULT_DIR / f"{request_id}.json"

    args = [
        sys.executable,
        str(AGENT_SCRIPT),
        "--prompt", prompt,
        "--mcp-url", mcp_url,
        "--result-json", str(result_json_path),
    ]
    if session_id:
        args.extend(["--session-id", session_id])

    # Map options booleans to CLI flags
    if isinstance(options, dict):
        if options.get("includePreScreenshot") is False:
            args.append("--no-pre-shot")
        if options.get("includePostScreenshot") is False:
            args.append("--no-post-shot")
        if options.get("includePreSense") is False:
            args.append("--no-pre-sense")

    # Run agent; capture stdout & stderr to the same log file
    print(f"[INFO] Spawning agent: {' '.join(args)}", flush=True)
    with log_path.open("wb") as logf:
        proc = subprocess.Popen(args, stdout=logf, stderr=subprocess.STDOUT)
        ret = proc.wait()

    # Try to load result json
    summary: Dict[str, Any] = {
        "status": "error" if ret != 0 else "ok",
        "requestId": request_id,
        "sessionId": session_id or "",
        "prompt": prompt,
        "mcpUrl": mcp_url,
        "exitCode": ret,
        "logPath": str(log_path),
        "resultJsonPath": str(result_json_path),
    }
    try:
        if result_json_path.exists():
            data = json.loads(result_json_path.read_text(encoding="utf-8"))
            summary.update(data if isinstance(data, dict) else {})
    except Exception as e:
        summary["parseError"] = f"{type(e).__name__}: {e}"

    return summary

def _process_message(sqs, msg: Dict[str, Any]) -> bool:
    """Return True on success (message should be deleted)."""
    body = _safe_json_loads(msg.get("Body", ""))
    if not body:
        print("[WARN] Invalid JSON body; skipping.", flush=True)
        return True  # discard

    if body.get("type") != "invoke-agent":
        print(f"[INFO] Unsupported message type: {body.get('type')}; skipping.", flush=True)
        return True  # discard

    prompt = str(body.get("prompt") or "").strip()
    if not prompt:
        print("[WARN] Missing 'prompt'; skipping.", flush=True)
        return True  # discard

    request_id = str(body.get("requestId") or f"req-{int(time.time())}")
    session_id = body.get("sessionId")
    result_bucket = body.get("resultBucket") or S3_RESULTS_BUCKET
    result_prefix = body.get("resultKeyPrefix") or "results/"
    options = body.get("options") if isinstance(body.get("options"), dict) else None

    print(f"[INFO] Processing requestId={request_id} prompt={prompt!r}", flush=True)

    # Start a visibility extension thread while we run the agent
    stop_evt = threading.Event()
    vis_thread = threading.Thread(target=_extend_visibility_loop, args=(stop_evt, sqs, msg["ReceiptHandle"]), daemon=True)
    vis_thread.start()

    try:
        summary = _run_agent_subprocess(prompt, session_id, request_id, MCP_URL, options=options)
        ok = summary.get("status") == "ok"
        # Upload artifacts if requested
        s3_locations: Dict[str, str] = {}
        if result_bucket:
            # upload result JSON
            result_json_path = Path(summary.get("resultJsonPath", ""))
            if result_json_path and result_json_path.exists():
                key = f"{result_prefix}{request_id}.json"
                loc = _upload_file_s3(result_bucket, key, result_json_path)
                if loc:
                    s3_locations["summary"] = loc
            # upload screenshot if present
            shots = summary.get("shots") or {}
            shot_path = shots.get("path")
            if shot_path:
                sp = Path(shot_path)
                if sp.exists() and sp.is_file():
                    key = f"{result_prefix}{request_id}/AutoScreenshot.png"
                    loc = _upload_file_s3(result_bucket, key, sp)
                    if loc:
                        s3_locations["screenshot"] = loc

        if s3_locations:
            print(f"[INFO] Uploaded artifacts: {s3_locations}", flush=True)

        return ok
    finally:
        # Stop visibility extension
        stop_evt.set()
        try:
            vis_thread.join(timeout=2.0)
        except Exception:
            pass

def _worker_loop(worker_id: int, stop_event: threading.Event):
    print(f"[INFO] Worker {worker_id} starting. Queue={SQS_QUEUE_URL}", flush=True)
    if not SQS_QUEUE_URL:
        print("[ERROR] SQS_QUEUE_URL is not set. Exiting.", flush=True)
        return
    if boto3 is None:
        print("[ERROR] boto3 is not installed. Exiting.", flush=True)
        return

    sqs = _sqs_client()

    while not stop_event.is_set():
        try:
            resp = sqs.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=SQS_WAIT_TIME,
                VisibilityTimeout=SQS_VISIBILITY_EXTENSION_SEC,  # initial visibility window
            )
        except Exception as e:
            print(f"[WARN] receive_message failed: {e}", flush=True)
            time.sleep(POLL_SLEEP)
            continue

        msgs = resp.get("Messages", [])
        if not msgs:
            # idle
            continue

        for m in msgs:
            receipt = m["ReceiptHandle"]
            try:
                success = _process_message(sqs, m)
                if success:
                    try:
                        sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt)
                        print("[INFO] Deleted message (success).", flush=True)
                    except Exception as e:
                        print(f"[WARN] delete_message failed: {e}", flush=True)
                else:
                    # Let it retry naturally; do not delete
                    print("[INFO] Agent reported failure; leaving message for retry.", flush=True)
            except Exception as e:
                print(f"[ERROR] Unhandled error processing message: {e}", flush=True)
            finally:
                # small backoff between messages
                time.sleep(POLL_SLEEP)

def main():
    stop_event = threading.Event()

    def _handle_sigint(signum, frame):
        print("[INFO] Received interrupt, shutting down...", flush=True)
        stop_event.set()

    try:
        signal.signal(signal.SIGINT, _handle_sigint)
        signal.signal(signal.SIGTERM, _handle_sigint)
    except Exception:
        pass

    workers = []
    for i in range(CONCURRENCY):
        t = threading.Thread(target=_worker_loop, args=(i, stop_event), daemon=True)
        workers.append(t)
        t.start()

    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    finally:
        stop_event.set()
        for t in workers:
            try:
                t.join(timeout=3.0)
            except Exception:
                pass
        print("[INFO] Orchestrator stopped.", flush=True)

if __name__ == "__main__":
    main()
