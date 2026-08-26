---
description: Review changes or a diff looking for errors, security issues and technical debt.
agent: reviewer
---

Review the following changes in the AI Mentoring project:

**Scope:** $ARGUMENTS

## Process

1. Identify the affected files and lines.
2. Look for: functional errors (duplicated resources, broken references), security flaws (secrets, overly permissive permissions), technical debt (hardcoded values, dead code), and misalignment with repo patterns.
3. Report with severity (CRITICAL / HIGH / MEDIUM / LOW), file:line, issue and suggested fix.

## Output

- Summary of changes.
- Findings sorted by severity.
- Verdict: APPROVED / CHANGES REQUIRED / REJECTED.
