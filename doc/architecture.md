# Arquitectura — AI Mentoring

> Plataforma event-driven serverless en AWS para convertir fotos de preguntas de examen en un banco de preguntas estructurado para mentoring de certificaciones AWS.

---

## Pipeline Funcional

```
S3 (foto examen) → S3 Event → SNS (notificaciones + email)
   └──→ SQS (main_queue, max_concurrency=3) → Lambda (processor.py)
           → Rekognition (OCR) → Bedrock (Claude Haiku 4.5) → DynamoDB
```

### Flujo Detallado

1. **S3** recibe una foto de pregunta de examen (`daniel-mentoring-exam-photos-edn-dev`)
2. **S3 Event** dispara notificación a **SQS** (vía SNS para notificación por email)
3. **SQS** encola el mensaje con DLQ (`maxReceiveCount=4`) y control de concurrencia (`maximum_concurrency=3`)
4. **Lambda `processor.py`** procesa la foto:
   - **Rekognition** extrae texto (OCR)
   - **Bedrock Claude Haiku 4.5** clasifica y estructura la pregunta en JSON
   - Validación de taxonomía canónica (10 categorías)
   - **DynamoDB** almacena el registro (`PutItem` con idempotencia)

---

## Servicios AWS

### S3 — Bucket de Fotos

- **Bucket**: `daniel-mentoring-exam-photos-edn-dev`
- **Propósito**: Recibe fotos de preguntas de examen
- **Notificación**: SQS (para pipeline) + SNS (para email)
- **Nota**: Solo un `aws_s3_bucket_notification` por bucket (restricción de AWS)

### SQS — Cola de Ingesta

- **Cola principal**: `mentoring-main-queue`
- **DLQ**: `mentoring-dlq` (`maxReceiveCount=4`)
- **Control de concurrencia**: `scaling_config.maximum_concurrency = 3` en Event Source Mapping
- **Política**: Restricta por `aws:SourceArn` al bucket S3

### SNS — Notificaciones

- **Tópico**: `AI-Mentoring-notifications-dev-daniel`
- **Suscripción**: Email (variable `notification_email`)
- **Política**: Restringida por `aws:SourceArn` al bucket S3

### Lambda — Functions

| Lambda | Archivo | Propósito | Memoria | Timeout |
|--------|---------|-----------|---------|---------|
| `mentoring-exam-processor` | `processor.py` | OCR + Bedrock + DynamoDB | 256 MB | 30s |
| `student-api` | `student_api.py` | CRUD de estudiantes | 256 MB | 30s |
| `quiz-engine` | `quiz_engine.py` | Quizzes y resultados | 256 MB | 30s |

**Configuración común:**
- Python 3.12
- Boto3 inicializado a nivel de módulo
- Variables de entorno con `os.environ.get()`
- `botocore adaptive retry` en `processor.py` (max_attempts=6)

### DynamoDB — Tablas

| Tabla | PK | GSIs | Propósito |
|-------|-----|------|-----------|
| `MentoringQuestions` | `QuestionID` | `TopicIndex` (Topic) | Banco de preguntas |
| `Students` | `StudentID` | `EmailIndex` (Email), `CohortIndex` (CohortID) | Perfiles de alumnos |
| `Quizzes` | `QuizID` | `StudentIndex` (StudentID) | Simulados generados |
| `QuizResults` | `ResultID` | `QuizIndex` (QuizID), `StudentIndex` (StudentID + Timestamp) | Respuestas y resultados |
| `Cohorts` | `CohortID` | — | Gestión de cohortes |

**Configuración común:**
- `PAY_PER_REQUEST` (sin capacidad provisionada)
- Schema mínimo en Terraform (solo PK + GSIs)
- Campos adicionales creados dinámicamente con `put_item`

### Bedrock — Claude Haiku 4.5

- **Modelo**: `us.anthropic.claude-haiku-4-5-20251001-v1:0`
- **Propósito**: Clasificar y estructurar preguntas de examen
- **Prompt**: Instrucciones en inglés para mapear a 10 categorías canónicas
- **Respuesta**: JSON estructurado con `topic`, `question_text`, `question_type`, `correct_count`, `options`

### Rekognition — OCR

- **Operación**: `DetectText`
- **Propósito**: Extraer texto de fotos de preguntas
- **Alternativa evaluada**: Textract (descartada, ver Conocimiento del Proyecto)

### API Gateway — HTTP API

- **Tipo**: HTTP API v2
- **Autenticación**: JWT Authorizer (Cognito User Pool)
- **Throttling**: 50 rps rate limit, 100 burst
- **CloudWatch**: Logs habilitados

**Rutas:**

