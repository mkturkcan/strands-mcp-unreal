# How the SQS Queue Is Read (Strands Orchestrator)

The local orchestrator at `Tools/StrandsMCP/orchestrator.py` reads the queue using AWS SQS long polling with `boto3`. It pulls messages, keeps them invisible while processing, and deletes them on success.

## Configuration (from .env)
- `AWS_REGION`: AWS region (e.g., `us-west-2`)
- `SQS_QUEUE_URL`: The FIFO queue URL
- `CONCURRENCY`: Number of worker threads (default 1)
- `SQS_WAIT_TIME`: Long-poll seconds (0..20, default 20)
- `SQS_VISIBILITY_EXTENSION_SEC`: Visibility timeout while processing (default 30)
- `POLL_SLEEP`: Small delay between iterations

A minimal `.env` loader reads these into environment variables on startup.

## Long-poll Receive
Each worker thread runs the `_worker_loop`, which repeatedly long-polls SQS:

```python
resp = sqs.receive_message(
    QueueUrl=SQS_QUEUE_URL,
    MaxNumberOfMessages=1,
    WaitTimeSeconds=SQS_WAIT_TIME,            # long-poll
    VisibilityTimeout=SQS_VISIBILITY_EXTENSION_SEC  # initial invisibility window
)
msgs = resp.get("Messages", [])
```

If no messages are returned, it loops and long-polls again.

## Processing a Message
`_process_message` parses the JSON body and expects:
```json
{
  "type": "invoke-agent",
  "prompt": "required",
  "sessionId": "optional",
  "options": { "includePreScreenshot": true, "includePostScreenshot": true, "includePreSense": true },
  "resultBucket": "optional",
  "resultKeyPrefix": "optional"
}
```

It starts a watchdog thread to extend visibility while the agent runs:
```python
sqs.change_message_visibility(
  QueueUrl=SQS_QUEUE_URL,
  ReceiptHandle=receipt_handle,
  VisibilityTimeout=SQS_VISIBILITY_EXTENSION_SEC
)
```
This prevents duplicate delivery during long-running work.

## Running the Agent
The orchestrator spawns the local agent runner:
```python
# Saved/Logs/Agent/{requestId}.log and Saved/AgentResults/{requestId}.json
proc = subprocess.Popen(
  [python, agent_test.py, "--prompt", prompt, "--mcp-url", mcp_url,
   "--result-json", result_json_path, "--session-id", session_id, ...],
  stdout=logfile, stderr=subprocess.STDOUT
)
ret = proc.wait()
```
- Logs go to `Saved/Logs/Agent/{requestId}.log`
- Result JSON goes to `Saved/AgentResults/{requestId}.json`

## Acknowledge vs Retry
- On success (`summary["status"] == "ok"`), the message is deleted:
```python
sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt)
```
- On failure or exception, the message is not deleted, so SQS re-delivers it after the visibility timeout. The main FIFO queue has a DLQ configured (Terraform) with `maxReceiveCount=5`.

## Optional Artifact Upload
If `S3_RESULTS_BUCKET` is set in `.env`, the orchestrator uploads:
- The result JSON
- The screenshot (`Saved/AutoScreenshot.png`) if present

```python
s3.upload_file(str(result_json_path), bucket, key)
s3.upload_file(str(screenshot_path), bucket, key)
```

## Ordering and Idempotency
- The queue is FIFO. The Lambda invoker uses:
  - `MessageGroupId` (default `agent-1`) to serialize all messages for a single Unreal instance.
  - `MessageDeduplicationId = requestId` to deduplicate within SQS’s 5‑minute window.
- The orchestrator relies on SQS FIFO for ordering/dedup (no separate processed-ID store).

## TL;DR
The orchestrator long-polls SQS, extends message visibility while the Agent executes, deletes on success, and lets SQS/ DLQ handle retries on failure. This provides a safe, pull-based trigger for the local Strands Agent.
