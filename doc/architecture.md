# Arquitectura — AI Mentoring

> Plataforma event-driven serverless en AWS para convertir fotos de preguntas de examen en un banco de preguntas estructurado para mentoring de certificaciones AWS.

---

## Pipeline Funcional

```
S3 (foto examen) → S3 Event → SNS (notificaciones + email)
   └──→ SQS (main_queue, max_concurrency=3) → Lambda (processor.py)
           → Bedrock (Claude Haiku 4.5 multimodal) → DynamoDB
```

### Flujo Detallado

1. **S3** recibe una foto de pregunta de examen (`daniel-mentoring-exam-photos-edn-dev`)
2. **S3 Event** dispara notificación a **SQS** (vía SNS para notificación por email)
3. **SQS** encola el mensaje con DLQ (`maxReceiveCount=4`) y control de concurrencia (`maximum_concurrency=3`)
4. **Lambda `processor.py`** procesa la foto:
   - **S3** lee los bytes de la imagen y la codifica en base64
   - **Bedrock Claude Haiku 4.5** analiza la imagen directamente (multimodal): enunciado, opciones, diagramas y tablas; estructura la pregunta en JSON
   - Validación de taxonomía canónica (10 categorías)
   - **DynamoDB** almacena el registro (`PutItem` con doble condición de idempotencia: por archivo `QuestionID` y por contenido `ContentHash`)
   - Si la imagen no es procesable (respuesta no JSON o sin pregunta/opciones), se **publica una alerta SNS** (email) y el mensaje se descarta (sin DLQ, sin reintentos)

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
- **Uso adicional**: la Lambda `processor` publica alertas a este topic cuando una imagen
  no es procesable (permiso `sns:Publish` añadido en `iam.tf`)

### Lambda — Functions

| Lambda | Archivo | Propósito | Memoria | Timeout |
|--------|---------|-----------|---------|---------|
| `mentoring-exam-processor` | `processor.py` | Bedrock multimodal + DynamoDB | 256 MB | 60s |
| `mentoring-student-api` | `student_api.py` | CRUD de estudiantes + cohortes | 256 MB | 15s |
| `quiz-engine` | `quiz_engine.py` | Quizzes y resultados | 256 MB | 15s |