| Método | Ruta | Lambda | Descripción |
|--------|------|--------|-------------|
| POST | `/students` | student_api | Crear alumno |
| GET | `/students/me` | student_api | Obtener perfil propio |
| PUT | `/students/me` | student_api | Actualizar perfil propio |
| GET | `/students/{studentId}` | student_api | Obtener alumno por ID |
| POST | `/quizzes/generate` | quiz_engine | Generar simulado |
| POST | `/quizzes/submit` | quiz_engine | Registrar respuesta |
| GET | `/quizzes/{quizId}/results` | quiz_engine | Obtener resultados |

### Cognito — Autenticación

- **User Pool**: `us-east-1_YolmrF9tp`
- **Username**: Email
- **Password policy**: 8+ caracteres, 1 mayúscula, 1 número
- **Auth flows**: SRP, User Password
- **App Client**: Configurado para frontend

### Amplify — Hosting Frontend

- **App ID**: `d1jhem8rxt5h6t`
- **Dominio**: `main.d1jhem8rxt5h6t.amplifyapp.com`
- **Branch**: `main`
- **Service Role**: `mentoring-amplify-role` (least privilege)

### IAM — Roles y Políticas

| Rol | Propósito | Permisos |
|-----|-----------|----------|
| `mentoring-lambda-processor` | Ejecutar `processor.py` | Rekognition, Bedrock, DynamoDB, SNS, SQS, CloudWatch |
| `mentoring-lambda-student-api` | Ejecutar `student_api.py` | DynamoDB (Students, Cohorts), Cognito GetUser |
| `mentoring-lambda-quiz-engine` | Ejecutar `quiz_engine.py` | DynamoDB (todas las tablas), Cognito GetUser |
| `ai-mentoring-github-actions` | CI/CD con OIDC | `ReadOnlyAccess` + `terraform-cicd-policy` |
| `mentoring-amplify-role` | Amplify Hosting | Logs (CloudWatch) |

### CloudFront — CDN (Legacy)

- **Distribution**: `d2dsobmtfi3ppb.cloudfront.net`
- **Estado**: Pendiente de eliminación (reemplazado por Amplify)
- **Origen**: S3 bucket frontend (legacy)

---

## Modelo de Datos

### MentoringQuestions

```
QuestionID (PK)    | Topic | QuestionText | QuestionType | CorrectCount | Options | OriginalTopic
```

- **Topic**: Una de 10 categorías canónicas (ver Conocimiento del Proyecto)
- **Options**: Lista de objetos con `text`, `is_correct`, `explanation`, `keywords`
- **OriginalTopic**: Valor original antes de normalización (preservado para auditoría)

### Students

```
StudentID (PK) | Email | Name | CreatedAt | SessionExpiresAt | CohortID | TopicsWeak[] | TotalQuizzes | AvgScore
```

- **GSI EmailIndex**: Permite buscar por email
- **GSI CohortIndex**: Permite buscar alumnos por cohorte
- **CohortID**: Referencia a tabla `Cohorts` (enrollment vía URL `?turma=<id>`)

### Quizzes

```
QuizID (PK) | StudentID | Topic | Difficulty | QuestionCount | Score | Status | CreatedAt
```

- **GSI StudentIndex**: Permite ver todos los quizzes de un alumno
- **Status**: `in_progress` | `completed`

### QuizResults

```
ResultID (PK) | QuizID | StudentID | QuestionID | GivenAnswer | IsCorrect | Timestamp
```

- **GSI QuizIndex**: Ver todas las respuestas de un quiz
- **GSI StudentIndex**: Ver historial cronológico de un alumno

### Cohorts

```
CohortID (PK) | Name | CreatedAt | MaxStudents | Active
```

- **Propósito**: Gestión de cohortes para mentoría grupal
- **Enrollment**: Estudiantes se unen vía URL con parámetro `?turma=<cohort_id>`
- **Validación**: `student_api.py` verifica existencia de cohorte antes de crear/actualizar perfil

---

## Conocimiento del Proyecto

### ¿Por qué Rekognition en vez de Textract?

**Decisión**: Se evaluó migrar de Rekognition a Textract (2026-08-24). Resultado: mantener Rekognition.

**Razones:**
1. **Calidad equivalente**: Para texto impreso claro (tipo de imagen que procesa este proyecto), ambos servicios tienen calidad similar
2. **Complejidad de parsing**: Rekognition devuelve lista plana (`LINE`/`WORD`); Textract requiere reconstruir orden navegando `Relationships` entre bloques — notablemente más complejo
3. **Costo**: Diferencia imperceptible al volumen actual (~$0.001/pregunta)
4. **Suficiencia**: Rekognition cumple con los requisitos actuales del proyecto

**Conclusión**: La refactorización de `processor.py` que exigiría Textract no se justifica sin un problema real de calidad de OCR. Textract queda evaluado y descartado; se reconsiderará si se necesita procesar documentos complejos (tablas, formularios, multi-columna).

