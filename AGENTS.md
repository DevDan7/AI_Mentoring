# AGENTS.md — AI Mentoring

## 1. Purpose

This repository contains the AI Mentoring project.

The project objective is to build an AWS and AI-based platform to process
AWS certification questions, classify them, store them, and later use them
for learning processes, simulations, and student tracking.

OpenCode acts as an engineering assistant to develop, review, test,
and document this project.

---

## 2. OpenCode Role

OpenCode must behave as a senior engineering team.

It must:

- Analyze before modifying.
- Understand the existing architecture before proposing changes.
- Reuse existing code and resources.
- Avoid unnecessary complexity.
- Prioritize simple, maintainable, and scalable solutions.
- Explain important decisions.
- Keep documentation updated.
- Run tests after relevant changes.

---

## 3. Architecture

The current architecture primarily uses:

- AWS
- Terraform
- S3
- SQS
- Lambda
- Bedrock
- DynamoDB
- SNS
- Python

The existing architecture must be considered the source of truth before
proposing modifications.

Do not change the architecture without justifying:

1. Existing problem.
2. Proposed solution.
3. Benefit.
4. Impact.
5. Alternatives considered.

---

## 4. AWS

Principles:

- Prefer managed AWS services.
- Prefer serverless architecture when appropriate.
- Apply least privilege principle.
- Consider security, cost, reliability, and observability.
- Avoid unnecessary AWS resources.
- Infrastructure must be managed via Terraform.
- Do not introduce manual resources that should be managed by Terraform.

---

## 5. Code

### Python

- Use Python 3.12 when applicable.
- Keep functions small and clear.
- Avoid duplication.
- Use descriptive names.
- Handle errors explicitly.
- Do not introduce dependencies without justifying their need.

### Terraform

- Keep infrastructure modular and clear.
- Do not hardcode credentials.
- Use variables for configuration.
- Review IAM permissions before modifying them.
- Do not delete existing resources without analyzing the impact.

---

## 6. Security

Never:

- Hardcode credentials.
- Expose secrets.
- Commit sensitive information.
- Grant unnecessary IAM permissions.
- Disable security controls to fix issues quickly.

Any modification related to IAM, data, or permissions must be reviewed
before being applied.

---

## 7. Project Changes

Before modifying code:

1. Inspect related files.
2. Understand current behavior.
3. Identify dependencies.
4. Determine the impact of the change.
5. Propose a plan when the change is significant.

Do not rewrite functional components without a technical reason.

---

## 8. Testing

After implementing changes:

- Run related tests.
- Create tests when they don't exist for the modified functionality.
- Verify errors and edge cases.
- Do not consider an implementation finished if relevant tests fail.

---

## 9. Documentation

Important changes must be reflected in the corresponding documentation.

When any of the following changes:

- Architecture
- Infrastructure
- Data flow
- AWS services
- Technical decisions

the corresponding documentation must be updated.

### Skills Update

Skills in `.opencode/skills/` are **static files** that do not update automatically.
When the architecture or infrastructure changes significantly, update the corresponding
skill to keep agent context accurate:

- `ai-mentoring-architecture` — update pipeline, services, roadmap, or decisions.
- `aws-serverless` — update infrastructure rules or common pitfalls.
- `python-lambda` — update handler patterns or runtime rules.
- `testing` — update verification steps or checklist.

---

## 10. Git

Before committing:

- Review `git status`.
- Review the changes made.
- Do not include secrets.
- Do not include temporary files.
- Keep commits small and descriptive.

Do not `git push` automatically unless requested.

---

## 11. Agent Behavior

OpenCode must:

- Ask when there is ambiguity that could change the solution.
- Do not invent resources, files, or existing configurations.
- Do not assume a solution is correct without reviewing the code.
- Show important changes made.
- Report problems found during implementation.
- Prioritize simple solutions over excessively complex ones.

---

## 12. Definition of Done

A task is considered complete when:

- The requested functionality is implemented.
- Changes respect the architecture.
- Relevant tests pass.
- No exposed secrets exist.
- Infrastructure remains reproducible.
- Necessary documentation is updated.
- Changes can be reviewed via Git.

---

## 13. Architecture Rules

### Reference Patterns
- Pipeline reference in `.opencode/skills/ai-mentoring-architecture/SKILL.md` and `doc/DOCUMENTATION.md`.
- All evolution must be documented in `doc/changelog.md` and `doc/architecture.md`.

### Rules
1. **One AWS resource per managed object**: Never two `aws_*_notification`, configs or settings pointing to the same object (AWS overwrites complete configurations).
2. **References, not literals**: Every ARN is derived from a resource (`aws_resource.name.attribute`). Hardcoding ARNs or bucket names is prohibited.
3. **Decoupling**: Ingestion (S3) never talks directly to the processor (Lambda); always via SQS queue.
4. **Resilience**: Every event queue has DLQ; the processor must handle retries without breaking.
5. **Costs**: DynamoDB on `PAY_PER_REQUEST`; ephemeral or idle resources without state; evaluate cost before adding services.
6. **Least privilege**: Every IAM permission scoped to the resource ARN; `aws:SourceArn` conditions for third-party event services.
7. **Single source of truth**: Service configuration lives in the defining resource; nothing duplicated across files.
8. **Secrets ≠ repo**: Secrets and personal data travel via `.tfvars` variables (gitignored), never in committed code or state.
9. **Mandatory verification**: `terraform validate` before declaring finished; `terraform plan` when credentials are available.

