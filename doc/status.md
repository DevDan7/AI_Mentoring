# Bitácora técnica — AI Mentoring

> Este documento es de uso interno: hallazgos, deuda técnica y decisiones de arquitectura. No está pensado para reclutadores — para eso está el `README.md`.

## Análisis del proyecto (2026-07-18)

### Qué hace hoy (pipeline funcional)

Arquitectura event-driven serverless en AWS:

```
S3 (foto examen) → SNS (AI-Mentoring-notifications-dev-daniel)
   ├──→ email (suscripción)
   └──→ SQS (main_queue, raw_message_delivery) → Lambda (processor.py)
           → Rekognition (OCR) → Bedrock (Claude Haiku 4.5) → DynamoDB
```

- **S3**: bucket `daniel-mentoring-exam-photos-edn-dev` recibe fotos de preguntas de examen.
- **SQS**: desacopla la ingesta; tiene DLQ con `maxReceiveCount=4` — buen patrón de resiliencia.
- **Lambda `processor.py`**: OCR con Rekognition → prompt a Bedrock pidiendo JSON estructurado en inglés (`topic`, `question_text`, `question_type`, `correct_count`, `options` con `text`/`is_correct`/`explanation`/`keywords`) → limpieza de markdown → `PutItem` en DynamoDB.
- **DynamoDB** `MentoringQuestions`: `QuestionID` (PK) + GSI por `Topic`, modo `PAY_PER_REQUEST`.
- **IAM**: rol y política dedicados, permisos acotados a los recursos necesarios.

Esto ya cubre, parcialmente, el objetivo de "base de datos de simulados": convierte fotos de preguntas en registros estructurados con tema y dificultad.

### Hallazgos y deuda técnica

1. ~~`iam.tf`: statements `AllowIAAnalysis` y `AllowBedrockInvokeModel` duplicaban `bedrock:InvokeModel`~~ — **Resuelto (2026-08-10): consolidado en un solo statement.**
2. ~~`lambda_processor.py` (raíz, vacío) es un artefacto muerto~~ — **Resuelto (2026-08-07): eliminado.**
3. ~~`README.md` estaba vacío~~ — **Resuelto (2026-08-07): README reescrito, separado de esta bitácora.**
4. ~~Sin control de versiones real~~ — **Resuelto (2026-08-07): repo creado en GitHub (`DevDan7/AI_Mentoring`), primer push hecho.**
5. **`terraform.tfstate` y `.tfstate.backup` sin backend remoto** — riesgo si esto llega a un repo remoto sin `.gitignore` (el state puede contener ARNs/IDs sensibles). Confirmar que quedaron excluidos del repo; evaluar backend remoto (S3 + DynamoDB lock) más adelante para colaboración/recuperación segura. **Pendiente.**
6. ~~`.venv` y `.terraform` sin excluir~~ — **Resuelto (2026-08-07): agregados al `.gitignore`.**
7. ~~**Sin manejo de duplicados**: cada foto genera un `QuestionID` nuevo aunque sea la misma pregunta reprocesada (ej. reintento desde DLQ) — puede generar duplicados en la tabla.~~ — **Resuelto (2026-08-13):** `QuestionID` se deriva ahora del `eTag` del objeto S3 (MD5 del contenido en uploads simples), con fallback a `uuid.uuid4()` si no viene. `put_item` usa `ConditionExpression='attribute_not_exists(QuestionID)'`; si ya existe, se captura `ConditionalCheckFailedException` (via `ClientError`), se loguea el duplicado y se omite sin relanzar, evitando reintentos infinitos vía SQS. **Limitación conocida:** en multipart upload el `eTag` es `hex-N` (depende del nº de partes), así que una misma foto subida por PUT simple vs multipart no se deduplica entre sí; el eTag solo es estable dentro del mismo evento S3 (caso SQS-redelivery, que es el objetivo).
8. **DynamoDB solo tiene la tabla de preguntas** — no existe todavía nada para "base de datos de alumnos" ni para relatorios/reportes de desempeño. Es el mayor gap frente al objetivo del proyecto. **Pendiente.**
9. **No hay capa de generación de "aulas" ni de reportes** — el pipeline actual solo ingiere y clasifica preguntas; falta toda la capa de negocio (alumnos, sesiones de mentoría, resultados de simulados, relatorios). **Pendiente.**
10. **Datos sensibles en `.tf`**: se detectó un email personal hardcodeado en `aws_sns_topic_subscription`. **Resuelto (2026-08-11)**: movido a variable `notification_email` (sensible, sin default) con valor real en `terraform.tfvars`, excluido vía `.gitignore` (`*.tfvars`). Regla adoptada: valores que exponen datos personales o credenciales van a `.tfvars`; configuración no sensible (región, entorno, nombres) puede tener `default` en `variables.tf`.
11. **CI sin deploy**: GitHub Actions solo ejecuta `terraform plan` (rol de solo lectura); `terraform apply` es manual. Es intencional hoy, pero hay que documentar que commit/push no despliega infraestructura. **Evaluar** si en el futuro se quiere un apply automático en `main` con permisos controlados.

