---
name: python-lambda
description: Python standards, handler patterns, error handling, and runtime execution rules for AWS Lambda. Use when writing, refactoring, or reviewing Python code in `src/`.
---

# Python Lambda — Development Standards

## Runtime & Environment

- **Target Runtime**: Python 3.12.
- **Handler Structure**: Standard entry point `lambda_handler(event, context)`.
- **Environment Variables**: Fetch runtime configuration (e.g., table names, bucket names) via `os.environ`. Never hardcode resource names.
- **Initialization Outside Handler**: Initialize SDK clients (Boto3 `boto3.client(...)`, `boto3.resource(...)`) globally outside the handler function to reuse connections across cold starts.

## Code Quality & Structure

- **Type Hints**: Use Python type annotations for function arguments and return types.
- **Single Responsibility**: Keep `lambda_handler` focused on parsing events and routing orchestration. Delegate business logic, AI calls, and database operations to helper functions or modules.
- **JSON Parsing & Cleanup**: Validate incoming event structures defensively. Sanitize and clean model responses (e.g., stripping Markdown fences like ` ```json `) before parsing JSON.

## Error Handling & Logging

- **Structured Logging**: Use the standard `logging` module configured at `INFO` level. Do not use raw `print()` statements.
- **Sanitized Logs**: Never log entire raw payloads if they contain tokens, private keys, or sensitive student data.
- **SQS Event Batching Handling**:
  - Handle exceptions gracefully per record when processing SQS events.
  - Fail explicitly (raise exception) if an item cannot be processed so SQS can retry or route it to the DLQ.
  - Do not silently swallow exceptions unless intended.

## Dependencies & SDK

- **Boto3**: Rely on the AWS Lambda runtime-provided `boto3` library unless a specific version lock is required.
- **Lightweight Dependencies**: Keep external packages minimal to optimize deployment package size and reduce cold-start latency.