### ¿Por qué 10 categorías canónicas?

**Problema original**: El prompt de Bedrock usaba clasificación de texto libre, generando ~84 tópicos fragmentados para 109 preguntas.

**Solución**: Taxonomía cerrada con 10 categorías funcionales basadas en las áreas de conocimiento de las certificaciones AWS:

1. Cloud Concepts & Well-Architected
2. Security, Identity & Compliance
3. Compute & Containers
4. Storage & Database
5. Networking & Content Delivery
6. Data, Analytics & Machine Learning
7. Management, Governance & DevOps
8. Billing, Cost Management & Support
9. Application Integration & Serverless Architecture
10. General / Otros Servicios

**Implementación**:
- Constante `CANONICAL_TOPICS` en `processor.py`
- Prompt de Bedrock con instrucciones explícitas de mapeo
- Validación defensiva post-Bedrock: topic no válido → reasigna a "General / Otros Servicios"

**Resultado**: 109 preguntas normalizadas a 10 categorías. Pipeline blindado a futuras inserciones fuera de la taxonomía.

### ¿Por qué `scaling_config.maximum_concurrency` en vez de `reserved_concurrent_executions`?

**Problema**: La cuenta AWS tiene límite de 10 concurrent executions (tier gratuito). `reserved_concurrent_executions` en la Lambda reduce el pool no reservado por debajo del mínimo de 10, causando error.

**Error exacto**:
```
InvalidParameterValueException: Specified ReservedConcurrentExecutions for function 
decreases account's UnreservedConcurrentExecution below its minimum value of [10].
```

**Solución**: `scaling_config.maximum_concurrency = 3` en el Event Source Mapping de SQS.

**Ventajas:**
- No toca el pool de concurrencia de la cuenta
- Controla solo invocaciones del SQS (no afecta otras funciones)
- No causa throttling

**Resultado**: Máximo 3 instancias Lambda en paralelo, controlando el throttling de Bedrock sin necesitar aumento de límite de cuenta.

### ¿Por qué backend remoto S3 + `use_lockfile`?

**Problema original**: `terraform.tfstate` vivía solo en la máquina local. GitHub Actions (máquina limpia en cada ejecución) no tenía acceso al estado, causando errores `ResourceInUseException` al intentar recrear recursos existentes.

**Solución**:
- Bucket S3 (`daniel-mentoring-terraform-state-853106001369`) con versionado
- Migración vía `terraform init -reconfigure`
- Bloqueo nativo con `use_lockfile = true` (Terraform 1.11+)

**¿Por qué no DynamoDB locking?** La tabla DynamoDB tradicional para locking es una pieza extra de infraestructura. `use_lockfile` es más simple y nativo.

### ¿Por qué botocore adaptive retry con 6 intentos?

**Problema**: Las ráfagas de fotos saturan el rate limit de Bedrock, generando `ThrottlingException`. Sin reintentos, los mensajes fallidos van a DLQ.

**Solución**: `botocore.Config` con `retries={'max_attempts': 6, 'mode': 'adaptive'}`

**Resultado**: Tasa de éxito mejoró de 73.4% a 100% (109/109 fotos). ThrottlingException reducidos de 290 a 92.

**Trade-off**: Duración promedio aumentó de 7.7s a 18.9s (reintentos consumen tiempo). Algunas invocaciones alcanzan timeout de 30s.

**Pendiente**: Evaluar reducir `max_attempts` a 3-4 para balancear éxito vs duración.

### Patrón recurrente: Huevo y Gallina en IAM

**Problema**: El proyecto ha enfrentado **dos veces** el mismo problema de dependencia circular en permisos IAM durante la automatización CI/CD:

1. **2026-08-24**: El rol `ai-mentoring-github-actions` no podía ejecutar `terraform apply` para crear `terraform-cicd-policy` porque esa política le daría permisos de escritura que no tenía aún.

2. **2026-08-27**: Al agregar permisos `cloudfront:*` y `amplify:*` a `terraform-cicd-policy`, Terraform necesitaba `iam:CreatePolicyVersion` para actualizar el body de la política, pero ese permiso no existía en la política.

**Causa raíz**: Terraform gestiona políticas IAM como recursos. Para actualizar una política existente, necesita `iam:CreatePolicyVersion`. Pero si la política no tiene ese permiso, Terraform no puede modificarse a sí mismo.

```
Política IAM (sin CreatePolicyVersion)
    └── Terraform intenta actualizar
        └── Necesita CreatePolicyVersion
            └── No existe en la política
                └── Error: AccessDenied
```

**Solución estándar** (para cualquier cambio de permisos en `terraform-cicd-policy`):

