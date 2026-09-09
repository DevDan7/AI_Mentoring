# Changelog — AI Mentoring

> Log cronológico consolidado de cambios significativos del proyecto. Orden: más reciente primero.

---

## 2026-09

### 08 Sep — Fix HTTP 500 en resultados de simulado libre (permiso `dynamodb:BatchGetItem`)
- **Problema**: En el E2E con `turma-beta-01`, al terminar un simulado libre y pulsar "Ver Resultados" la pantalla mostraba "Erro". `GET /quizzes/{quizId}/results` devolvía HTTP 500.
- **Causa raíz**: `get_results()` (`quiz_engine.py`) usa `questions_table.meta.client.batch_get_item()` sobre `MentoringQuestions` para traer enunciados/respuestas correctas/explicaciones en lote. El rol `quiz-engine-role` (statement `AllowReadQuestions` en `iam.tf`) solo tenía `dynamodb:Query` y `dynamodb:GetItem` → `AccessDeniedException`. Confirmado en CloudWatch `/aws/lambda/quiz-engine` (último evento 2026-09-07 15:59 UTC). `generate_quiz` y `submit_answer` no fallaban porque usan `query`/`get_item`.
- **Solución**: Se añadió `"dynamodb:BatchGetItem"` a `AllowReadQuestions`. `BatchGetItem` sobre la tabla base no requiere permiso de índice; efectivo tras `apply`, sin redeploy de la Lambda.
- **Verificación**: `terraform validate`/`plan` OK; flujo alumno → simulado libre → Ver Resultados carga resumen y detalle por pregunta. Detalle en `technical-log.md`.
- Archivos: `iam.tf` (PR #105).

### 08 Sep — Saneamiento de infraestructura Terraform: drift de Amplify y hash de `archive_file`
- **Amplify — drift permanente de `repository` (PR #106)**: `terraform apply` fallaba en `aws_amplify_app.frontend` con `BadRequestException: You should at least provide one valid token`. El recurso vivo está conectado por **deploy key SSH**; el valor de `repository` en config/state (`https://github.com/DevDan7/AI_Mentoring`) difiere del recurso vivo (`https://github.com/devdan7/ai_mentoring.git`) y nunca re-sincroniza porque la API `UpdateApp` exige un token que Terraform no envía (por `ignore_changes = [access_token]`). **Solución**: agregar `repository` a `ignore_changes` → `lifecycle { ignore_changes = [access_token, repository] }`. Drift cosmético y permanente. El deploy real de Amplify sigue activo (job SUCCEED, frontend sirve HTTP 200).
- **Lambda — falso positivo de `source_code_hash` (PR #107)**: todo `terraform plan` local marcaba las 3 Lambdas como "update in-place" sin cambios en `src/`. Los bloques `data "archive_file"` no fijaban `output_file_mode`, así que el zip hereda los permisos del working tree: local (umask 002 → `0664`) vs checkout de GitHub Actions (umask 022 → `0644`) → distinto hash. **Solución**: `output_file_mode = "0644"` en los 3 bloques → hash determinista. `terraform plan` → `No changes` incluso con `src/*.py` en `0664`.
- Archivos: `amplify.tf`, `lambda.tf`, `lambda_quiz_engine.tf`, `lambda_student_api.tf`.

### 08 Sep — Autorización owner-or-teacher en `get_student` (IDOR) y UX para no-profesores
- **PR #102 — IDOR en `GET /students/{studentId}`**: cualquier alumno autenticado podía leer el perfil de otro alumno por ID. Se añadió el control `is_teacher(claims) or claims['sub'] == studentId` en `get_student()` (`student_api.py`); si no, 403.
- **PR #101 — UX del panel del profesor**: `teacher.html` ante un 403 del backend ahora redirige a `dashboard.html` y muestra aviso; un usuario sin el claim `Teachers` es desviado a los ~3 s en vez de quedar en una página vacía.
- **Nota (diagnóstico Bug 1, "el profesor no ve los resultados")**: NO es por falta de turma — `list_all_students()` y `get_student_quizzes()` no filtran por cohorte. Si el profesor no ve datos, la causa típica es un **token JWT viejo sin `cognito:groups`**: tras agregar al usuario al grupo `Teachers` debe cerrar y volver a iniciar sesión. Detalle en `technical-log.md`.
- Archivos: `src/student_api.py`, `src/frontend/js/teacher.js`.

### 08 Sep — Documentación y tooling; limpieza de código muerto en el frontend
- **PR #103 — documentación y config**: se rescataron a `doc/` los contratos request/response de la API y el catálogo de 10 bugs de la restructuración MVP antes de eliminar `.kiro/` del repo (`doc/architecture.md`, `doc/technical-log.md`); nueva guía `TEACHER_SETUP.md` (alta de profesor en el grupo `Teachers` de Cognito, troubleshooting de 403) y helper `check_user_groups.js` (decodifica el `id_token` en consola del navegador para inspeccionar `cognito:groups`); `CLAUDE.md` (instrucciones de proyecto para Claude Code) y `.claude/agents/git-helper.md` (subagente que propone comandos git/gh sin ejecutarlos). `.gitignore`: `.claude/settings.local.json`.
- **PR #104 — código muerto en el frontend**: se eliminaron 3 funciones sin call sites en `src/frontend/js/api.js` (`updateStudent`, `completeQuiz`, `checkCohortCapacity` — solo se usa `checkCohortCapacityPublic`), el `<div id="successMsg">` nunca mostrado en `dashboard.html` y `teacher.html`, y ~9 atributos `id` sin referencia JS ni CSS. Elementos vivos y clases intactos.
- Archivos: `doc/architecture.md`, `doc/technical-log.md`, `TEACHER_SETUP.md`, `check_user_groups.js`, `CLAUDE.md`, `.claude/agents/git-helper.md`, `.gitignore`, `src/frontend/js/api.js`, `src/frontend/dashboard.html`, `src/frontend/teacher.html`.

### 07 Sep — Fix profesor 403: serialización de `cognito:groups` en API Gateway HTTP API v2
- **Problema**: Tras desplegar los fixes E2E, el panel del profesor saltaba 403 (Forbidden) en `GET /students` y `GET /cohorts`. El frontend sí detectaba el rol (redirigía a `teacher.html`) pero la Lambda devolvía 403.
- **Causa raíz**: API Gateway HTTP API v2 con authorizer JWT de Cognito serializa el claim `cognito:groups` del token como **JSON string** (`'["Teachers"]'`) en `requestContext.authorizer.jwt.claims`, no como lista. El `split(',')` de `is_teacher()` no separaba dicho string → `'Teachers' in {'["Teachers"]'}` → False → 403. El error 403 ya existía implícitamente con el código anterior (igual chequeo); no es un problema de despliegue.
- **Solución**: `is_teacher()` (`student_api.py`) y el chequeo inline de teacher en `get_results()` (`quiz_engine.py`) ahora intentan `json.loads()` cuando `cognito:groups` llega como string, con fallback a `split(',')` (retrocompatible con formatos legacy).
- **Tests**: +5 casos (63 → **68 tests en verde**): JSON string `'["Teachers"]'`, `'["Students","Testers"]'`, multi-grupo, fallback no-array, y acceso 200 a quiz de otro alumno con `'["Teachers","Admin"]'`.
- Archivos: `src/student_api.py`, `src/quiz_engine.py`, `tests/test_phase_system.py`, `tests/test_quiz_engine.py`.

### 07 Sep — Fixes E2E: is_teacher defensivo, get_results sin HTTP 500, tarjeta Simulado Final
- **Problemas detectados en el test E2E**:
  1. Profesor — "Erro ao carregar turmas": `is_teacher(claims)` levantaba `AttributeError` si `claims` era `None`/no-dict, y no normalizaba `cognito:groups` con separación por comas/espacios.
  2. Resultados — Internal Server Error: `get_results()` podía lanzar 500 si un ítem del banco tenía `Options` ausente/lista (formato legacy), si `opt` no era dict, o si un resultado no traía `QuestionID`.
  3. Dashboard — el alumno no tenía tarjeta de "Simulado Final" (no existía tal sección).
- **Solución**:
  1. `is_teacher()` ahora maneja `claims=None`, grupos como string/list/tuple/set, cadenas coma-separadas y valores inválidos (nunca lanza; fail-closed). Mismo patrón aplicado al chequeo inline de teacher en `get_results()`.
  2. Enriquecimiento defensivo en `get_results()`: `question_ids` tolera `QuestionID` ausente, `Options` validado como dict, guardas `isinstance(opt, dict)`, y `try/except` por resultado con `print()` (CloudWatch) + fallbacks (`statement:''`, `correct_answers:[]`, `explanation:''`) — la respuesta queda parcial en vez de 500.
  3. Nueva tarjeta en `dashboard.html` (`#finalExamCard`) con estados: "Disponível" (con botón → `generateFinalExam()`), "Bloqueado pelo professor (disponível a partir de DD/MM/YYYY HH:MM)", "Bloqueado pelo professor" y "Exame final já realizado" (sin botón).
- **Tests**: +9 casos (54 → **63 tests en verde**): `claims=None`, grupos vacíos/numéricos/coma-separados en `is_teacher`; pregunta ausente del banco, `Options` como lista legacy, teacher con claim coma-separado y bloqueo 403 con `claims=None` en `get_results`.
- Archivos: `src/student_api.py`, `src/quiz_engine.py`, `src/frontend/dashboard.html`, `tests/test_phase_system.py`, `tests/test_quiz_engine.py`.

### 07 Sep — Fix frontend: /config devolvía 404 (ruta relativa contra Amplify)
- **Problema**: `config.js` hacía `fetch('/config')` con ruta relativa. En hosting estático (Amplify) el navegador la resuelve contra el dominio del frontend (`main.d1jhem8rxt5h6t.amplifyapp.com/config`) en lugar del API Gateway → 404 → error "Não foi possível carregar a configuração" al entrar.
- **Solución**: Se añadió la constante `API_GATEWAY_URL = "https://9ftb5bwpk7.execute-api.us-east-1.amazonaws.com"` en `src/frontend/js/config.js` y el fetch ahora apunta a `${API_GATEWAY_URL}/config`. El endpoint `/config` (auth `NONE`, CORS `allow_origins=["*"]` en el stage) sigue devolviendo `apiUrl`, `userPoolId` y `clientId` desde las env vars de la Lambda — el único valor fijo es la URL base (bootstrap inevitable en hosting estático).
- **Verificación**: `node --check` OK; `curl https://9ftb5bwpk7.execute-api.us-east-1.amazonaws.com/config` debe responder 200 con JSON.
- **Nota**: si el API Gateway se recrea y cambia el endpoint, actualizar `API_GATEWAY_URL`.

### 07 Sep — Fase 7: Migración de datos ejecutada (restructuración MVP completada)
- **Ejecución**: Migración manual con credenciales AWS locales (nunca por CI/CD) usando `scripts/migrate_clean.py` (pasos: export → confirmación `SI` → batch delete → seed → verificación). Resultado real:
  - Tablas `AI_Mentoring-Students-dev`, `AI_Mentoring-Quizzes-dev`, `AI_Mentoring-QuizResults-dev` y `AI_Mentoring-Cohorts-dev` limpiadas (backups en `scripts/backup/`, gitignored).
  - Turma inicial sembrada en `Cohorts`: `CohortID="turma-beta-01"`, `Name="Beta Turma 01"`, `MaxStudents=7`.
  - `MentoringQuestions` verificada **intacta con 203 preguntas** (tabla excluida explícitamente de todos los pasos).
  - Verificación post-migración: `verify_empty` OK (cohortes=1, resto 0, `beta_cohort_exists=true`).
- **Scripts nuevos**: `scripts/migrate_clean.py` (con flags `--dry-run` `--export-only` `--project` `--environment` `--region` `--backup-dir` `--timestamp`) y `scripts/migrate_restore.py` (auto-detección del juego completo de 4 backups más reciente o `--prefix`). Restauración por si un backup se pierde o hay que revertir.
- **Tests**: `tests/test_migration_scripts.py` con 9 casos en memoria (dry-run sin mutar, export-only, flujo completo, cancelación, roundtrip `Decimal`, restore latest/prefijo, grupos incompletos). Suite total: **54 tests en verde**.
- **Dependencias**: `pytest==9.1.1` y `hypothesis==6.167.1` añadidos a `requirements.txt`; `.gitignore` incluye `scripts/backup/`.
- **Requisitos cumplidos**: 15.1, 15.2, 15.4, 15.5 (y 15.3 por backend). Equivale a Checkpoint 12 del plan de restructuración.
- Archivos: `scripts/migrate_clean.py`, `scripts/migrate_restore.py`, `tests/test_migration_scripts.py`, `.gitignore`, `requirements.txt`.

### 06 Sep — Restructuración del MVP (Fases 1–6): modelo de fases, examen final, frontend y tests
- **Backend (PRs #91–#93)**: Simplificación del sistema de fases de `initial → phase_1 → phase_2 → final_exam → free_practice` (progresión por score ≥ 70%) a `initial → free_practice → final_exam` sin umbrales. `student_api.py` incorporó `GET /config`, `PUT /students/{studentId}/final-exam-release` y `DELETE /students/{studentId}/final-exam-attempt`; se eliminó la llamada Cognito `AdminListGroupsForUser` en `is_teacher()` (ahora lee el claim `cognito:groups`).
- **Examen final (PR #95)**: Liberado por fecha (`FinalExamReleaseDate`) + `has_taken_initial_test`; reanudación de examen `in_progress` (no duplica quizzes); exclusividad estricta de 1 `completed` (`can_generate_final_exam`); anti-repetición; `domain_breakdown` en resultados. Matriz `FINAL_EXAM_DISTRIBUTION` recalibrada a 65 preguntas (Compute 7, DA&ML 2, AI & Serverless 2, MGD/General 0).
- **Frontend (PR #94)**: Overhaul a PT-BR con páginas dinámicas (`index`, `dashboard`, `quiz`, `results`, `teacher`) y módulos JS (`config`, `auth`, `api`, `teacher`) consumiendo `GET /config` para API URL/Cognito dinámicos.
- **Tests (PR #95)**: `test_phase_system.py` reenfocado al modelo nuevo, `test_quiz_engine.py` (nuevo, resume/403/get_results/submit idempotente) y `test_pbt.py` (nuevo, 6 propiedades con Hypothesis). Suite total: 54 tests.
- **Decisión clave**: `phase_1`/`phase_2` eliminados; el proceso de aprendizaje ahora es diagnóstico inicial + práctica libre + un examen final administrado por el instructor.

### 05 Sep (Noche) — Fix Teacher Dashboard initialization & Logout
- **Problema**: El panel del profesor (`teacher.html`) no cargaba los estudiantes, los KPIs ni permitía cerrar sesión (`logoutBtn`). La causa raíz era que la función de inicialización `initTeacherDashboard()` estaba definida en `teacher.js` pero nunca se invocaba al cargar el DOM.
- **Solución**: Se añadió el listener `document.addEventListener("DOMContentLoaded", () => { initTeacherDashboard(); });` al final de `src/frontend/js/teacher.js`, garantizando la carga automática de alumnos, cohortes, KPIs, eventos y el funcionamiento correcto del botón de cierre de sesión.

### 05 Sep (Tarde) — Fix AWS Amplify build error "Unable to assume specified IAM Role"
- **Problema**: Los builds #46, #47 y #48 de AWS Amplify fallaban con `Unable to assume specified IAM Role`. La causa raíz era que el workflow de CI/CD ejecutaba `terraform apply` en cada push a `main`, y como `access_token` es un atributo sensible que siempre genera diff en Terraform, Terraform intentaba actualizar el recurso `aws_amplify_app` en cada ejecución. Esta actualización en caliente invalidaba temporalmente el rol IAM asociado a Amplify.
- **Solución**: Se agregó `lifecycle { ignore_changes = [access_token] }` al recurso `aws_amplify_app.frontend` en `amplify.tf` para evitar que Terraform modifique el recurso innecesariamente y rompa la confianza del rol IAM.

### 05 Sep — Estabilización pre-despliegue: 6 etapas corregidas
- **Problema**: Análisis exhaustivo de infraestructura IaC y lógica backend para estabilizar "AI Mentoring" antes del despliegue final de la interfaz del profesor (teacher.html). Se identificaron y corrigieron 6 etapas críticas afectando IAM, Lambda y manejo NoSQL.

- **Etapa 1 — Infraestructura e IAM** (`iam.tf` / `iam_student_api.tf`): `quiz_engine` realizaba queries sobre GSI `StudentIndex`, pero la política IAM solo tenía permisos sobre la tabla base → `403 AccessDeniedException`. Se agregó `"dynamodb:Query"` a `quiz_engine_policy` y ruta comodín `"${aws_dynamodb_table.quizzes.arn}/index/*"`. También se agregó `"dynamodb:Scan"` a `student_api_policy` para tabla `cohorts`.

- **Etapa 2 — Manejo Defensivo de FailedAttempts** (`quiz_engine.py`): `SET FailedAttempts.phase_1 = :attempts` lanzaba `ValidationException` si el mapa padre no existía. Se implementó patrón **Overwrite Complete Map**: `failed_map = dict(student.get('FailedAttempts') or {})` + `SET FailedAttempts = failed_map`. Garantiza tolerancia a atributos nulos desde el día 1.

- **Etapa 3 — Regresión en Simulados Libres** (`quiz_engine.py`): Fase `'initial'` bloqueaba generación de exámenes libres `'free'` → `403 Forbidden`. Se habilitó `'free'` dentro de `'initial'` en `ALLOWED_TYPES`. También se añadió lectura defensiva `current_phase = student.get('CurrentPhase', 'initial')`.

- **Etapa 4 — Límite Estricto de 1 Intento en Examen Final** (`quiz_engine.py`): No existía bloqueo tras reprobar el Examen Final. Se implementó **Early Return** al inicio de `generate_quiz`: `if quiz_type == 'final_exam' and FailedAttempts.get('final_exam', 0) >= 1: return 403` (interrupción antes de consultar BD).

- **Etapa 5 — Calibración del Examen Final a 65 Preguntas**: Verificación confirmada. La constante `FINAL_EXAM_DISTRIBUTION` suma exactamente 65 preguntas alineadas con blueprint CLF-C02: Dominio 1 (19), Dominio 2 (19), Dominio 3 (15), Dominio 4 (7), complementos (5 + 1). Diccionario mantenido sin cambios (ya estaba calibrado).

- **Etapa 6 — NameError en get_quiz_history** (`student_api.py`): La función intentaba retornar `student.get('CurrentPhase')` pero `student` no estaba instanciado en el scope → error 500. Se agregó lectura previa: `student = students_table.get_item(Key={'StudentID': student_id})` antes de construir el payload.

**Lecciones clave documentadas:**
- GSI es subrecurso independiente con ARN `/index/*`; permisos tabla base no autorizan índices
- `dict(student.get('FailedAttempts') or {...})` usa evaluación perezosa para fallback limpio
- Manejo defensivo garantiza tolerancia a atributos nulos desde MVP v1.0 (aún sin alumnos oficiales)
- Fase 2 usa algoritmo adaptativo `get_weak_topics()`, no distribución estática
- Validaciones generales (`ALLOWED_TYPES`) deben ejecutarse antes que reglas de negocio específicas

---



### 04 Sep — Fix feedback loop SNS→SQS + reducción max_attempts
- **Problema 1**: Feedback loop entre SNS y SQS — cuando `notify_unprocessable()`
  publicaba una alerta a SNS, el mensaje volvía a la cola SQS como si fuera una foto.
  La Lambda intentaba parsear texto no-JSON y fallaba, generando mensajes en DLQ.
- **Solución 1**: `try/except JSONDecodeError` en `processor.py` para ignorar
  mensajes no-JSON (notificaciones SNS) sin fallar.
- **Problema 2**: `max_attempts=6` en botocore causaba timeouts de 30s en Lambda
  cuando Bedrock retornaba ThrottlingException.
- **Solución 2**: Reducido `max_attempts` de 6 a 3 (balance entre resiliencia y timeout).
- **Limpieza**: DLQ vaciada (1 mensaje de notificación SNS eliminado).
- **Resultado**: 203 preguntas en DynamoDB, 0 duplicados, 0 mensajes en DLQ.
- Referencia: sección "Feedback Loop SNS→SQS" en `technical-log.md`

### 03 Sep — Corrección dedupe por contenido: GSI ContentHashIndex + query previo
- **Problema**: la `ConditionExpression` con `attribute_not_exists(ContentHash)` no
  deduplica entre ítems distintos (DynamoDB solo evalúa contra el ítem que se escribe).
  Resultado: 8 pares de duplicados por contenido entraron al subir 65 fotos nuevas.
- **Solución**: crear GSI `ContentHashIndex` en `dynamodb.tf` y añadir un `query` al GSI
  antes de `put_item` en `processor.py`. Si el query retorna un ítem → skip.
- **Limpieza**: script `scripts/limpiar_duplicados_contenido_v2.py` eliminó los 8
  duplicados (conservando las versiones `question_XXX.png`).
- `dynamodb.tf`: nuevo atributo `ContentHash` + GSI `ContentHashIndex` (`KEYS_ONLY`)
- `processor.py`: query al GSI `ContentHashIndex` antes de `put_item`; `ConditionExpression`
  simplificada a solo `attribute_not_exists(QuestionID)` (red de seguridad).
- `iam.tf`: añadido `dynamodb:Query` al rol de la Lambda + ARN del GSI.
- Tests ampliados a 11 (`test_duplicado_por_contenido_se_omite`).
- Resultado final: 155 ítems, 0 colisiones de hash.
- **Lección aprendida**: `ConditionExpression` no es suficiente para dedup por atributo
  entre ítems distintos; se necesita un query previo vía GSI.

### 03 Sep — Fix IAM: DeletePolicyVersion + límite de versiones
- **Problema**: `terraform apply` bloqueado en CI/CD al intentar actualizar
  `mentoring-processor-policy` (añadir `dynamodb:Query` + GSI ARN para
  la dedupe por contenido). Causa: `terraform-cicd-policy` no tenía
  `iam:DeletePolicyVersion` y ya tenía 5 versiones (v2-v6), bloqueando
  la creación de v7 por `LimitExceeded`. 4ta ocurrencia del patrón
  "Huevo y Gallina" en IAM.
- **Solución**: Bypass manual vía AWS CLI — eliminar v2 (liberar espacio),
  inyectar permisos faltantes (`DeletePolicyVersion`, `GetPolicyVersion`,
  `SetDefaultPolicyVersion`) en v6, publicar v7 como default.
- **Prevención actualizada**: ciclo de vida completo de IAM policies
  (`CreatePolicyVersion` + `DeletePolicyVersion` + `GetPolicyVersion` +
  `SetDefaultPolicyVersion`) + limpieza periódica de versiones (máx. 3)
  + check de drift en CI/CD.
- Referencia: sección "Patrón recurrente: Huevo y Gallina en IAM" en
  `architecture.md` + sección "Incidente IAM" en `technical-log.md`

### 03 Sep — Validación de Cupo + Bug Fix + Limpieza

#### Agregado
- Endpoint público `GET /public/cohorts/{cohortId}/capacity` para validar cupo antes del registro
- Frontend valida cupo ANTES de registrar en Cognito (muestra "Turma lotada" si está llena)
- Turma real `BRSAO251/G3` recreada en DynamoDB (7 cupos)

#### Corregido
- **Decimal is not JSON serializable**: `MaxStudents` de DynamoDB viene como `Decimal`, corregido con `int()` en `get_cohort_capacity()`
- **apiCall() redirige durante registro**: `checkCohortCapacity()` usaba `apiCall()` que requería token. Usuario sin token → `logout()` → redirigía a index.html. Corregido con endpoint público sin auth
- **Formulario de confirmación no aparecía**: Debido al bug anterior, `signUp()` se ejecutaba pero `confirmForm` no se mostraba

#### Prueba 3 completada
- AccessExpiresAt validation funciona correctamente
- GET /students/me retorna 403 cuando expiró
- POST /quizzes/generate retorna 403 cuando expiró
- POST /quizzes/submit retorna 403 cuando expiró
- **Block 1 completado al 100%**

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
