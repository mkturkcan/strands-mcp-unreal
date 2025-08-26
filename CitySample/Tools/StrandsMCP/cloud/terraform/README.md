# Terraform: Strands Agent Invoker Stack (Option A)

This Terraform stack deploys:
- SQS FIFO queue + DLQ
- Lambda invoker (Python 3.11) that enqueues messages to SQS
- HTTP API Gateway routing POST /invoke to the Lambda

The local orchestrator (running on your Windows box) long-polls the SQS queue and invokes the Strands Agent locally.

## Prerequisites

- Terraform >= 1.3
- AWS credentials configured (e.g., `aws configure` or environment variables with permissions to create SQS, Lambda, API Gateway, and IAM)
- Python 3.11 for packaging the Lambda (done automatically via Terraform `archive_file`)

## Files

- `main.tf` – all resources and variables
- `../lambda_invoker/app.py` – Lambda handler packaged into a zip by Terraform

## Variables

Defined in `main.tf`:

- `aws_region` (string, default: `us-west-2`)
- `project_name` (string, default: `strands-agent`)
- `message_group_id` (string, default: `agent-1`)

You can override via CLI or a `terraform.tfvars` file, for example:
```
aws_region     = "us-west-2"
project_name   = "strands-agent"
message_group_id = "agent-1"
```

## Deploy

From this directory:
```
terraform init
terraform apply -auto-approve
```

Outputs:
- `api_endpoint` – Base URL of the HTTP API
- `invoke_url` – Full POST endpoint (use this)
- `sqs_queue_url` – Main FIFO queue URL (paste into orchestrator .env)
- `sqs_dlq_url` – DLQ URL
- `lambda_function_name`

## Invoke via API Gateway

Example HTTP request (PowerShell):
```
$invoke = (terraform output -raw invoke_url)
$body = @{ prompt = "Get to the highest point."; requestId = "req-1234" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri $invoke -ContentType "application/json" -Body $body
```

Example curl:
```
curl -X POST "$(terraform output -raw invoke_url)" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Get to the highest point.","requestId":"req-1234"}'
```

Response:
```
{
  "status": "queued",
  "requestId": "req-1234",
  "sqsMessageId": "...",
  "groupId": "agent-1"
}
```

## Orchestrator configuration

On the Windows box, copy `.env.example` to `.env` and set:
```
AWS_REGION=us-west-2
SQS_QUEUE_URL=<paste terraform output: sqs_queue_url>
S3_RESULTS_BUCKET=<optional bucket name>
MCP_URL=http://localhost:8000/mcp
CONCURRENCY=1
```

Start the orchestrator:
```
python MyProject/Tools/StrandsMCP/orchestrator.py
```

Ensure Unreal (with StrandsInputServer) and the MCP server are running locally.

## Clean up

To remove all resources:
```
terraform destroy
```

## Notes

- The Lambda is minimal and only publishes to SQS. It does not wait for agent completion.
- FIFO queue ensures sequential processing (single Unreal instance). Use distinct `message_group_id` for independent lanes.
- Use the DLQ to diagnose repeated failures of the orchestrator/agent.
