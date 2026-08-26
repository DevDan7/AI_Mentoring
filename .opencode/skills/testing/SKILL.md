---
name: testing
description: Testing, verification and quality control guidelines for AI Mentoring project.
---

# Testing — Project Verification

## 1. Testing Standards

- **AWS Mocking**: Run automated unit tests using `pytest` and mock all Boto3 SDK calls with `moto` or `unittest.mock`. Never execute unit tests against live AWS resources.
- **Syntax Verification**: Execute byte-compilation check locally before committing: `python -m py_compile src/*.py`
- **Terraform Verification**: Run `terraform validate` after editing `.tf` files and inspect `terraform plan` outputs to prevent accidental resource deletion or duplication.
- **Documentation Integrity**: Keep internal logs (`doc/status.md`) and public docs (`README.md`) strictly aligned with functional code.

## 2. Final Pre-Commit Checklist

1. `python -m py_compile src/*.py` and `pytest` pass cleanly with zero errors.
2. `terraform validate` executes successfully.
3. `terraform plan` confirms no state conflicts or unintended resource destructions.
4. Staged code contains no hardcoded secrets, API keys, or sensitive personal data.
5. API Gateway routes match Lambda integrations and permissions.
6. Cognito User Pool ID and App Client ID present in `outputs.tf`.
7. Internal log (`doc/status.md`) is updated with recent changes and debt items.

## 3. Related Skills

For architecture context, load `ai-mentoring-architecture`. For AWS serverless patterns, load `aws-serverless`. For Python standards, load `python-lambda`.
