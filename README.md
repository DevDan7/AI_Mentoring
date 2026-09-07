# AI Mentoring

![AI MENTORING](img/AI_Mentoring_banner.png)

Serverless, event-driven platform that turns exam-question photos into a structured question bank, built to support AWS certification mentoring sessions at Escola da Nuvem.

This project is already in real use in my mentoring sessions and is being actively developed toward a fully operational platform — with the long-term goal of exploring monetization once the student-facing features are in place.

---

## 🏗️ Solution Architecture 

![Arquitetura AWS Serverless](img/architecture_AI_Mentoring.png)

--- 

## What it does today

Mentoring students send photos of exam-style questions (from mock exams they're studying). The pipeline automatically extracts the question, classifies it by topic and difficulty, and stores it in a structured database — building a growing question bank that feeds future "commented mock exam" classes.

Students flow through a simplified learning model: they take a diagnostic quiz (`initial`), move to free practice by topic, and sit a teacher-released 65-question final exam (`final_exam`). The teacher dashboard manages students, cohorts, phase changes and final-exam release/reset.

## Architecture

```
[Student Browser]
    → AWS Amplify (HTTPS hosting, auto-deploy from GitHub)
    → API Gateway HTTP API (JWT Authorizer)
        → Lambda (student_api.py) → DynamoDB (Students, Cohorts)
        → Lambda (quiz_engine.py) → DynamoDB (Quizzes, QuizResults, MentoringQuestions)

[Exam Photo Pipeline]
S3 (exam question photo)
   → S3 Event Notification
   → SQS (main queue, with DLQ)
   → Lambda (processor.py)
        → Amazon Bedrock — Claude (multimodal: OCR + structuring into topic, explanation, difficulty)
   → DynamoDB (MentoringQuestions)
```

- **Amazon S3** — receives the exam question photo upload.
- **AWS Amplify** — HTTPS hosting for the frontend (`index`, `dashboard`, `quiz`, `results`, `teacher`) with auto-deploy on each push to `main`.
- **Amazon API Gateway** (HTTP API) — entry point for all student-facing API calls; JWT Authorizer validates Cognito tokens before reaching Lambda.
- **Amazon SQS** — decouples ingestion from processing; includes a Dead Letter Queue (`maxReceiveCount=4`) so a failed message doesn't get lost or block the queue.
- **AWS Lambda** (`processor.py`) — reads the exam photo from S3 and sends the image directly to Amazon Bedrock (Claude, multimodal) for OCR + structured JSON (`topic`, `explanation`, `difficulty`), then writes to DynamoDB (Rekognition was removed on 2026-09-02).
- **AWS Lambda** (`student_api.py`) — auth with JWT claims + `cognito:groups`, CRUD for student profiles, cohorts, config and final-exam management.
- **AWS Lambda** (`quiz_engine.py`) — generates quizzes (diagnostic, free by topic, final exam), records responses, resumes `in_progress` sessions, computes results with `domain_breakdown`.
- **Amazon DynamoDB** (`MentoringQuestions`) — `QuestionID` as partition key, with a GSI on `Topic` for querying the question bank by subject.
- **Amazon DynamoDB** (`Quizzes`, `QuizResults`) — stores quiz sessions and student answers.
- **Amazon DynamoDB** (`Students`) — stores profiles (phase `initial`/`free_practice`/`final_exam`) with GSIs on `Email` and `CohortID`.
- **Amazon DynamoDB** (`Cohorts`) — seminars with capacity limit (`MaxStudents`); `turma-beta-01` seeded and active.
- **Amazon Cognito** — User Pool + App Client for student authentication; email/password login, JWT tokens for API access.
- **IAM** — dedicated roles and policies scoped to only the resources each Lambda needs.
- **Terraform** — the entire infrastructure above is defined as code.

## Tech stack

AWS Lambda · Amazon API Gateway · Amazon SQS · Amazon DynamoDB · Amazon Bedrock · Amazon S3 · AWS Amplify · Amazon Cognito · IAM · Terraform · Python (Boto3) · HTML · CSS (Pico.css) · JavaScript · Hypothesis (property-based tests)

## Project structure

```
.
├── main.tf, iam.tf, dynamodb.tf, lambda.tf, provider.tf   # Infrastructure as Code
├── api_gateway.tf, api_gateway_authorizer.tf, api_gateway_routes.tf  # API Gateway HTTP API
├── lambda_quiz_engine.tf, iam_student_api.tf               # Quiz engine Lambda + IAM
├── lambda_student_api.tf, iam_student_api.tf               # Student API Lambda + IAM
├── cognito.tf, outputs.tf                                  # Cognito User Pool + App Client
├── amplify.tf                                              # Amplify Hosting for the frontend
├── requirements.txt        # Python dependencies packaged with the Lambda
├── src/
│   ├── processor.py        # Lambda: Bedrock multimodal (OCR + JSON) + DynamoDB
│   ├── quiz_engine.py      # Lambda: quizzes, respuestas, examen final (65q)
│   ├── student_api.py      # Lambda: CRUD alumno/cohorte + final-exam release/reset
│   └── frontend/           # Frontend (HTML/CSS/JS, deployed via Amplify)
│       ├── index.html      # Login / Registro
│       ├── dashboard.html  # Perfil del alumno + generar quiz
│       ├── quiz.html       # Tomar quiz
│       ├── results.html    # Ver resultados
│       ├── teacher.html    # Panel del profesor (alumnos, cohortes, fases, examen)
│       └── js/             # Módulos JS (config, auth, api, teacher)
├── events/                 # Test events for Lambda invocations
│   └── apigw/              # Test events en formato API Gateway v2.0
├── scripts/
│   ├── test_api.sh         # Script de testing end-to-end
│   ├── migrate_clean.py    # Migración: limpieza de tablas + seed turma-beta-01 (manual)
│   └── migrate_restore.py  # Migración: restauración desde backups (manual)
├── doc/
│   ├── DOCUMENTATION.md    # Índice de documentación del proyecto
│   ├── architecture.md     # Arquitectura, modelo de datos, decisiones
│   ├── technical-log.md    # Pruebas, problemas, soluciones
│   ├── changelog.md        # Registro de cambios consolidado
│   ├── roadmap.html        # Roadmap interactivo del proyecto
│   └── questions/          # Banco de preguntas (PNG)
└── README.md
```

Infrastructure code lives at the project root; application code lives under `src/` — this keeps the Lambda deployment package (zipped by Terraform's `archive_file`) limited to only the code that actually runs, without pulling in Terraform files or documentation.

## Roadmap

The pipeline above covers question ingestion and classification — one piece of a larger platform. Status:

- [x] Student profiles and progress tracking (simplified phase model: `initial` → `free_practice` → `final_exam`)
- [x] Quiz results storage (linking students to questions answered, correct/incorrect, timestamps) with `domain_breakdown`
- [x] A way for students to answer quizzes (Amplify-hosted frontend: index, dashboard, quiz, results)
- [x] Teacher dashboard (students, cohorts, phase changes, final-exam release/reset)
- [x] Final exam (65 questions, CLF-C02 matrix, release-by-date, 1 attempt, anti-repetition, resume `in_progress`)
- [x] Beta cohort seeded (`turma-beta-01`) and data migration for production cleanup (2026-09-07)
- [ ] Automated report generation (monthly/annual metrics per student and per class)
- [ ] CloudFront legacy cleanup (replaced by Amplify)

Full engineering notes and technical debt tracking live in [`doc/DOCUMENTATION.md`](doc/DOCUMENTATION.md).

## Documentation

Internal documentation lives in `doc/`, organized by theme:

| File | Purpose |
|------|---------|
| [`DOCUMENTATION.md`](doc/DOCUMENTATION.md) | Documentation index and maintenance instructions |
| [`architecture.md`](doc/architecture.md) | System architecture, data model, design decisions |
| [`technical-log.md`](doc/technical-log.md) | Performance tests, problems, solutions |
| [`changelog.md`](doc/changelog.md) | Consolidated chronological change log |
| [`roadmap.html`](doc/roadmap.html) | Interactive project roadmap |

Each file is self-contained. Start with `DOCUMENTATION.md` for an overview of the project's technical state.

## Deploying

```bash
# Infrastructure
terraform init
terraform plan
terraform apply

# Frontend: auto-deployed by AWS Amplify on push to main (no manual sync needed)
```

Data migration scripts (manual, never via CI/CD) live in `scripts/`:

```bash
python scripts/migrate_clean.py --dry-run   # verify, no mutation
python scripts/migrate_clean.py             # export → confirm "SI" → clean → seed turma-beta-01
python scripts/migrate_restore.py           # restore from latest backup set in scripts/backup/
```

Requires Terraform >= 1.5.0, Python 3.12, AWS CLI configured with active credentials, and a deployed Cognito User Pool.

## Author

**Daniel Villegas**
Cloud Engineer | AWS Certified (4x)
[LinkedIn](https://www.linkedin.com/in/vdaniel07) · [GitHub](https://github.com/DevDan7)
