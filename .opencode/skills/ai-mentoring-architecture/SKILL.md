---
name: ai-mentoring-architecture
description: Architecture and context for the AI Mentoring project. Use when working on any task related to the project: pipeline, AWS services, data model, roadmap, or technical log.
---

# AI Mentoring — Project Architecture

Event-driven serverless platform that converts photos of exam questions into a structured question bank for AWS certification mentoring at Escola da Nuvem.

## Current Pipeline (Functional)

`S3 (exam photo) -> S3 Event -> SNS (notifications + email) -> SQS (main_queue + DLQ, max_concurrency=3) -> Lambda -> Rekognition (OCR) -> Bedrock Claude Haiku 4.5 -> DynamoDB`

## Services and Roles

- **S3** — Bucket `daniel-mentoring-exam-photos-edn-dev` receives incoming photos. Frontend bucket `ai-mentoring-frontend-*` for static hosting.
- **SNS** — Email notifications (`notification_email`) on new photos; SQS subscription for pipeline ingestion. Access policy restricted by `SourceArn`.
- **SQS** — Decouples ingestion from processing; DLQ with `maxReceiveCount=4`. ESM `maximum_concurrency=3` for Bedrock rate-limit protection.
- **Lambda** — 3 handlers: `processor.py` (OCR pipeline, 256 MB, 30s, botocore adaptive retry), `student_api.py` (student CRUD, Cognito JWT validation, API Gateway v2.0), `quiz_engine.py` (quiz generation, answer submission, results).
- **Bedrock** — Claude Haiku 4.5 structures response as JSON. Canonical taxonomy enforced via `CANONICAL_TOPICS` (10 categories).
- **DynamoDB** — 4 tables: `MentoringQuestions` (QuestionID PK, TopicIndex GSI), `Students` (StudentID PK, EmailIndex GSI), `Quizzes` (QuizID PK, StudentIndex GSI), `QuizResults` (ResultID PK, QuizIndex + StudentIndex GSIs). All `PAY_PER_REQUEST`.
- **API Gateway** — HTTP API with JWT Authorizer (Cognito), 7 routes, throttling 50 rps / burst 100.
- **Cognito** — User Pool + App Client for student authentication (SRP, refresh tokens).
- **CloudFront** — CDN with OAC, HTTPS redirect, S3 origin.
- **IAM** — Least-privilege roles; OIDC for GitHub Actions (read-only CI).

## Key Architectural Decisions

- **Single `aws_s3_bucket_notification`**: AWS allows only one notification configuration per bucket; `queue` and `topic` must reside within the same resource block.
- **Derived ARNs**: Always use resource attributes (`aws_resource.name.attribute`), never hardcoded literals.
- **Secrets in `.tfvars`** (gitignored): Sensitive values passed via variables; non-sensitive default values stored in `variables.tf`.
- **Local State** (Pending): Evaluate remote backend using S3 + DynamoDB locking.

## Roadmap

1. ✅ Data model for students and mock exam results (3 DynamoDB tables created 2026-08-18).
2. ✅ Lambda/endpoint to log student answers (`student_api.py`, `quiz_engine.py` created 2026-08-21).
3. CI/CD with `terraform apply` on main (GitHub Environments with required reviewers).
4. Migrate frontend to AWS Amplify.
5. Auto-registration via Cognito + DynamoDB sync.
6. Refactor to AWS Step Functions for async orchestration.
7. Resolve duplicate handling; evaluate remote backend (S3 + DynamoDB lock).

## Sources

- `README.md` — Public documentation (recruiters).
- `doc/DOCUMENTATION.md` — Documentation index and maintenance instructions.
- `doc/architecture.md` — Internal technical log: architecture, data model, decisions.
- `doc/changelog.md` — Consolidated chronological change log.