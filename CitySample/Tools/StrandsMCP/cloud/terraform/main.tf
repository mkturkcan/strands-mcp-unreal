terraform {
  required_version = ">= 1.3.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.4.0"
    }
  }
}

# -------------------------
# Variables
# -------------------------
variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-west-2"
}

variable "project_name" {
  description = "Base name prefix for resources"
  type        = string
  default     = "strands-agent"
}

variable "message_group_id" {
  description = "FIFO message group id (ensures sequential processing)"
  type        = string
  default     = "agent-1"
}

# -------------------------
# Provider / Data
# -------------------------
provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}

locals {
  name_prefix = var.project_name
}

# -------------------------
# SQS: DLQ and Main FIFO queue
# -------------------------
resource "aws_sqs_queue" "dlq" {
  name                        = "${local.name_prefix}-dlq.fifo"
  fifo_queue                  = true
  content_based_deduplication = false

  # Retain messages in DLQ for 14 days (max)
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "queue" {
  name                        = "${local.name_prefix}.fifo"
  fifo_queue                  = true
  content_based_deduplication = false

  # Initial visibility; orchestrator will extend while processing
  visibility_timeout_seconds = 60

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 5
  })
}

# -------------------------
# Lambda packaging (zip app.py)
# -------------------------
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda_invoker"
  output_path = "${path.module}/lambda_invoker.zip"
}

# -------------------------
# IAM for Lambda
# -------------------------
resource "aws_iam_role" "lambda_role" {
  name               = "${local.name_prefix}-invoker-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Principal = { Service = "lambda.amazonaws.com" },
      Action   = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Allow SendMessage to the main queue
resource "aws_iam_policy" "sqs_send" {
  name   = "${local.name_prefix}-sqs-send"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect   = "Allow",
      Action   = ["sqs:SendMessage"],
      Resource = [aws_sqs_queue.queue.arn]
    }]
  })
}

resource "aws_iam_role_policy_attachment" "attach_sqs_send" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.sqs_send.arn
}

# -------------------------
# Lambda Function
# -------------------------
resource "aws_lambda_function" "invoker" {
  function_name = "${local.name_prefix}-invoker"
  role          = aws_iam_role.lambda_role.arn
  runtime       = "python3.11"
  handler       = "app.lambda_handler"
  filename      = data.archive_file.lambda_zip.output_path
  timeout       = 10
  memory_size   = 256
  architectures = ["x86_64"]

  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      SQS_QUEUE_URL    = aws_sqs_queue.queue.url
      MESSAGE_GROUP_ID = var.message_group_id
    }
  }
}

# -------------------------
# API Gateway HTTP API (v2) with Lambda proxy
# -------------------------
resource "aws_apigatewayv2_api" "http" {
  name          = "${local.name_prefix}-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.invoker.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "post_invoke" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "POST /invoke"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http.id
  name        = "$default"
  auto_deploy = true
}

# Allow API Gateway to invoke Lambda
resource "aws_lambda_permission" "apigw_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.invoker.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*/invoke"
}

# -------------------------
# Outputs
# -------------------------
output "api_endpoint" {
  description = "Base URL for the HTTP API"
  value       = aws_apigatewayv2_api.http.api_endpoint
}

output "invoke_url" {
  description = "POST endpoint to queue an agent invocation"
  value       = "${aws_apigatewayv2_api.http.api_endpoint}/invoke"
}

output "sqs_queue_url" {
  description = "Main SQS FIFO queue URL"
  value       = aws_sqs_queue.queue.url
}

output "sqs_dlq_url" {
  description = "DLQ URL"
  value       = aws_sqs_queue.dlq.url
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.invoker.function_name
}