1. **CLI manual** con credenciales de admin para actualizar la política
2. **Sincronizar `iam.tf`** para reflejar los cambios hechos en AWS
3. **Terraform plan local** para verificar 0 cambios (sin drift)
4. **Commit y push** para que GitHub Actions pueda ejecutar sin errores

**Prevención**: Incluir `iam:CreatePolicyVersion` y `iam:DeletePolicy` en `terraform-cicd-policy` desde el inicio (agregados 2026-08-27).

### Estado vs Objetivo

El objetivo del proyecto tiene 3 piezas:

1. **Base de datos de alumnos** — Perfil, progreso, temas débiles
2. **Generación de aulas desde un banco de simulados** — Quizzes personalizados
3. **Relatorios** — Reportes de progreso por alumno

**Estado actual:**

| Pieza | Estado |
|-------|--------|
| BD de alumnos | ✅ `Students` table + `student_api.py` |
| Banco de preguntas | ✅ `MentoringQuestions` + pipeline de ingesta |
| Generación de quizzes | ✅ `quiz_engine.py` (generate_quiz, submit_answer, get_results) |
| Gestión de cohortes | ✅ `Cohorts` table + enrollment vía URL |
| Relatorios | ⚠️ Parcial — métricas en `get_results`, sin generación automatizada de reportes |

**Próximos pasos (roadmap ejecutivo):**

| # | Tarea | Estado |
|---|-------|--------|
| 1 | ~~Limpiar deuda técnica rápida~~ | ✅ Hecho (2026-08-07) |
| 2 | ~~Configurar GitHub Actions con OIDC~~ | ✅ Hecho (2026-08-08) |
| 3 | ~~Diseñar modelo de datos~~ | ✅ Hecho (2026-08-18) |
| 4 | ~~CI/CD con apply~~ | ✅ Hecho (2026-08-24) |
| 5 | ~~Migración Frontend a Amplify~~ | ✅ Hecho (2026-08-27) |
| 6 | ~~Auto-registro de alumnos~~ | ✅ Hecho (2026-08-28) |
| 7 | ~~Gestión de cohortes~~ | ✅ Hecho (2026-08-29) |
| 8 | Refactor: AWS Step Functions para orquestación asíncrona | ⏳ Pendiente |
| 9 | Cleanup: avisos de depreciación (`key_schema` vs `hash_key`) | ⏳ Evaluado, mantenido (bug del proveedor AWS) |
| 10 | Generación automatizada de relatorios | ⏳ Pendiente |

---

## Decisiones de Diseño

### Idempotencia en `processor.py`

- **QuestionID** se deriva del `eTag` del objeto S3 (MD5 del contenido)
- Fallback a `uuid.uuid4()` si no viene eTag
- `put_item` con `ConditionExpression='attribute_not_exists(QuestionID)'`
- `ConditionalCheckFailedException` capturada y omitida (duplicado)

**Limitación**: En multipart upload el eTag es `hex-N` (depende del nº de partes), así que una misma foto subida por PUT simple vs multipart no se deduplica entre sí.

### Schema Mínimo en DynamoDB

Terraform solo declara atributos que son PK, SK o están en un GSI. Los demás campos se crean dinámicamente con `put_item` desde Python.

**Razón**: DynamoDB/Terraform rechaza atributos definidos en el bloque `attribute` que no son keys ni indexados.

### Least Privilege en IAM

- Cada Lambda tiene su propio rol con permisos acotados
- Third-party event services (SQS, SNS) restringidos con `aws:SourceArn`
- GitHub Actions: `ReadOnlyAccess` + `terraform-cicd-policy` (escritura acotada)

### Secrets en `.tfvars`

- Valores sensibles (email, tokens) en `terraform.tfvars` (excluido de git)
- `notification_email` marcada como `sensitive = true` en `variables.tf`
- Configuración no sensible puede tener `default` en `variables.tf`

---

## Infraestructura como Código

### Terraform

- **Versión Provider AWS**: `~> 6.0`
- **Versión Provider Archive**: `~> 2.4`
- **Archivos**: 19 archivos `.tf` en raíz del proyecto
- **Backend**: S3 con `use_lockfile = true`

### CI/CD

- **GitHub Actions**: OIDC con rol `ai-mentoring-github-actions`
- **Flujo**: PR → `terraform plan` automático → merge a `main` → `terraform apply` con aprobación manual
- **Entorno**: `production` con required reviewers

### Reglas de Terraform

1. Un solo `aws_s3_bucket_notification` por bucket
2. ARNs derivados de recursos (nunca hardcoded)
3. Secretos en `.tfvars` (nunca en código)
4. `terraform validate` antes de declarar terminado
5. `terraform plan` antes de cada cambio significativo
