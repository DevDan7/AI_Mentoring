# Changelog — AI Mentoring

> Log cronológico consolidado de cambios significativos del proyecto. Orden: más reciente primero.

---

## 2026-09

### 03 Sep — Validación de Cupo + Bug Fix + Limpieza

#### Agregado
- Endpoint público `GET /public/cohorts/{cohortId}/capacity` para validar cupo antes del registro
- Frontend valida cupo ANTES de registrar en Cognito (muestra "Turma lotada" si está llena)
- Turma real `BRSAO251/G3` recreada en DynamoDB (7 cupos)

#### Corregido
- **Decimal is not JSON serializable**: `MaxStudents` de DynamoDB viene como `Decimal`, corregido con `int()` en `get_cohort_capacity()`
- **apiCall() redirige durante registro**: `checkCohortCapacity()` usaba `apiCall()` que requería token. Usuario sin token → `logout()` → redirigía a index.html. Corregido con endpoint público sin auth
- **Formulario de confirmación no aparecía**: Debido al bug anterior, `signUp()` se ejecutaba pero `confirmForm` no se mostraba

#### Limpieza
- Eliminados 4 usuarios de prueba de Cognito (cupo1, cupo4, cupo5, cupo6)
- Eliminados 3 perfiles de prueba de DynamoDB
- Eliminada turma de prueba `TEST-CUPO-01`
- Recreada turma real `BRSAO251/G3` con MaxStudents=7

#### Archivos Modificados
- `src/student_api.py`: Ruta pública + fix Decimal
- `api_gateway_routes.tf`: Ruta `GET /public/cohorts/{cohortId}/capacity`
- `src/frontend/js/api.js`: Función `checkCohortCapacityPublic()`
- `src/frontend/index.html`: Usa función pública para validar cupo

### 02 Sep — Poblar ContentHash en el banco existente (98 preguntas)
- Nuevo `scripts/poblar_content_hash.py`: calcula el `ContentHash` con la MISMA funcion
  `content_hash()` de `src/processor.py` y lo anade a los items de `MentoringQuestions`
- Ejecutado contra las preguntas existentes: 98 actualizados, 0 errores, backup previo en
  `scripts/backup_pre_hash_20260903_100917.json`
- Tras el update: 0 items sin hash, 98 hashes unicos, 0 colisiones (preguntas todas distintas)
- Auditoria de duplicados por contenido re-ejecutada: 0 grupos
- Resultado: la dedupe por contenido queda activa contra TODO el banco (existente + futuras),
  de modo que las ~200 fotos nuevas que se suban no duplicaran las preguntas ya existentes

### 02 Sep — Dedupe por contenido + alerta SNS para imágenes no procesables
- `processor.py`: nuevo campo `ContentHash` (SHA-256 del enunciado normalizado: minúsculas,
  sin tildes, espacios ni puntuación) en cada registro de `MentoringQuestions`
- `ConditionExpression` ampliada a doble condición:
  `attribute_not_exists(QuestionID) AND attribute_not_exists(ContentHash)`
  - `QuestionID` → evita duplicar si vuelve la misma foto (eTag)
  - `ContentHash` → evita duplicar si otra foto trae la misma pregunta (contenido)
- Tras este cambio, una misma pregunta subida en 2+ fotos distintas solo se guarda una vez
  (la primera); las siguientes se omiten como "Duplicado detectado"
- Imágenes no procesables (respuesta no JSON o sin pregunta/opciones): ya no se pierden en
  silencio — se publica una alerta SNS (email) con la clave del archivo y el motivo
- `iam.tf`: nuevo statement `AllowPublishNotifications` (`sns:Publish`) scoped al ARN del topic
- `lambda.tf`: nueva variable de entorno `SNS_TOPIC_ARN` en el processor
- Tests ampliados a 10 casos (`tests/test_processor_multimodal.py`): hash estable, hash que
  ignora mayúsculas/tildes, publicación SNS, no-publicación sin ARN, dedupe por contenido
- Sin GSI: la condición `attribute_not_exists(ContentHash)` funciona sin índice (menor costo,
  sin infraestructura adicional)

### 02 Sep — Migración a Bedrock multimodal (sin Rekognition)
- `processor.py`: eliminada la dependencia de Rekognition `DetectText` (OCR)
- La Lambda ahora lee la imagen de S3 (`s3:get_object`), la codifica en base64 y
  la envía a Bedrock como bloque de imagen multimodal junto al prompt de texto
