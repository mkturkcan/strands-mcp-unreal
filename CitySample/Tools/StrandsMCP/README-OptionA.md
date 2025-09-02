# Strands Agent Invocation via AWS (Option A)

This setup allows you to trigger the local Strands Agent (controlling Unreal) from AWS:
- API Gateway (HTTP) → Lambda Invoker → SQS FIFO queue
- Local Orchestrator (Windows machine) long-polls SQS, runs `agent_test.py` with your prompt.
- Results can be stored locally and optionally uploaded to S3.

Contents:
- agent_test.py (parameterized CLI to run the agent)
- orchestrator.py (SQS long-poller + subprocess runner)
- .env.example (copy to `.env` and fill)
- cloud/lambda_invoker/app.py (Lambda handler)
- cloud/terraform/ (IaC to deploy SQS + DLQ, Lambda, API Gateway)

## Prereqs on the Windows box (local machine with Unreal)
- Unreal running with the StrandsInputServer plugin (listening on TCP 127.0.0.1:17777).
- MCP server running: `python Tools/StrandsMCP/server.py` (HTTP SSE on http://localhost:8000/mcp).
- Each MCP tool now accepts an optional `agent_id` parameter so commands can target specific Unreal agents (e.g. `move(agent_id="agent-1", forward=1.0)`).
- Python environment that can import:
  - `mcp`, `anyio`, `httpx` (already available via UE PipInstall).
  - `strands` (already available via UE PipInstall).
  - `boto3` for orchestrator (install into the Python you intend to run `orchestrator.py` with).
- AWS credentials on the Windows box with permissions:
  - SQS: ReceiveMessage, DeleteMessage, ChangeMessageVisibility on the main queue.
  - S3: PutObject to the results bucket (optional).

Recommended: Create a small venv for the orchestrator and install boto3:
```
py -3 -m venv %USERPROFILE%\strands-orch-venv
%USERPROFILE%\strands-orch-venv\Scripts\python -m pip install --upgrade pip
%USERPROFILE%\strands-orch-venv\Scripts\python -m pip install boto3
```

## Configure the orchestrator
1) Copy `.env.example` to `.env` and fill in:
```
AWS_REGION=us-west-2
SQS_QUEUE_URL=https://sqs.us-west-2.amazonaws.com/123456789012/strands-agent.fifo
S3_RESULTS_BUCKET=your-results-bucket (optional)
MCP_URL=http://localhost:8000/mcp
CONCURRENCY=1
```

2) Start the orchestrator (using the same Python you installed boto3 into):
```
%USERPROFILE%\strands-orch-venv\Scripts\python MyProject\Tools\StrandsMCP\orchestrator.py
```
Logs will be in `MyProject\Saved\Logs\Agent\*.log`. Result JSONs in `MyProject\Saved\AgentResults\*.json`.

## Quick local test (without AWS)
Invoke the agent directly (make sure MCP server and Unreal are running):
```
py MyProject\Tools\StrandsMCP\agent_test.py --prompt "Jump once"
```
It prints a JSON summary to stdout and writes a summary to `--result-json` if you pass that flag.

## End-to-end with AWS
1) Deploy the cloud stack with Terraform:
   - See `cloud/terraform/README.md` for steps.
   - Terraform outputs:
     - `invoke_url`: POST endpoint to queue an invocation
     - `sqs_queue_url`: The SQS FIFO queue URL used by the orchestrator

2) Call the API:
```
curl -X POST "$INVOKE_URL" ^
  -H "Content-Type: application/json" ^
  -d "{\"prompt\":\"Get to the highest point.\",\"requestId\":\"req-1234\"}"
```
Response:
```
{ "status": "queued", "requestId": "req-1234", "sqsMessageId": "...", "groupId": "agent-1" }
```

3) The orchestrator will:
   - Receive the SQS message
   - Launch `agent_test.py --prompt "Get to the highest point." ...`
   - Optionally upload summary and screenshot to S3 (if configured)

## Message schema (SQS body)
```
{
  "type": "invoke-agent",
  "prompt": "Get to the highest point.",
  "sessionId": "optional",
  "options": {
    "includePreScreenshot": true,
    "includePostScreenshot": true,
    "includePreSense": true
  },
  "requestId": "uuid-or-string",
  "resultBucket": "optional-override",
  "resultKeyPrefix": "optional/prefix/"
}
```

## Lambda Invoker request body (API Gateway)
```
{
  "prompt": "Get to the highest point.",
  "requestId": "req-1234",
  "sessionId": "optional",
  "options": { ... },
  "resultBucket": "optional-override",
  "resultKeyPrefix": "optional/prefix/",
  "groupId": "agent-1"
}
```

## Operational tips
- Run the orchestrator as a Scheduled Task with “Run whether user is logged on or not” and “Restart on failure”.
- Use a FIFO queue to guarantee sequential execution for a single Unreal instance.
- Use a DLQ for visibility on repeated failures. Consider SNS notifications on DLQ activity.
- For security, use least-privileged IAM policies for both Lambda (only SendMessage) and the local machine (SQS receive/delete, optional S3 put).

## Troubleshooting
- If orchestrator logs `boto3 is required`: install boto3 in the interpreter you are using to run orchestrator.
- If agent cannot discover tools: ensure `server.py` is running on http://localhost:8000/mcp; pass `--mcp-url` to agent_test.py if needed.
- If Unreal does not react: ensure StrandsInputServer is enabled and listening on 127.0.0.1:17777, and that Unreal has focus/input.
- Screenshots/state time out: check filesystem paths under `MyProject\Saved\...` and plugin permissions.
