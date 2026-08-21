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

## Architecture

```
[Student Browser]
    → CloudFront (HTTPS CDN)
    → S3 (Landing Page: HTML/CSS/JS)
    → API Gateway HTTP API (JWT Authorizer)
        → Lambda (student_api.py) → DynamoDB (Students)
        → Lambda (quiz_engine.py) → DynamoDB (Quizzes, QuizResults, MentoringQuestions)

[Exam Photo Pipeline]
S3 (exam question photo)
   → S3 Event Notification
   → SQS (main queue, with DLQ)
   → Lambda (processor.py)
        → Amazon Rekognition (OCR)
        → Amazon Bedrock — Claude (structures topic, explanation, difficulty)
   → DynamoDB (MentoringQuestions)
```

- **Amazon S3** — receives the exam question photo upload; also hosts the Landing Page (static files).
- **Amazon CloudFront** — CDN with HTTPS for the Landing Page; default CloudFront domain.
- **Amazon API Gateway** (HTTP API) — entry point for all student-facing API calls; JWT Authorizer validates Cognito tokens before reaching Lambda.
- **Amazon SQS** — decouples ingestion from processing; includes a Dead Letter Queue (`maxReceiveCount=4`) so a failed message doesn't get lost or block the queue.
- **AWS Lambda** (`processor.py`) — runs OCR via Rekognition, then prompts Amazon Bedrock (Claude) to return structured JSON (`topic`, `explanation`, `difficulty`), and writes the result to DynamoDB.
- **AWS Lambda** (`student_api.py`) — CRUD operations for student profiles; reads JWT claims from API Gateway for authentication.
- **AWS Lambda** (`quiz_engine.py`) — generates quizzes from the question bank, records student responses, and calculates metrics.
- **Amazon DynamoDB** (`MentoringQuestions`) — `QuestionID` as partition key, with a GSI on `Topic` for querying the question bank by subject.
- **Amazon DynamoDB** (`Quizzes`, `QuizResults`) — stores quiz sessions and student answers.
- **Amazon DynamoDB** (`Students`) — stores student profiles with GSI on `Email`.
- **Amazon Cognito** — User Pool + App Client for student authentication; email/password login, JWT tokens for API access.
- **IAM** — dedicated roles and policies scoped to only the resources each Lambda needs.
- **Terraform** — the entire infrastructure above is defined as code.

## Tech stack

AWS Lambda · Amazon API Gateway · Amazon SQS · Amazon DynamoDB · Amazon Rekognition · Amazon Bedrock · Amazon S3 · Amazon CloudFront · Amazon Cognito · IAM · Terraform · Python (Boto3) · HTML · CSS (Pico.css) · JavaScript

## Project structure

```
.
├── main.tf, iam.tf, dynamodb.tf, lambda.tf, provider.tf   # Infrastructure as Code
├── api_gateway.tf, api_gateway_authorizer.tf, api_gateway_routes.tf  # API Gateway HTTP API
├── lambda_quiz_engine.tf, iam_student_api.tf               # Quiz engine Lambda + IAM
├── lambda_student_api.tf, iam_student_api.tf               # Student API Lambda + IAM
├── cognito.tf, outputs.tf                                  # Cognito User Pool + App Client
├── landing.tf                                              # S3 + CloudFront for frontend
├── requirements.txt        # Python dependencies packaged with the Lambda
├── src/
│   ├── processor.py        # Lambda: OCR + Bedrock + DynamoDB
│   ├── quiz_engine.py      # Lambda: generación de quizzes y registro de respuestas
│   ├── student_api.py      # Lambda: CRUD de alumnos con validación Cognito
│   └── frontend/           # Landing Page (HTML/CSS/JS)
│       ├── index.html      # Login / Registro
│       ├── dashboard.html  # Perfil del alumno + generar quiz
│       ├── quiz.html       # Tomar quiz
│       ├── results.html    # Ver resultados
│       └── js/             # Módulos JS (config, auth, api)
├── events/                 # Test events for Lambda invocations
│   └── apigw/              # Test events en formato API Gateway v2.0
├── scripts/
│   └── test_api.sh         # Script de testing end-to-end
├── doc/
│   ├── status.md           # Engineering log: findings, technical debt, roadmap
│   ├── roadmap.html        # Roadmap interactivo del proyecto
│   └── quiz-results-dashboard.html  # Quiz results visualization
└── README.md
```

Infrastructure code lives at the project root; application code lives under `src/` — this keeps the Lambda deployment package (zipped by Terraform's `archive_file`) limited to only the code that actually runs, without pulling in Terraform files or documentation.

## Roadmap

The pipeline above covers question ingestion and classification — one piece of a larger platform. Next up:

- [x] Student profiles and progress tracking
- [x] Quiz results storage (linking students to questions answered, correct/incorrect, timestamps)
- [x] A way for students to actually answer generated questions (Landing Page with quiz interface)
- [ ] "Class generation" logic: pull questions by topic/difficulty, prioritizing a student's weak areas
- [ ] Automated report generation (monthly/annual metrics per student and per class)

Full engineering notes and technical debt tracking live in [`doc/status.md`](doc/status.md).

## Deploying

```bash
# Infrastructure
terraform init
terraform plan
terraform apply

# Frontend (after terraform apply outputs the S3 bucket name)
aws s3 sync src/frontend/ s3://$(terraform output -raw frontend_s3_bucket_name) --exclude "*.js" --exclude "*.html"
aws s3 sync src/frontend/ s3://$(terraform output -raw frontend_s3_bucket_name) --exclude "*" --include "*.html" --content-type "text/html"
aws s3 sync src/frontend/js/ s3://$(terraform output -raw frontend_s3_bucket_name)/js/ --content-type "application/javascript"

# Invalidate CloudFront cache
aws cloudfront create-invalidation --distribution-id $(terraform output -raw cloudfront_url | sed 's|https://||' | sed 's|/.*||') --paths "/*"
```

Requires Terraform >= 1.5.0, Python 3.12, AWS CLI configured with active credentials, and a deployed Cognito User Pool.

## Author

**Daniel Villegas**
Cloud Engineer | AWS Certified (4x)
[LinkedIn](https://www.linkedin.com/in/vdaniel07) · [GitHub](https://github.com/DevDan7)
