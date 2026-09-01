# Changelog — AI Mentoring

> Log cronológico consolidado de cambios significativos del proyecto. Orden: más reciente primero.

---

## 2026-09

### 01 Sep — Fase 7c: Historial de quizzes + fixes críticos

#### Features
- Nuevo endpoint `GET /students/me/quizzes` para historial de simulados
- Sección "Histórico de Simulados" en dashboard con tabla de resultados
- Cálculo y almacenamiento de `ScorePercentage` al completar quizzes
- IAM: permiso `Query` sobre tabla Quizzes para Lambda `student_api`

#### Bugs corregidos
- `QUIZZES_TABLE` faltante en variables de entorno de Lambda `student_api`
- `Float` no soportado por DynamoDB → convertido a `Decimal`
- `Decimal` no serializable por JSON → convertido a `float` en respuestas
- Amplify IAM trust policy con `Condition` demasiado restrictiva → eliminada

#### Archivos modificados
- `src/quiz_engine.py`: score calculation + Decimal/Float handling
- `src/student_api.py`: quiz history endpoint + Decimal/Float handling
- `src/frontend/dashboard.html`: sección historial
- `src/frontend/js/api.js`: función `getQuizHistory()`
- `iam_student_api.tf`: permiso Quizzes
- `iam.tf`: Amplify role trust policy
- `api_gateway_routes.tf`: nueva ruta
- `lambda_student_api.tf`: variable `QUIZZES_TABLE`

#### PRs
- #57: fix: convert score_percentage to Decimal for DynamoDB compatibility
- #58: fix: remove SourceArn condition from Amplify IAM trust policy

---

## 2026-08

### 30 Ago — Fix visualización de perfil y cohorte en dashboard
- Corregido `ensureStudentProfile()` para retornar perfil completo después de crear
- Corregido `dashboard.html` para leer `CohortID` en vez de `Cohort`
- Bug: Email, StudentID y Cohort mostraban `undefined`/`Sem turma` para alumnos nuevos
- PR #49