- Prompt reescrito para modo imagen: analiza enunciado, opciones A–F y
  diagramas/tablas; mantiene el mapeo a las 10 categorías canónicas
- `media_type` inferido de la extensión del archivo (PNG → `image/png`, resto → `image/jpeg`)
- Manejo de fallos: respuesta no JSON o sin pregunta/opciones → se descarta con log
  en CloudWatch (`continue`, sin excepción, sin DLQ)
- `iam.tf`: retirado `rekognition:DetectText` del rol de la Lambda
  (`s3:GetObject` ya existía y cubre la lectura de imagen)
- `lambda.tf`: timeout del processor de 30s → 60s (margen para inferencia multimodal);
  `max_tokens` de Bedrock subido de 1000 → 1500
- Tests creados: `tests/test_processor_multimodal.py` (5 casos, stdlib `unittest.mock`)
- Documentación: `doc/architecture.md` actualizada (pipeline, servicios, decisión de diseño)
- Eliminado un componente del pipeline (costo y dependencia menos)

### 02 Sep — Deduplicación por contenido + limpieza de duplicados
- Auditoría directa sobre tabla `MentoringQuestions` (`scripts/detectar_duplicados_contenido.py`):
  comparación por contenido (`QuestionText` normalizado: minúsculas, sin acentos,
  sin puntuación) → criterio "solo idénticas exactas"
- Resultado: 110 ítems, 11 grupos duplicados, 13 candidatos a eliminar, 97 únicos
- Verificado que la deduplicación por eTag (archivo) no detecta duplicados de contenido:
  misma pregunta en fotos distintas entraba por separado
- Limpieza aplicada (`scripts/limpiar_duplicados_contenido.py --apply`): 13 eliminados, 0 errores
- Backups previos: `scripts/backup_pre_limpieza_20260902_130900.json` (110 ítems)
- Validación final: 97 ítems, 0 grupos duplicados por contenido
- Nota: 2 de los 13 eliminados estaban referenciados en quizzes de un alumno de TEST
  (a eliminar); por decisión se limpiaron igualmente
- Pendiente (Fase 3): deduplicación preventiva por contenido en `processor.py` (hash
  del enunciado de Bedrock) para que las próximas fotos no reintroduzcan duplicados

### 01 Sep — Fix trust policy de Amplify (huevo-gallina IAM #3)
- `iam.tf`: `amplify_role` — condición `ArnLike` reemplazada por
  `ArnLikeIfExists` sobre `aws:SourceArn` (Amplify no siempre envía esa
  clave; la condición estricta bloqueaba builds legítimos)
- `iam.tf`: `terraform_cicd_policy` — agregado `iam:UpdateAssumeRolePolicy`
  (permiso distinto de `iam:UpdateRole`, necesario para tocar trust
  policies vía CI/CD)
- Apply aplicado localmente (bootstrap manual, mismo patrón que las 2
  ocurrencias anteriores del problema huevo-gallina), verificado con
  `terraform plan` limpio en el PR antes de mergear
- Build de Amplify verificado exitoso tras el fix
- Deuda técnica anotada (sin resolver hoy): drift crónico en
  `aws_amplify_app.frontend.repository` (mayúsculas/`.git`) y hash de
  Lambdas que cambia en cada corrida de CI por timestamps de `git checkout`

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

### 01 Sep — Bloque 1: Protecciones básicas para Beta

#### Features
- Validación de `MaxStudents` en `create_student()` — rechaza si turma está llena
- Campo `AccessExpiresAt` en Students (CreatedAt + 30 días por defecto)
- Check de expiración en `get_student()`, `generate_quiz()` y `submit_answer()`
- `iam.tf`: Agregado `dynamodb:GetItem` sobre Students para `quiz_engine`

#### Archivos modificados
- `src/student_api.py`: MaxStudents validation, AccessExpiresAt creation + check
- `src/quiz_engine.py`: Función `check_student_access()`, checks en generate/submit
- `iam.tf`: GetItem sobre Students en quiz_engine_policy

#### Turma Real Creada
- CohortID: `BRSAO251/G3`
- MaxStudents: 7
- Período: 01/09/2026 - 29/09/2026
- Link: `https://main.d1jhem8rxt5h6t.amplifyapp.com/?turma=BRSAO251/G3`

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