### Brecha entre lo que existe y el objetivo real

El objetivo tiene 3 piezas: (1) BD de alumnos, (2) generación de aulas desde un banco de simulados, (3) relatorios. Hoy solo existe la mitad de la pieza (2): la ingesta/clasificación de preguntas. Faltan:

- **Tabla de alumnos** (DynamoDB o RDS) con perfil, progreso, temas débiles.
- **Tabla de resultados de simulados** (respuestas del alumno, correctas/incorrectas, timestamp) vinculada por `AlumnoID` + `QuestionID`.
- **Lógica de generación de "aula"**: query a `MentoringQuestions` por `Topic`/`Difficulty` (ya existe el GSI para eso) filtrando por temas débiles del alumno.
- **Generación de relatorios**: otra Lambda o job (podría ser Bedrock de nuevo) que agregue resultados por alumno y genere un resumen/PDF/reporte.
- **Alguna interfaz de entrada** para que el alumno responda las preguntas generadas (hoy el flujo es unidireccional: foto → clasificación, no hay feedback loop del alumno).

### Próximos pasos sugeridos (orden recomendado)

1. ~~Limpiar deuda técnica rápida (lambda vacía, README, primer commit)~~ — **Hecho.**
2. ~~Configurar GitHub Actions con OIDC (validación de Terraform vía `plan` en PRs)~~ — **Hecho (2026-08-08).**
3. Diseñar el modelo de datos de "alumnos" y "resultados de simulados".
4. Añadir una Lambda/endpoint para registrar respuestas del alumno y actualizar progreso.
5. Añadir una Lambda de relatorios que consuma ambas tablas.
6. Resolver el manejo de duplicados (hallazgo #7) antes de escalar el volumen de fotos procesadas.
7. Evaluar backend remoto de Terraform (hallazgo #5).

---

## Log de cambios

- **2026-08-13**: implementada idempotencia en `src/processor.py` (hallazgo #7). `QuestionID` = `eTag` del objeto S3 (sin comillas) con fallback a `uuid.uuid4()`; `ConditionExpression='attribute_not_exists(QuestionID)'` en `put_item`; `ConditionalCheckFailedException` capturada y omitida silenciosamente. Limitación documentada: multipart upload genera eTag compuesto (`hex-N`), pierde deduplicación entre subidas distintas.
- **2026-07-18**: análisis inicial del proyecto.
- **2026-08-07**: repo creado en GitHub, primer push. Lambda vacía eliminada. README separado de esta bitácora. Trust role OIDC para GitHub Actions creado (solo lectura por ahora).
- **2026-08-08**: GitHub Actions (`terraform-plan.yml`) funcionando con autenticación OIDC — sin credenciales de larga duración guardadas en GitHub.
  - **Hallazgo de debugging**: la trust policy del IAM Role debe coincidir con el `sub` exacto que envía el token OIDC de GitHub. Cuando hay un cambio de nombre de usuario o de repo en el historial, GitHub agrega IDs internos inmutables al claim (`repo:usuario@ID/repo@ID:*` en vez de `repo:usuario/repo:*`). El valor real solo se pudo confirmar revisando el evento `AssumeRoleWithWebIdentity` en **CloudTrail** — el log de GitHub Actions solo muestra "Not authorized", sin detalle. Trust policy corregida para usar los IDs reales.
- **2026-08-10/11**: consolidado el statement duplicado de `bedrock:InvokeModel` en `iam.tf`. Agregado notificación por email (SNS) sobre nuevas fotos subidas a S3, con política de tópico restringida por `SourceArn` al bucket. Confirmado funcionando el flujo PR → `terraform plan` automático vía GitHub Actions (rol de solo lectura, no aplica cambios). Movido bloque OIDC de `main.tf` a `iam.tf`. Creado `variables.tf` con variables no sensibles (`aws_region`, `environment`, `project_name`, `bucket_name`) y `notification_email` como sensible, con valor real en `terraform.tfvars` (excluido del repo).
  - **Hallazgo de debugging**: el primer intento de agregar SNS creó un segundo `aws_s3_bucket_notification` para el mismo bucket. En AWS, un bucket solo admite una configuración de notificaciones — dos recursos separados hacen que cada `apply` sobreescriba la configuración anterior en vez de sumarla, arriesgando desactivar silenciosamente el trigger de SQS que alimenta todo el pipeline. Corregido consolidando `queue` y `topic` dentro de un único `aws_s3_bucket_notification`.
- **2026-08-11**: configurado el entorno de desarrollo de opencode para el proyecto (`.opencode/`): agentes (`architect`, `developer`, `reviewer`), skills (`ai-mentoring-architecture`, `aws-serverless`, `python-lambda`, `testing`), comandos (`plan`, `implement`, `test`, `review`, `document`) y reglas (`architecture`, `aws`, `python`, `security`). Se codificaron como reglas los patrones y hallazgos clave del proyecto (un solo `aws_s3_bucket_notification`, referencias en vez de ARNs hardcodeados, secretos en `.tfvars`, menor privilegio) para que futuras sesiones de IA las respeten sin re-descubrirlos.
- **2026-08-12**: rediseñado el prompt de Bedrock en `src/processor.py` para responder preguntas completas de examen: estructura en inglés con opciones A–F, `question_type`, `correct_count`, y por opción (`text`, `is_correct`, `explanation`, `keywords`). El `put_item` en DynamoDB se actualizó a los nuevos campos (`QuestionText`, `QuestionType`, `CorrectCount`, `Options`).
  - **Problema resuelto — SNS rompe el pipeline**: al agregar SNS para notificaciones por email, el flujo dejó de procesar fotos (llegaba el email pero no entraban items a DynamoDB). Causas raíz: (1) la política de la cola referenciaba `aws_sns_topic.s3_notifications` que no existía — `terraform validate` fallaba; (2) no había suscripción SNS→SQS; (3) el bucket notificaba en paralelo a cola y tópico y, con la política cambiada, el envío directo S3→SQS quedaba denegado. Resuelto adoptando SNS como hub único de fan-out (email + SQS): corregida la referencia al tópico real, agregada suscripción `sqs_sub` con `raw_message_delivery = true` (SQS recibe el evento S3 plano → sin cambios en `processor.py`), y eliminado el bloque `queue` del `aws_s3_bucket_notification`.
  - **Hallazgo de debugging**: los cambios se commitearon y mergearon, pero no se aplicaron — GitHub Actions solo corre `terraform plan` (rol de solo lectura), nunca `apply`. El email llegaba porque esa parte ya estaba desplegada, pero la suscripción SQS nueva no existía en AWS. Lección: commit/push ≠ deploy; `terraform apply` se corre manualmente.
  - **Deuda pagada**: el email estaba hardcodeado en `aws_sns_topic_subscription`; conectado a la variable `notification_email` (sensitive, valor real en `terraform.tfvars`).