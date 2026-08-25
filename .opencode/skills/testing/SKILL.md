---
name: ai-engineering-skills
description: Comprehensive technical knowledge base for AI Mentoring. Includes project architecture, AWS serverless patterns, Python Lambda standards, and testing guidelines.
---

# AI Engineering Skills — Consolidated Guide

## 1. Project Architecture (AI Mentoring)

Event-driven serverless platform converting exam photos into a structured question bank for AWS certification mentoring.

### Pipeline Flow
`S3 (exam photo) -> S3 Event -> SNS (notifications + email) -> SQS (main_queue + DLQ, max_concurrency=3) -> Lambda -> Rekognition (OCR) -> Bedrock Claude Haiku 4.5 -> DynamoDB`

### Core Resources
- **S3**: Bucket `daniel-mentoring-exam-photos-edn-dev` receives incoming exam photos. Frontend bucket `ai-mentoring-frontend-*` for static hosting.
- **SNS**: Email notifications (`notification_email`) on new photos; SQS subscription for pipeline ingestion. Access policy restricted by `SourceArn`.
- **SQS**: Decouples ingestion from processing; DLQ with `maxReceiveCount=4`. ESM `maximum_concurrency=3` for Bedrock rate-limit protection.
- **Lambda**: 3 handlers — `processor.py` (OCR pipeline, 256 MB, 30s, botocore adaptive retry), `student_api.py` (student CRUD, Cognito JWT validation, API Gateway v2.0), `quiz_engine.py` (quiz generation, answer submission, results).
- **Bedrock**: Claude Haiku 4.5 structures response as JSON. Canonical taxonomy enforced via `CANONICAL_TOPICS` (10 categories).
- **DynamoDB**: 4 tables — `MentoringQuestions` (QuestionID PK, TopicIndex GSI), `Students` (StudentID PK, EmailIndex GSI), `Quizzes` (QuizID PK, StudentIndex GSI), `QuizResults` (ResultID PK, QuizIndex + StudentIndex GSIs). All `PAY_PER_REQUEST`.
- **API Gateway**: HTTP API with JWT Authorizer (Cognito), 7 routes, throttling 50 rps / burst 100.
- **Cognito**: User Pool + App Client for student authentication (SRP, refresh tokens).
- **CloudFront**: CDN with OAC, HTTPS redirect, S3 origin.
- **IAM**: Least-privilege roles; OIDC for GitHub Actions (read-only CI).

---

## 2. AWS Serverless Infrastructure Patterns

- **Single Notification Resource**: AWS permits only one `aws_s3_bucket_notification` per bucket. Manage all SQS and SNS triggers within a single resource block to prevent state overwrites during `terraform apply`.
- **Dynamic References**: Always reference resources dynamically using attributes (`aws_resource.name.arn`), never hardcode literal ARNs.
- **Access Scope**: Scope IAM statements to explicit ARNs and restrict cross-service event sources using `aws:SourceArn` conditions.
- **Cost & Resilience**: Maintain DLQs for all event sources, enable `PAY_PER_REQUEST` on DynamoDB tables, and tune Lambda execution timeouts appropriately for AI calls.

---

## 3. Python & Lambda Development Standards

- **Runtime Setup**: Target Python 3.12 runtime. Initialize Boto3 SDK clients globally outside `lambda_handler` to enable connection reuse across cold starts.
- **Configuration**: Fetch table, bucket, and queue names dynamically from `os.environ`. Never hardcode resource names.
- **Logging & Error Handling**: Use structured `logging` configured at `INFO` level. Do not log sensitive data, raw tokens, or private keys. Raise explicit exceptions on batch processing failures so SQS can trigger retry logic.
- **Data Cleanup**: Validate incoming events defensively and sanitize model outputs (strip Markdown code fences) prior to executing `json.loads`.

---

## 4. Testing, Verification & Quality Control

- **AWS Mocking**: Run automated unit tests using `pytest` and mock all Boto3 SDK calls with `moto` or `unittest.mock`. Never execute unit tests against live AWS resources.
- **Syntax Verification**: Execute byte-compilation check locally before committing: `python -m py_compile src/*.py`
- **Terraform Verification**: Run `terraform validate` after editing `.tf` files and inspect `terraform plan` outputs to prevent accidental resource deletion or duplication.
- **Documentation Integrity**: Keep internal logs (`doc/status.md`) and public docs (`README.md`) strictly aligned with functional code.

---

## 5. Final Pre-Commit Checklist

1. `python -m py_compile src/*.py` and `pytest` pass cleanly with zero errors.
2. `terraform validate` executes successfully.
3. `terraform plan` confirms no state conflicts or unintended resource destructions.
4. Staged code contains no hardcoded secrets, API keys, or sensitive personal data.
5. API Gateway routes match Lambda integrations and permissions.
6. Cognito User Pool ID and App Client ID present in `outputs.tf`.
7. Internal log (`doc/status.md`) is updated with recent changes and debt items.