---

## 14. AWS Rules

### Configuration
- **Region**: `us-east-1` (defined in `provider.tf`).
- **AWS Provider** `~> 6.0`; `archive` provider `~> 2.4`.
- Infrastructure 100% IaC with Terraform; no manually created resources in the console.

### Services
- **S3**: Bucket `daniel-mentoring-exam-photos-edn-dev`. Single notification configuration (SQS + SNS together in `aws_s3_bucket_notification`).
- **SQS**: Queue `mentoring-main-queue` with DLQ `mentoring-dlq` (`maxReceiveCount=4`); queue policy restricted by `aws:SourceArn` to the bucket.
- **Lambda**: `mentoring-exam-processor`, Python 3.12, 256 MB, timeout 30s, SQS trigger with `batch_size=1`.
- **DynamoDB**: Table `MentoringQuestions`, `QuestionID` (PK) + GSI `TopicIndex`, `PAY_PER_REQUEST`.
- **SNS**: Topic `AI-Mentoring-notifications-dev-daniel`; email subscription via variable `notification_email`; policy restricted by `aws:SourceArn`.
- **Bedrock**: Claude Haiku 4.5 model (`us.anthropic.claude-haiku-4-5-20251001-v1:0`).
- **Rekognition**: `DetectText` for OCR.

### CI/CD
- GitHub Actions authenticates via OIDC with role `ai-mentoring-github-actions` (read-only, `ReadOnlyAccess`).
- The role assumes claim `repo:DevDan7@152210372/AI_Mentoring@1326486822:*` — do not alter without verifying CloudTrail.

### Prohibited
- Creating resources outside Terraform.
- Changing region without updating `provider.tf` and reviewing other references.
- Modifying OIDC trust policy blindly (use CloudTrail to confirm claims).

---

## 15. Python Rules

### Environment
- **Python 3.12**; virtualenv `.venv` (do not commit).
- Dependencies in `requirements.txt`; minimal packages (boto3).

### Structure
- Handlers in `src/` like `processor.py` with `lambda_handler(event, context)`.
- Boto3 clients initialized at module level, once.
- Configuration via environment variables with safe fallback (e.g., `os.environ.get('TABLE_NAME', '...')`).

### Style
- Standard library imports first, then boto3/third-party.
- No comments repeating the code; only business context if it adds value.
- `print()` for CloudWatch logging; never log secrets or personal data.
- Descriptive names in English (the project mixes ES in IaC comments; in code, English).

### Error Handling
- Validate test messages/invalid events and skip them (`continue`).
- In Lambda handler: log the error and re-raise for SQS retry per queue policy.
- URL-decode S3 keys (`urllib.parse.unquote_plus`).
- Parse Bedrock responses after cleaning markdown fences (```json).

### Verification
- `python -m py_compile src/processor.py` without errors.
- Verify Bedrock prompt JSON requests strict structure and code validates before `put_item`.

---

## 16. Security Rules

### Secrets and Personal Data
1. **Prohibited** to commit secrets, credentials, personal emails, or tokens in any file.
2. Sensitive values go in `variables.tf` (with `sensitive = true`) and actual value in `terraform.tfvars` (excluded by `.gitignore` with `*.tfvars`).
3. Verify `git status` and `git diff` before committing to confirm no secrets entered the repo.
4. If a secret is exposed: rotate and log the incident in `doc/changelog.md`.

### Terraform State
- `terraform.tfstate` and `.tfstate.backup` contain sensitive ARNs/IDs: **do not** commit. Remote backend (S3 + DynamoDB lock) pending — evaluate.
- `.terraform/` and `.venv/` not committed.

### IAM and Policies
- Least privilege principle: every statement scoped to necessary ARNs.
- Third-party event services (SQS, SNS) restrict with `aws:SourceArn` condition to the exact bucket.
- CI role (`github-actions`) is **read-only**; should not be able to apply changes.

### CI/CD (OIDC)
- No long-lived credentials in GitHub Secrets for Terraform; use OIDC.
- OIDC role trust policy with exact `aud` and `sub`; verify claims with CloudTrail on assumption failures.

---

## 17. Workflow Rules

### Git Operations
- NEVER execute `git add`, `git commit`, `git push`, or any git write operation.
- At the end of every task that modifies files, deliver ready git commands with appropriate messages for manual execution.
- Output format at task end:
  ```
  ## Git Commands to Execute:
  git add [files]
  git commit -m "[message]"
  git push origin [branch]
  ```

### Terraform Operations
- NEVER execute `terraform apply` or `terraform destroy`.
- At the end of every infrastructure task, deliver ready commands:
  ```
  ## Terraform Commands to Execute:
  terraform validate
  terraform plan
  terraform apply
  ```

### Educational Approach (Socratic)
- For Terraform infrastructure changes, explain the WHY of each decision before implementing.
- Use guiding questions: "Why do you think this resource needs this configuration?", "What would happen if we remove this parameter?".
- Contextualize each change with the current project architecture.

### Infrastructure Evaluation
- Before implementing infrastructure changes, evaluate pros, cons, and alternatives.
- Use the `/infra-eval` command for formal evaluations.

---

## 18. Communication Rules
- Respond in Spanish when the user speaks in Spanish.
- Be direct and technical, without unnecessary preamble.
- At the end of every task, deliver ready-to-run commands.
