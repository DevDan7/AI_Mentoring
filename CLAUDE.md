# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This repo also has `AGENTS.md`, written for OpenCode but equally applicable here — it's the fuller,
authoritative source for engineering conventions (Python/Terraform style, IAM rules, definition-of-done).
This file covers commands and architecture; read `AGENTS.md` for the rest.

## Critical workflow rules

- **NEVER run `git add`, `git commit`, `git push`, `terraform apply`, or `terraform destroy`.** At the end
  of any task that changes files or infra, output ready-to-run commands for the user to execute manually.
- Data migration scripts (`scripts/migrate_*.py`) are manual-only — never wire them into CI/CD.
- Secrets/personal data only via `terraform.tfvars` (gitignored) or `sensitive = true` Terraform variables —
  never in committed code or `.tfstate`.
- Respond in Spanish when the user writes in Spanish; be direct and technical.
- For Terraform infra changes, explain the *why* before implementing (this project treats infra changes as
  a teaching opportunity for the user).

## Commands

```bash
# Tests
pytest                                    # full suite (tests/), includes Hypothesis property-based tests
python -m py_compile src/processor.py     # quick sanity compile check for a Lambda handler

# Terraform (validate/plan only — never apply/destroy, see above)
terraform init
terraform validate
terraform plan

# End-to-end API smoke test (hardcoded test user/Cognito client in the script)
bash scripts/test_api.sh

# Data migration (manual only, never CI/CD)
python scripts/migrate_clean.py --dry-run   # verify, no mutation
python scripts/migrate_clean.py             # export → confirm → clean → seed turma-beta-01
python scripts/migrate_restore.py           # restore from scripts/backup/
```

Frontend has no build step — it's static HTML/CSS/JS deployed by AWS Amplify automatically on push to `main`.

## Architecture

Serverless, event-driven AWS platform with two pipelines:

**Exam-photo ingestion** (builds the question bank):
```
S3 (photo upload) → S3 Event Notification → SQS (main queue + DLQ, maxReceiveCount=4)
  → Lambda processor.py → Amazon Bedrock (Claude, multimodal OCR + JSON structuring)
  → DynamoDB MentoringQuestions
```

**Student-facing platform**:
```
Browser → AWS Amplify (static frontend) → API Gateway HTTP API (JWT Authorizer, Cognito)
  → Lambda student_api.py  → DynamoDB Students, Cohorts
  → Lambda quiz_engine.py  → DynamoDB Quizzes, QuizResults, MentoringQuestions
```

Key points:
- **Infra code lives at repo root** (`*.tf`), **application code under `src/`** — deliberate split so
  Terraform's `archive_file` only zips runtime code for Lambda deployment packages.
- Three Lambda handlers share this repo: `src/processor.py`, `src/quiz_engine.py`, `src/student_api.py`,
  each `lambda_handler(event, context)`, boto3 clients created once at module level.
- **Auth**: Cognito User Pool + JWT Authorizer on API Gateway. Teacher role comes from the `cognito:groups`
  claim — in API Gateway HTTP API v2 payloads this claim arrives as a JSON-encoded *string*, not a native
  array/object, and must be parsed before use (see `src/student_api.py` and recent commit history for the fix).
- **Student phase model**: `initial` (diagnostic quiz) → `free_practice` (by topic) → `final_exam`
  (65-question CLF-C02 exam, teacher-released, 1 attempt, anti-repetition, resumable if `in_progress`).
- **DynamoDB**: `MentoringQuestions` (PK `QuestionID`, GSI `TopicIndex`), `Students` (GSIs on `Email`,
  `CohortID`), `Cohorts` (capacity via `MaxStudents`), `Quizzes`, `QuizResults` — all `PAY_PER_REQUEST`.
- Region `us-east-1`; AWS provider `~> 6.0`, `archive` provider `~> 2.4` (`provider.tf`).
- Bedrock model: `us.anthropic.claude-haiku-4-5-20251001-v1:0`.

## CI/CD

- `.github/workflows/terraform-plan.yml` — runs `terraform plan` on PRs to `main`.
- `.github/workflows/terraform-apply.yml` — runs `terraform apply -auto-approve` on push to `main` (production
  GitHub environment).
- Both authenticate via OIDC assuming `ai-mentoring-github-actions`, a **read-only** IAM role — CI cannot
  itself apply infra changes beyond what that role permits.
- Frontend (`src/frontend/`) auto-deploys via AWS Amplify on push to `main` — no manual sync step.