**Configuración común:**
- Python 3.12
- Boto3 inicializado a nivel de módulo
- Variables de entorno con `os.environ.get()`
- `botocore adaptive retry` en `processor.py` (max_attempts=6)
- **Empaquetado**: un `data "archive_file"` por Lambda (`lambda*.tf`), zip de un solo `.py` desde `src/`, con `output_file_mode = "0644"` para que `source_code_hash` sea determinista sin importar el umask de quien corra el plan (CI usa 0644; local con umask 002 daba 0664 → diff fantasma en las 3 Lambdas). Añadido el 2026-09-08 (PR #107).

### DynamoDB — Tablas

| Tabla | PK | GSIs | Propósito |
|-------|-----|------|-----------|
| `MentoringQuestions` | `QuestionID` | `TopicIndex` (Topic), `ContentHashIndex` (ContentHash) | Banco de preguntas (dedupe por contenido vía GSI) |
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
- **Propósito**: Analiza la imagen directamente (multimodal) y estructura la pregunta de examen
- **Entrada**: Imagen base64 + prompt de texto
- **Prompt**: Instrucciones en inglés para mapear a 10 categorías canónicas
- **Respuesta**: JSON estructurado con `topic`, `question_text`, `question_type`, `correct_count`, `options`
- **Límite de imagen**: ~3.75 MB por imagen (fotos típicas muy por debajo)

### Rekognition — OCR (eliminado)

- **Operación anterior**: `DetectText`
- **Estado**: Reemplazado por el análisis multimodal de Bedrock (2026-09-02)
- **Motivo**: Bedrock interpreta el layout completo (enunciado, opciones, diagramas, tablas)
  que el OCR plano pierde; elimina un componente y su costo del pipeline
- **Permiso IAM**: `rekognition:DetectText` retirado del rol de la Lambda

### API Gateway — HTTP API

- **Tipo**: HTTP API v2
- **Autenticación**: JWT Authorizer (Cognito User Pool)
- **Throttling**: 50 rps rate limit, 100 burst
- **CloudWatch**: Logs habilitados

**Rutas:**

| Método | Ruta | Lambda | Descripción |
|--------|------|--------|-------------|
| GET | `/config` | student_api | Config pública (API URL, Cognito User Pool/Client) — sin auth |
| POST | `/students` | student_api | Crear alumno |
| GET | `/students` | student_api | Listar alumnos (solo teacher) |
| GET | `/students/me` | student_api | Obtener perfil propio |
| PUT | `/students/me` | student_api | Actualizar perfil propio |
| GET | `/students/{studentId}` | student_api | Obtener alumno por ID (teacher, o el propio alumno — fix 2026-09-08) |
| GET | `/students/me/quizzes` | student_api | Historial de simulados propio |
| GET | `/students/{studentId}/quizzes` | student_api | Historial de simulados de un alumno (solo teacher) |
| PUT | `/students/{studentId}/phase` | student_api | Cambiar fase de alumno (solo teacher) |
| PUT | `/students/{studentId}/final-exam-release` | student_api | Liberar examen final de un alumno con fecha (solo teacher) |
| DELETE | `/students/{studentId}/final-exam-attempt` | student_api | Resetear intento de examen final (solo teacher) |
| GET | `/cohorts` | student_api | Listar cohortes |
| GET | `/cohorts/{cohortId}/capacity` | student_api | Consulta de cupo (requiere auth) |
| GET | `/public/cohorts/{cohortId}/capacity` | student_api | Consulta de cupo (público, sin auth) |
| POST | `/quizzes/generate` | quiz_engine | Generar simulado (initial/free/final_exam) |
| POST | `/quizzes/submit` | quiz_engine | Registrar respuesta |
| GET | `/quizzes/{quizId}/results` | quiz_engine | Obtener resultados (con `domain_breakdown`) |
| GET | `/quizzes/{quizId}` | quiz_engine | Obtener quiz (reanudación de `in_progress`) |
| POST | `/quizzes/{quizId}/complete` | quiz_engine | Completar quiz y persistir resultado |

### Contratos de API (request/response, verificados contra código real 2026-09-08)

Extraído y verificado línea por línea contra `src/student_api.py`/`src/quiz_engine.py` antes de eliminar `.kiro/` (que tenía la fuente original en `design.md`). Solo se listan los endpoints con body no trivial.

```json
POST /students
→ Request:  { "cohort_id": "turma-beta-01" }
→ 201:      { "student_id", "email", "name" }
→ 409:      { "message": "Student profile already exists" }
→ 403:      { "message": "Turma está cheia" }

GET /students   (solo teacher)
→ 200: {
    "students": [{
      "student_id", "name", "email", "cohort_id", "current_phase",
      "failed_attempts", "created_at", "access_expires_at",
      "final_exam_release_date", "has_taken_initial_test"
    }],
    "total": 7
  }

PUT /students/{studentId}/final-exam-release   (solo teacher)
→ Request:  { "release_date": "2025-08-01T10:00:00Z" }
→ 200:      { "student_id", "final_exam_release_date" }

DELETE /students/{studentId}/final-exam-attempt   (solo teacher)
→ 200: { "student_id", "message": "Final exam attempt reset" }
→ 404: { "message": "El alumno no tiene examen final registrado" }

GET /students/{studentId}/quizzes   (solo teacher)
→ 200: { "quizzes": [{ "quiz_id", "quiz_type", "topic", "status", "created_at", "completed_at", "score_percentage" }] }

POST /quizzes/generate
→ Request:  { "quiz_type": "initial"|"free"|"final_exam", "topic"?, "num_questions"? (default 5, solo free) }
→ 201:      { "quiz_id", "student_id", "quiz_type", "topic", "questions": [{ "question_id", "topic", "type", "statement", "options": { "A": {"text","keywords"}, ... } }] }
→ 403:      acceso expirado, tipo de quiz no permitido en fase actual, examen ya completado, o fecha no liberada
→ 404:      sin preguntas disponibles (solo quiz initial/final_exam)

POST /quizzes/submit
→ Request:  { "quiz_id", "question_id", "given_answers": ["A"] }
→ 201:      { "result_id", "quiz_id", "is_correct", "explanation" }

POST /quizzes/{quizId}/complete
→ 200: { "message": "Quiz completed", "quiz_id", "completed_at", "score_percentage",
         "phase_advanced"?, "previous_phase"?, "new_phase"? }   // los 3 últimos solo si hubo avance de fase

GET /quizzes/{quizId}/results   (student propio o teacher cualquier quiz)
→ 200: {
    "quiz": { "quiz_id", "student_id", "topic", "status", "created_at" },
    "metrics": { "score_percentage", "total_questions", "correct_answers", "incorrect_answers" },
    "domain_breakdown": { "<dominio CLF-C02>": { "correct", "total", "percentage" } },  // solo si quiz_type == final_exam
    "answers": [{ "question_id", "statement", "given_answers", "correct_answers", "is_correct", "explanation" }]
  }
```

Mensajes de error verbatim usados por el backend (mezclan pt-BR y español, ver nota de idioma en `AGENTS.md`):
- 403 acceso expirado: `"Acesso expirado. Entre em contato com seu instrutor."`
- 403 examen final no liberado: `"Exame disponível a partir de {DD/MM/YYYY HH:MM}"`
- 403 examen final ya completado: `"Você já realizou o exame final. Contate seu instrutor para um novo intento."`
- 400 topic vacío en quiz free: `"O campo topic é obrigatório"`

**Nota de discrepancia encontrada en la verificación:** el `design.md` original (ya eliminado) mostraba una versión simplificada de `is_teacher()` que NO parseaba `cognito:groups` como JSON string. Esa versión simple nunca estuvo en producción tal cual — el código real siempre necesitó (y tiene, ver `student_api.py`) el parseo defensivo documentado en el fix del 2026-09-07 más abajo. No es una regresión, solo un ejemplo de código desactualizado en la spec original.

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
- **Conexión al repo**: deploy key **SSH** (no PAT); `access_token`/`oauth_token` del recurso vivo son `null`.
- **`lifecycle { ignore_changes = [access_token, repository] }`** (`amplify.tf`):
  - `access_token` — atributo sensible que genera diff en cada `apply`; actualizarlo en caliente invalidaba temporalmente el rol IAM de Amplify (ver changelog 05 Sep).
  - `repository` — el casing de la config (`https://github.com/DevDan7/AI_Mentoring`) difiere del recurso vivo (`https://github.com/devdan7/ai_mentoring.git`) y **nunca re-sincroniza**: la API `UpdateApp` de Amplify exige un token cuando cambia `repository`, y Terraform no lo envía por el `ignore` de `access_token` → `apply` fallaba con `BadRequestException: You should at least provide one valid token`. Drift cosmético y permanente; el deploy real no se ve afectado (PR #106, 2026-09-08).

### IAM — Roles y Políticas

| Rol | Propósito | Permisos |
|-----|-----------|----------|
| `mentoring-lambda-processor` | Ejecutar `processor.py` | Bedrock, DynamoDB, SNS, SQS, CloudWatch (Rekognition removido el 2026-09-02) |
| `mentoring-lambda-student-api` | Ejecutar `student_api.py` | DynamoDB (Students GetItem/Query/Put/Update, Cohorts GetItem/Scan, Quizzes Query), CloudWatch Logs |
| `mentoring-lambda-quiz-engine` | Ejecutar `quiz_engine.py` | DynamoDB (`MentoringQuestions` Query/GetItem/**BatchGetItem**; `Quizzes`/`QuizResults` GetItem/Put/Query; `Students` GetItem/UpdateItem), CloudWatch Logs. `BatchGetItem` agregado el 2026-09-08 para `get_results()` (PR #105) |
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
StudentID (PK) | Email | Name | CreatedAt | UpdatedAt | AccessExpiresAt | CohortID | Role | CurrentPhase | PhaseHistory | FailedAttempts | MaxAttemptsAlert | InitialTestQuizID | HasTakenInitialTest | FinalExamReleaseDate
```

- **GSI EmailIndex**: Permite buscar por email
- **GSI CohortIndex**: Permite buscar alumnos por cohorte
- **CohortID**: Referencia a tabla `Cohorts` (enrollment vía URL `?turma=<id>`)
- **AccessExpiresAt**: Fecha de expiración del acceso (CreatedAt + 30 días por defecto)
- **Role**: `"student"` por defecto; `"teacher"` para profesores (asignado vía CLI o claim `cognito:groups`)
- **CurrentPhase**: Fase actual del alumno (`initial`, `free_practice`, `final_exam`) — modelo simplificado post-restructuración
- **PhaseHistory**: Array de objetos `{Phase, UnlockedAt, UnlockedBy}` que registra cada cambio de fase
- **FailedAttempts**: Objeto inicializado `{final_exam: 0}` al crear el alumno. Hoy el control real de intentos lo ejerce el conteo de exámenes finales con `Status=completed` (exclusividad de 1 intento confirmado); campo reservado para métricas.
- **MaxAttemptsAlert**: Campo legacy sin consumo actual en el código (no se escribe desde `quiz_engine.py`/`student_api.py`).
- **InitialTestQuizID**: Quiz ID del diagnóstico inicial
- **HasTakenInitialTest**: Booleano — indica si el alumno completó el diagnóstico `initial`
- **FinalExamReleaseDate**: Fecha ISO en que el examen final queda disponible (lo fija el instructor con `PUT /students/{id}/final-exam-release`)

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
CohortID (PK) | Name | CreatedAt | MaxStudents | Active | PeriodStart | PeriodEnd
```

- **Propósito**: Gestión de cohortes para mentoría grupal
- **Enrollment**: Estudiantes se unen vía URL con parámetro `?turma=<cohort_id>`
- **Validación**: `student_api.py` verifica existencia de cohorte antes de crear/actualizar perfil
- **MaxStudents**: Límite de alumnos por turma (validado en `create_student()`)
- **Validación de cupo**: `student_api.py` cuenta alumnos actuales por CohortIndex y rechaza si llega al tope

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

### ¿Por qué Bedrock multimodal en vez de Rekognition? (2026-09-02)

**Contexto**: El pipeline original dependía de Rekognition `DetectText` para extraer texto plano
y solo ese texto era enviado a Bedrock. La imagen en sí nunca llegaba al modelo.

**Problema**: El OCR plano pierde el layout (enunciado, opciones A–F), diagramas, tablas, gráficos
y marcas de respuesta (✓/●). Si el OCR fallaba en una línea, esa información se perdía.

**Decisión**: Claude Haiku 4.5 es multimodal; el `processor.py` ahora lee los bytes de la imagen
desde S3 (`s3:GetObject`, ya disponible en el IAM de la Lambda) y los envía como imagen base64,
junto a un prompt de texto que pide estructurar la pregunta y describir diagramas/tablas.

**Beneficios:**
1. **Mayor fidelidad**: el modelo interpreta el layout completo y el contexto visual real.
2. **Menos componentes**: se elimina Rekognition del pipeline (una dependencia y su costo menos).
3. **Mejor estructura**: las opciones se leen por posición visual, no por heurística de texto.

**Costos / consideraciones:**
- Imagen típica ≈ 1.6k tokens (~$0.001/pregunta con Haiku), equiparable al costo previo.
- Timeout del Lambda subió de 30s a 60s para dar margen a la inferencia multimodal.
- Límite de ~3.75 MB por imagen; fotos típicas muy por debajo.

**Manejo de fallos**: si la respuesta no es JSON parseable o no trae pregunta/opciones,
el mensaje se descarta (`continue`, sin excepción, sin DLQ) pero se **publica una alerta SNS**
(email) con la clave del archivo y el motivo — la imagen no se pierde silenciosamente.

### ¿Cómo se evitan preguntas duplicadas por contenido? (2026-09-02, corregido 2026-09-03)

**Problema original**: La dedupe solo funcionaba por archivo (`attribute_not_exists(QuestionID)`).
Una misma pregunta subida en 2+ fotos con distinto nombre creaba duplicados.

**Primera solución (2026-09-02)**: añadir `ContentHash` y usar `ConditionExpression` doble.
Pero DynamoDB solo evalúa `attribute_not_exists` contra el ítem que se escribe, no contra
la tabla → no deduplica entre ítems distintos. Entraron 8 duplicados.

**Solución corregida (2026-09-03)**: GSI `ContentHashIndex` + query previo.

1. **GSI `ContentHashIndex`** en `dynamodb.tf`: permite buscar por `ContentHash`.
2. **`processor.py`** hace un `query` al GSI antes de `put_item`:
   - Si el query retorna un ítem → la pregunta ya existe → skip.
   - Si no retorna nada → procede con `put_item`.
3. **`ConditionExpression`** simplificada a `attribute_not_exists(QuestionID)` (red de seguridad).

**Lección**: `ConditionExpression` con `attribute_not_exists` no es suficiente para dedup
por atributo entre ítems distintos; se necesita un query previo vía GSI.

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

**Problema**: El proyecto ha enfrentado **cuatro veces** el mismo problema de dependencia circular en permisos IAM durante la automatización CI/CD:

1. **2026-08-24**: El rol `ai-mentoring-github-actions` no podía ejecutar `terraform apply` para crear `terraform-cicd-policy` porque esa política le daría permisos de escritura que no tenía aún.

2. **2026-08-27**: Al agregar permisos `cloudfront:*` y `amplify:*` a `terraform-cicd-policy`, Terraform necesitaba `iam:CreatePolicyVersion` para actualizar el body de la política, pero ese permiso no existía en la política.

3. **2026-09-01**: El rol `mentoring-amplify-role` empezó a fallar con
   `Unable to assume specified IAM Role` durante builds de Amplify. La causa
   NO fue el patrón del ARN en la condición `ArnLike` sobre `aws:SourceArn`
   — fue doble: por un lado, Amplify requería `ArnLikeIfExists` en el trust policy, y por otro, **Terraform recreaba/modificaba el recurso `aws_amplify_app` en cada ejecución de `apply` debido a cambios detectados en el `access_token` (sensible)**. Esta actualización constante del recurso Amplify invalidaba temporalmente el rol IAM.
   *Solución aplicada (2026-09-05)*: Se añadió `lifecycle { ignore_changes = [access_token] }` en `amplify.tf` para evitar que Terraform modifique innecesariamente la app Amplify en cada CI/CD.


   Para aplicar el fix (cambiar `ArnLike` por `ArnLikeIfExists` en el trust
   policy de `amplify_role`) apareció una **variante nueva** del mismo
   problema de fondo: el rol `ai-mentoring-github-actions` no tenía el
   permiso `iam:UpdateAssumeRolePolicy` — que es una acción DISTINTA de
   `iam:UpdateRole` (esa solo cubre descripción/duración de sesión, no el
   trust policy). Sin ese permiso puntual, ni siquiera GitHub Actions podía
   aplicar el cambio.

4. **2026-09-03**: Al actualizar `mentoring-processor-policy` (añadir
   `dynamodb:Query` + GSI ARN para la dedupe por contenido), Terraform
   necesitó eliminar la versión vieja de la política (`v2`). Pero
   `terraform-cicd-policy` no tenía `iam:DeletePolicyVersion`. Además,
   la política ya tenía 5 versiones (v2-v6), bloqueando la creación de
   `v7` por `LimitExceeded`. Resolución: bypass manual vía AWS CLI
   (eliminar v2, inyectar permisos, publicar v7).

**Causa raíz**: Terraform gestiona políticas IAM como recursos con versiones.
Para actualizar una política existente, necesita crear una nueva versión y
eliminar la más antigua (máximo 5 versiones). Si la política no tiene
`iam:DeletePolicyVersion`, Terraform no puede auto-limpiar versiones viejas.
Al acumularse 5 versiones, se bloquea la creación de nuevas (`LimitExceeded`).

```
terraform-cicd-policy (sin DeletePolicyVersion)
    └── Terraform intenta actualizar mentoring-processor-policy
        └── Necesita crear v7 + eliminar v2
            └── iam:DeletePolicyVersion no existe
                └── Error: AccessDenied
                    └── terraform apply bloqueado
```

**Solución estándar** (para cualquier cambio de permisos en `terraform-cicd-policy`):

1. **CLI manual** con credenciales de admin para actualizar la política
2. **Sincronizar `iam.tf`** para reflejar los cambios hechos en AWS
3. **Terraform plan local** para verificar 0 cambios (sin drift)
4. **Commit y push** para que GitHub Actions pueda ejecutar sin errores

**Si `LimitExceeded`** (5 versiones):
5. `aws iam list-policy-versions` → identificar versiones inactivas
6. `aws iam delete-policy-version` → liberar espacio
7. Repetir pasos 1-4

**Prevención**: Incluir el ciclo de vida completo de IAM policies en
`terraform-cicd-policy`: `iam:CreatePolicyVersion`, `iam:DeletePolicyVersion`,
`iam:GetPolicyVersion`, `iam:SetDefaultPolicyVersion`. Limpiar versiones
viejas periódicamente (máximo 3 por política). Ver `technical-log.md`
para script de limpieza y check de drift en CI/CD.

**Nota**: si el cambio de IAM es sobre un *trust policy*
(`assume_role_policy`) en vez de una política de permisos regular, el
permiso necesario en `terraform-cicd-policy` es específicamente
`iam:UpdateAssumeRolePolicy` — no alcanza con `iam:UpdateRole`.

### Estado vs Objetivo

El objetivo del proyecto tiene 3 piezas:

1. **Base de datos de alumnos** — Perfil, progreso, temas débiles
2. **Generación de aulas desde un banco de simulados** — Quizzes personalizados
3. **Relatorios** — Reportes de progreso por alumno

**Estado actual:**

| Pieza | Estado |
|-------|--------|
| BD de alumnos | ✅ `Students` table + `student_api.py` |
| Banco de preguntas | ✅ `MentoringQuestions` + pipeline de ingesta (203 preguntas) |
| Generación de quizzes | ✅ `quiz_engine.py` (generate_quiz, submit_answer, get_results, complete) |
| Gestión de cohortes | ✅ `Cohorts` table (turma-beta-01 sembrada) + enrollment vía URL |
| Sistema de fases simplificado | ✅ `initial → free_practice → final_exam` sin umbrales (restructuración 2026-09) |
| Relatorios | ⚠️ Parcial — métricas en `get_results` (`domain_breakdown`), sin generación automatizada de reportes |

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
| 7b | ~~Rol de Profesor (teacher dashboard)~~ | ✅ Hecho (2026-09-05) |
| 7c | ~~Historial de quizzes~~ | ✅ Hecho (2026-09-01) |
| 7d | Links externos (Anki, próximos simulados) | ⏳ Pendiente |
| 7e | ~~Restructuración MVP: fases simplificadas + examen final~~ | ✅ Hecho (2026-09-06) |
| 7f | ~~Migración de datos (limpieza tablas + turma-beta-01)~~ | ✅ Hecho (2026-09-07) |
| 7g | ~~Saneamiento infra post-E2E (permiso `BatchGetItem`, hash `archive_file`, drift Amplify)~~ | ✅ Hecho (2026-09-08) |
| 11 | ~~Bloque 1: Protecciones básicas~~ | ✅ Hecho (2026-09-01) |
| 12 | Refactor: AWS Step Functions para orquestación asíncrona | ⏳ Pendiente |
| 13 | Cleanup: avisos de depreciación (`key_schema` vs `hash_key`) | ⏳ Evaluado, mantenido (bug del proveedor AWS) |
| 14 | Generación automatizada de relatorios | ⏳ Pendiente |

---

## 🛠️ Etapas Corregidas (Fase de Estabilización Pre-Despliegue)

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

### Validación de Cupo en Cohorts

**Problema**: Sin límite, una turma podía aceptar alumnos ilimitados.

**Solución**: 
- Campo `MaxStudents` en Cohorts (creado dinámicamente)
- `create_student()` cuenta alumnos actuales por `CohortIndex` antes de insertar
- Si `current_count >= MaxStudents`, retorna 403

**Limitación**: Sin bloqueo optimista, dos registros simultáneos podrían pasar. Aceptado para volumen actual (< 100 alumnos/turma).

### Control de Acceso Temporal

**Problema**: Alumnos podían acceder indefinidamente después de finalizar el período de mentoria.

**Solución**:
- Campo `AccessExpiresAt` en Students (= CreatedAt + 30 días por defecto)
- `get_student()` y `quiz_engine.py` verifican la fecha antes de servir
- Si expiró, retornan 403 con mensaje de contacto al profesor

**Renovación**: Profesor debe actualizar `AccessExpiresAt` manualmente vía CLI o futura interfaz admin.

### Sistema de Fases (modelo simplificado — restructuración 2026-09)

#### Flujo de Progresión

```
initial (Diagnóstico 20q)
    ↓ completar el quiz (sin umbral)
free_practice (práctica libre ilimitada por tema)
    ↓ instructor libera el examen final (FinalExamReleaseDate)
final_exam (65q, matriz AWS Cloud Practitioner)
    → 1 intento completed (exclusividad estricta)
    ↓ instructor resetea el intento para permitir re-intento
```

#### Reglas de Negocio

1. **Diagnóstico sin umbral**: Completar el quiz `initial` (cualquier score) avanza automáticamente a `free_practice` (`PhaseHistory` con `UnlockedBy: system`). El alumno queda marcado con `HasTakenInitialTest=true`.
2. **Práctica libre**: Disponible en todas las fases (`quiz_type='free'`), selección por tema con `num_questions`.
3. **Examen final por fecha**: Se genera solo si el instructor fijó `FinalExamReleaseDate` y la fecha ya pasó. Sin fecha → 403 *"Exame não liberado"*.
4. **Exclusividad estricta**: Un alumno solo puede tener **1 examen final `completed`** (`can_generate_final_exam` = 0 completados). Para un nuevo intento, el instructor usa `DELETE /students/{id}/final-exam-attempt`, que marca el examen más reciente con `Status=reset` (no lo borra).
5. **Reanudación de `in_progress`**: Si existe un examen final en progreso, no se crea otro: se reanuda el existente (evita duplicados por doble submit).
6. **Anti-repetición**: El examen final excluye preguntas ya respondidas por el alumno en quizzes anteriores (`get_student_answered_question_ids`).
7. **Control del profesor**:
   - `PUT /students/{studentId}/phase` — forzar cambio de fase del alumno.
   - `PUT /students/{studentId}/final-exam-release` — fijar/actualizar `FinalExamReleaseDate` (solo teacher).
   - `DELETE /students/{studentId}/final-exam-attempt` — resetear intento del examen final (solo teacher).
8. **Resultados**: `get_results` devuelve score y `domain_breakdown` (desempeño por dominio CLF-C02).

#### Matriz de Preguntas — Examen Final (65 preguntas)

Basado en AWS Cloud Practitioner CLF-C02. Fuente: `FINAL_EXAM_DISTRIBUTION` en `src/quiz_engine.py`:

| Domain | Tema Canonical | Preguntas | % |
|--------|---------------|-----------|---|
| 1. Cloud Concepts | Cloud Concepts & Well-Architected | 16 | 24.6% |
| 2. Security & Compliance | Security, Identity & Compliance | 20 | 30.8% |
| 3. Technology & Services | Compute & Containers | 7 | 10.8% |
| 3. Technology & Services | Storage & Database | 6 | 9.2% |
| 3. Technology & Services | Networking & Content Delivery | 5 | 7.7% |
| 3. Technology & Services | Data, Analytics & Machine Learning | 2 | 3.1% |
| 3. Technology & Services | Application Integration & Serverless Architecture | 2 | 3.1% |
| 4. Billing & Support | Billing, Cost Management & Support | 7 | 10.8% |
| Complemento | Management, Governance & DevOps | 0 | 0% |
| Complemento | General / Otros Servicios | 0 | 0% |
| **Total** | | **65** | **100%** |

**Mapeo de dominios** (para `domain_breakdown`): `TOPIC_TO_DOMAIN` agrupa Compute, Storage, Networking, DA&ML, AI & Serverless, MGD y General en **Cloud Technology & Services**; Cloud Concepts y Billing conservan dominios propios (Cloud Concepts & Well-Architected Framework / Billing, Pricing & Support).

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
