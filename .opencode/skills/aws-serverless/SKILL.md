---
name: aws-serverless
description: AWS serverless architecture patterns and best practices for this repository. Use when writing or reviewing Terraform infrastructure (S3, SQS, Lambda, DynamoDB, SNS, IAM) or designing event flows.
---

# AWS Serverless — Project Patterns

## Services Used

- **Amazon S3**: Object storage for exam photos (`s3:ObjectCreated:*` events) and frontend static hosting.
- **Amazon SNS**: Event routing (S3 → SNS → SQS) and email notifications.
- **Amazon SQS**: Main queue + DLQ to decouple ingestion from processing. ESM `maximum_concurrency=3`.
- **AWS Lambda**: Python 3.12 handlers — `processor.py` (SQS-triggered OCR), `student_api.py` (API GW-triggered CRUD), `quiz_engine.py` (API GW-triggered quiz engine).
- **Amazon DynamoDB**: 4 tables (`PAY_PER_REQUEST`), GSIs for topic/email/quiz/student queries.
- **Amazon API Gateway**: HTTP API, JWT Authorizer (Cognito), 7 routes, payload format v2.0.
- **Amazon Cognito**: User Pool + App Client for student authentication (SRP, refresh tokens).
- **Amazon CloudFront**: CDN with OAC, HTTPS redirect, S3 origin.
- **Amazon Rekognition**: OCR (`DetectText`).
- **Amazon Bedrock**: Claude Haiku 4.5 for structured JSON responses.
- **IAM**: Least-privilege roles; OIDC for GitHub Actions.

## Infrastructure Rules (Terraform)

- **Single Management Resource**: Never use two resources to manage the same object (e.g., only one `aws_s3_bucket_notification` per bucket). Multiple resources cause `apply` operations to overwrite each other.
- **Attribute References**: Always reference resources dynamically via attributes (`aws_resource.name.arn`), never hardcoded ARNs.
- **Scoped Permissions**: Every IAM statement must target specific resource ARNs; restrict with `aws:SourceArn` conditions when handling cross-service events.
- **Resilience**: Always configure a DLQ with a reasonable `maxReceiveCount`; enforce idempotency and duplicate handling.
- **Cost Optimization**: Use `PAY_PER_REQUEST` for DynamoDB, minimum required `memory_size` for Lambda, and eliminate idle resources.
- **API Gateway + Lambda**: Use payload format version `2.0`. Configure JWT Authorizer with Cognito User Pool ARN. Every route must specify `authorization_type = "JWT"`.
- **Cognito Configuration**: App Client must set `generate_secret = false` for frontend SPAs. Configure `prevent_user_existence_errors = "ENABLED"`. Token validity: access/id 1h, refresh 30d.
- **CloudFront + S3**: Use OAC (not legacy OAI). Bucket policy must condition on `AWS:SourceArn` matching the distribution ARN. Block all public access on S3.
- **Validation**: Always validate using `terraform validate` (and `terraform plan` when AWS credentials are active).

## Common Pitfalls

- SQS/SNS policies missing `aws:SourceArn` condition → allows unauthorized resources to publish messages.
- Renaming a bucket in state without updating literal references.
- Lambda timeouts set too short for AI/OCR calls (Bedrock/Rekognition).
- Deploying services/resources outside the target region (`us-east-1`).
- API Gateway route added without corresponding Lambda `aws_lambda_permission` → Integration fails with 503.
- Cognito token expiry (1h access token) causing infinite redirect loops in frontend if refresh fails.
- DynamoDB `Unused attributes` error when defining non-indexed attributes in Terraform `attribute` blocks.
