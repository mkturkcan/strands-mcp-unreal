#!/usr/bin/env python3
import os
import json
import uuid
import base64
from typing import Any, Dict

import boto3

SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL", "")
MESSAGE_GROUP_ID = os.environ.get("MESSAGE_GROUP_ID", "agent-1")  # FIFO queue group for sequential processing

sqs = boto3.client("sqs")


def _parse_event_body(event: Dict[str, Any]) -> Dict[str, Any]:
    body = event.get("body", "")
    if not isinstance(body, str):
        return {}
    if event.get("isBase64Encoded"):
        try:
            body = base64.b64decode(body).decode("utf-8", errors="ignore")
        except Exception:
            return {}
    try:
        return json.loads(body)
    except Exception:
        return {}


def _response(status: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def lambda_handler(event, context):
    # HTTP API (APIGW v2) compatibility
    method = (event.get("requestContext", {}).get("http", {}) or {}).get("method", "POST")
    if method != "POST":
        return _response(405, {"error": "method_not_allowed", "detail": f"{method} not supported, use POST"})

    if not SQS_QUEUE_URL:
        return _response(500, {"error": "config_error", "detail": "SQS_QUEUE_URL is not configured"})

    body = _parse_event_body(event)
    if not body:
        return _response(400, {"error": "invalid_json"})

    # Required: prompt
    prompt = str(body.get("prompt") or "").strip()
    if not prompt:
        return _response(400, {"error": "missing_field", "field": "prompt"})

    # Optional
    request_id = str(body.get("requestId") or str(uuid.uuid4()))
    session_id = body.get("sessionId")
    options = body.get("options") if isinstance(body.get("options"), dict) else None
    result_bucket = body.get("resultBucket")
    result_prefix = body.get("resultKeyPrefix")
    group_id = str(body.get("groupId") or MESSAGE_GROUP_ID or "agent-1")

    # Build message payload for the local orchestrator
    msg: Dict[str, Any] = {
        "type": "invoke-agent",
        "prompt": prompt,
        "requestId": request_id,
    }
    if session_id:
        msg["sessionId"] = session_id
    if options:
        msg["options"] = options
    if result_bucket:
        msg["resultBucket"] = result_bucket
    if result_prefix:
        msg["resultKeyPrefix"] = result_prefix

    try:
        resp = sqs.send_message(
            QueueUrl=SQS_QUEUE_URL,
            MessageBody=json.dumps(msg, separators=(",", ":")),
            MessageGroupId=group_id,
            MessageDeduplicationId=request_id,  # ensure idempotency on FIFO queues
        )
        return _response(
            202,
            {
                "status": "queued",
                "requestId": request_id,
                "sqsMessageId": resp.get("MessageId"),
                "groupId": group_id,
            },
        )
    except Exception as e:
        return _response(500, {"error": "sqs_send_failed", "detail": f"{type(e).__name__}: {e}"})