### 29 Ago — Gestión de cohortes
- Nueva tabla DynamoDB `Cohorts` con `CohortID` como PK (PR #47)
- GSI `CohortIndex` en tabla `Students` para buscar alumnos por cohorte
- `student_api.py`: validación de existencia de cohorte antes de crear/actualizar alumno
- Frontend: enrollment automático vía parámetro URL `?turma=<cohort_id>`
- IAM: permisos de lectura para `Cohorts` table en `student_api`

### 29 Ago — Reorganización de documentación
- Creados 4 archivos temáticos: `DOCUMENTATION.md`, `architecture.md`, `technical-log.md`, `changelog.md`
- Eliminado `status.md` (migración completa a estructura temática)
- Eliminados dashboards HTML temporales: `dashboard.html`, `quiz-results-dashboard.html`
- Agentes OpenCode actualizados: `git.md` (DevOps workflow), `aws-tutor.md` (nuevo subagente)

### 28 Ago — Flujo de autenticación completo
- Implementación completa: SignUp, confirmación, forgot password, auto-creación de perfil (PR #44)
- Localización completa a Portugués Brasil (pt-BR)
- Archivos: `auth.js`, `index.html`, `api.js`, `dashboard.html`

### 28 Ago — Fix CI/CD y workflow
- Agregada variable `TF_VAR_gh_repository` en `terraform-apply.yml`
- Workflow `terraform-plan.yml` actualizado para soporte de Amplify Hosting

### 28 Ago — Auto-registro de alumnos
- Implementación completa de Option B (PR #45)
- Archivos: `auth.js`, `index.html`, `api.js`, `dashboard.html`
- Funcionalidades: SignUp, confirmación, forgot password, auto-creación de perfil
- Traducción: Interfaz completa a Portugués Brasil (pt-BR)

### 27 Ago — Fix permisos IAM para CI/CD
- Sincronizados permisos de `terraform-cicd-policy` con AWS
- Agregados: `iam:CreatePolicyVersion`, `iam:DeletePolicy`
- Agregados permisos `cloudfront:*` y `amplify:*` para migración frontend

### 27 Ago — Migración Frontend a Amplify Hosting
- Creados recursos Terraform: `amplify.tf` con `aws_amplify_app.frontend` + `aws_amplify_branch.main`
- IAM Service Role: `mentoring-amplify-role` con least privilege
- Segunda ocurrencia del problema huevo/gallina IAM — resuelta con CLI manual
- PR #39 y #40 mergeados
- **Nota**: `landing.tf` eliminado, recursos S3+CloudFront legacy en `frontend.tf` (comentario residual)

### 26 Ago — Fix drift IAM
- Agregado `aws_iam_role_policy_attachment.github_actions_readonly` en `iam.tf`
- Adjuntar `ReadOnlyAccess` al rol `ai-mentoring-github-actions`
- Drift entre código y estado real en AWS eliminado
- PR #37

### 25 Ago — Reestructuración de configuración OpenCode
- Agente `git.md` creado (generador de comandos git, solo lectura)
- Agente `developer.md` eliminado
- Agentes `reviewer.md` y comando `review.md` traducidos al español
- Comandos obsoletos eliminados: `document.md`, `implement.md`, `plan.md`, `test.md`, `prompts.md`
- Comando `infra-eval.md` renombrado a `infra-review.md`
- Skill `testing/SKILL.md` simplificado
- `AGENTS.md` actualizado con sección "Skills Update"
- `opencode.json` actualizado con agentes `plan` y `git`

### 24 Ago — CI/CD con `terraform apply` automatizado
- GitHub Actions ejecuta `apply` en push a `main` con gate de aprobación manual
- Backend remoto S3 + `use_lockfile = true` (resolución del hallazgo #5)
- Bucket S3: `daniel-mentoring-terraform-state-853106001369`
- **Incidente**: Scope creep de agente IA durante `/implement` (24 archivos modificados sin solicitud)
- **Incidente**: Drift de permisos IAM (`ReadOnlyAccess` desadjuntado)
- PR #33

### 24 Ago — Evaluación Rekognition vs Textract
- Script de comparación aislado (`scripts/test_ocr_comparison.py`)
- Probado contra 5 fotos reales
- Resultado: calidad equivalente, parsing más complejo en Textract
- Decisión: mantener Rekognition
- **Nota**: Script en rama `test/ocr-comparison-textract`, no en main

### 22 Ago — Blindaje de taxonomía en processor.py
- Constante `CANONICAL_TOPICS` con 10 categorías funcionales
- Prompt de Bedrock reescrito con mapeo explícito
- Validación defensiva post-Bedrock: topic no válido → "General / Otros Servicios"
- Pipeline blindado a futuras inserciones fuera de taxonomía

### 22 Ago — Normalización de tópicos
- 109 ítems normalizados de ~84 tópicos fragmentados a 10 categorías canónicas
- Script de migración: `scripts/normalizar_temas.py` con `scripts/mapa_temas.json`
- Respaldo pre-migración generado
- Valor original preservado en `OriginalTopic`

### 21 Ago — Landing Page con S3 + CloudFront
- 4 páginas HTML + 3 módulos JS
- S3 bucket `ai-mentoring-frontend-*` + CloudFront distribution
- Bug fix: `quiz_engine.py` campo `Statement` → `QuestionText`
- PR #16

### 21 Ago — API Gateway HTTP API
- JWT Authorizer con Cognito User Pool
- 7 rutas protegidas
- Throttling: 50 rps / burst 100
- Lambdas adaptadas a formato API Gateway v2.0
- Error IAM resuelto: `submit_answer` necesitaba `dynamodb:GetItem`

### 21 Ago — Lambda student_api.py
- CRUD completo: create, get, update, get_by_email
- Validación de tokens Cognito
- 5/5 tests pasados
- Archivos: `src/student_api.py`, `lambda_student_api.tf`, `iam_student_api.tf`

### 21 Ago — Lambda quiz_engine.py
- 3 acciones: generate_quiz, submit_answer, get_results
- Soporte Multiple Choice (sets en DynamoDB)
- Test exitoso: topic "AWS Well-Architected Framework", 3 preguntas
- PR #16

### 18 Ago — Modelo de datos (3 tablas DynamoDB)
- Students (StudentID PK, EmailIndex GSI)
- Quizzes (QuizID PK, StudentIndex GSI)
- QuizResults (ResultID PK, QuizIndex + StudentIndex GSIs)
- Error de `Unused attributes` resuelto (solo PK/SK/GSI en bloque `attribute`)
- PR #14

### 17 Ago — Solución de concurrencia
- `scaling_config.maximum_concurrency = 3` en SQS ESM
- Reemplazó intento fallido de `reserved_concurrent_executions`
- Lote 3: 100% éxito, DLQ=0, Throttling=2

### 17 Ago — Error de concurrencia
- `reserved_concurrent_executions = 3` causó error
- Cuenta tiene límite de 10 concurrent executions
- Pool no reservado bajaba a 7 (< mínimo de 10)

### 16 Ago — Botocore adaptive retry
- `max_attempts=6`, `mode='adaptive'`
- Tasa de éxito: 73.4% → 100%
- DLQ: 30 → 5
- Throttling: 290 → 92
- Trade-off: duración promedio de 7.7s → 18.9s
- PR #11

### 15 Ago — Revert memory_size a 256 MB
- 512 MB no mejoró desempeño (memoria pico ~105 MB en ambos)
- Costo se duplicaba sin beneficio
- PR #8

### 15 Ago — Lote 1 de fotos (109 fotos)
- 80 items DynamoDB (73.4%), 30 en DLQ
- 290 ThrottlingException
- Tabla `MentoringQuestions` vaciada para eliminar formatos heredados

### 13 Ago — Idempotencia en processor.py
- QuestionID derivado del eTag S3
- ConditionExpression para evitar duplicados
- ConditionalCheckFailedException capturada y omitida
- **Limitación**: multipart upload genera eTag compuesto

### 13 Ago — Prueba de desempeño 512 MB
- Línea base: 256 MB, duración 3-4s, pico 8.8s
- Comparación: 512 MB no mejoró, memoria pico idéntica

### 12 Ago — Rediseño de prompt Bedrock
- Estructura en inglés con opciones A–F
- Campos: `topic`, `question_text`, `question_type`, `correct_count`, `options`
- DynamoDB actualizado a nuevos campos

### 11 Ago — Notificación SNS por email
- Tópico `AI-Mentoring-notifications-dev-daniel`
- Suscripción email con variable `notification_email` (sensible)
- Política de tópico restringida por `SourceArn`

### 11 Ago — Consolidación IAM
- Statement duplicado `AllowIAAnalysis`/`AllowBedrockInvokeModel` consolidado
- Bloque OIDC movido de `main.tf` a `iam.tf`
- Creado `variables.tf` con variables no sensibles

### 11 Ago — Configuración OpenCode
- Agentes: `architect`, `developer`, `reviewer`
- Skills: `ai-mentoring-architecture`, `aws-serverless`, `python-lambda`, `testing`
- Comandos: `plan`, `implement`, `test`, `review`, `document`
- Reglas: `architecture`, `aws`, `python`, `security`

### 08 Ago — GitHub Actions con OIDC
- `terraform-plan.yml` funcionando con autenticación OIDC
- Sin credenciales de larga duración en GitHub

### 07 Ago — Primer push a GitHub
- Repo: `DevDan7/AI_Mentoring`
- Lambda vacía eliminada
- README reescrito
- `.gitignore` actualizado (`.venv`, `.terraform`)

---

## 2026-07

### 18 Ago — Análisis inicial del proyecto
- Arquitectura event-driven serverless identificada
- Pipeline: S3 → SNS → SQS → Lambda → Rekognition → Bedrock → DynamoDB
- 11 hallazgos de deuda técnica documentados
- Roadmap definido

---

## Notas

### Archivos de Referencia
- `scripts/test_ocr_comparison.py` — En rama `test/ocr-comparison-textract`, no en main
- Archivos ZIP en raíz — Artefactos de build generados por Terraform (en `.gitignore`)
- `.opencode/node_modules/` — Excluido via `.opencode/.gitignore`

### Items Resueltos
- **Hallazgo #5**: Backend remoto S3 + locking (2026-08-24)
- **Hallazgo #9**: Drift IAM ReadOnlyAccess (2026-08-26)
- **Item 5 "Próximos pasos"**: Migración Frontend a Amplify (2026-08-27)
- **Item 6 "Próximos pasos"**: Auto-registro de alumnos (2026-08-28)
- **Item 7 "Próximos pasos"**: Gestión de cohortes (2026-08-29)
