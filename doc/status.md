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

## Pruebas de desempeño

### Línea base — memory_size = 256 MB (2026-08-13, ~10:15 AM)

| Métrica | Valor |
|---|---|
| Invocaciones | Ráfaga de ~35 |
| Duration (promedio) | 3,000–4,000 ms |
| Duration (picos) | hasta 8,800 ms (Rekognition/Bedrock + cold start) |
| Errores | 0 (0 unhandled, 0 throttles) |
| Concurrencia máx. | 2 (límite cuenta: 10) |
| Timeout | 30 s — absorbe holgadamente los picos de 8.8 s |

**Conclusión**: función saludable; timeout no es cuello de botella. Punto de comparación para el incremento a 512 MB.

### Comparación 512 MB (verificada en CloudWatch, 2026-08-14)

**Advertencia metodológica:** el test de 512 MB fue una ráfaga de 34 fotos subidas a S3 en ~2 s (14:44 UTC). La alta concurrencia resultante **saturó el rate limit de Bedrock**, generando 17 `ThrottlingException` que **contaminan el promedio** de duración (incluye reintentos con backoff). La comparación a continuación usa los datos crudos de CloudWatch; ver `Problemas detectados` abajo.

| Métrica | 256 MB (base) | 512 MB |
|---|---|---|
| Invocaciones | 10 (14:09 UTC) | 45 (14:44–14:46 UTC) |
| Duration promedio | 5,453 ms | 6,865 ms (contaminado por 17 errores) |
| Duration pico | 6,133 ms | 13,325 ms (reintentos con backoff) |
| Duration mínima | 4,092 ms | 2,848 ms |
| Errores | 0 | 17 (Bedrock `ThrottlingException`) |
| Mensajes en DLQ | 0 | 1 (`07.png`) |
| Memoria pico usada | ~105 MB | ~105 MB |
| Concurrencia máx. | 2 | 10 (límite cuenta) |

**Conclusión**: **no hay evidencia de mejora con 512 MB.** La memoria jamás fue el cuello de botella (pico ~105 MB en ambos), la duración no bajó y el costo de Lambda **se duplica** (precio por GB-segundo ×2) sin beneficio demostrado. La prueba quedó invalidada por throttling de Bedrock.

### Problemas detectados durante la prueba (2026-08-13)

1. **17 × `ThrottlingException` de Bedrock** (`InvokeModel`, error: "Too many requests, please wait before trying again", `reached max retries: 4`). Causa raíz: ráfaga de 34 fotos → SQS entrega con alta concurrencia → hasta 10 Lambdas en paralelo (límite cuenta) → **10 llamadas simultáneas a Claude Haiku 4.5** → rate limit excedido.
2. **Pérdida de 1 pregunta en la DLQ**: el mensaje de `07.png` agotó los 4 reintentos de SQS (`maxReceiveCount=4`) y cayó a la DLQ **sin procesarse**. Requiere reproceso manual o descarte.
3. **Comparación de desempeño invalidada**: los promedios de 512 MB incluyen invocaciones fallidas que "quemaron" tiempo en reintentos de botocore (backoff), inflando el pico a 13.3 s.
4. **Costo duplicado sin mejora**: la Lambda no usa más de ~105 MB; subir de 256 a 512 MB solo duplica el costo por invocación.
5. **`raise` incondicional en `processor.py`**: el `except Exception` relanza cualquier error, convirtiendo un throttle temporal de Bedrock en error de Lambda → reintentos SQS → riesgo de pérdida en DLQ.

### Posibles soluciones (pendientes de aplicar)

- **Capturar `ThrottlingException` de Bedrock**: reintento con backoff + jitter dentro del timeout de 30 s (los picos de 13 s caben holgadamente), evitando que el throttle llegue al manejo genérico de errores.
- **Limitar la concurrencia**: `reserved_concurrency` bajo en la Lambda (p.ej. 3–4) y/o espaciado en el fan-out SNS→SQS para no saturar el rate limit de Bedrock.
- **Revisar la DLQ**: reprocesar `07.png` manualmente o descartarlo conscientemente.
- **Revertir a 256 MB** (recomendado): la memoria no es el cuello de botella; 512 MB duplica costo. **Resuelto (2026-08-15).**
- **Prueba controlada futura**: subir fotos escalonadamente (no en ráfaga) para comparar duración limpia antes de cualquier decisión de configuración.

---

## Subida masiva de fotos — Lote 2026-08-15

### Contexto

Tras vaciar la tabla `MentoringQuestions` para eliminar formatos heredados (items sin `Options`/`QuestionType` de antes del rediseño del 2026-08-12), se subió un lote real de **109 fotos** de preguntas de examen AWS (`question_001.png` a `question_109.png`) al bucket S3 `daniel-mentoring-exam-photos-edn-dev`. El objetivo era alimentar el banco de preguntas con datos 100% consistentes y validar el pipeline completo a escala.

### Métricas de procesamiento

| Métrica | Valor |
|---|---|
| Archivos question en S3 | 109 |
| Items en DynamoDB | 80 |
| Mensajes en DLQ | 30 |
| Tasa de éxito | 73.4% |
| Invocaciones Lambda | 223 |
| Menciones ThrottlingException | 290 |
| Duración promedio | 7,772 ms |
| Duración mínima | 116 ms |
| Duración máxima | 12,707 ms |
| Memoria pico usada | ~105 MB (de 256 MB asignados) |

### Distribución de archivos

| Destino | Cantidad | Porcentaje |
|---|---|---|
| DynamoDB (procesados exitosamente) | 80 | 73.4% |
| DLQ (fallidos tras 4 reintentos) | 29 | 26.6% |
| **Total** | **109** | **100%** |

### Archivos fallidos (29)

Todos fallaron por `ThrottlingException` de Bedrock tras agotar los 4 reintentos de SQS:

```
question_002, 006, 011, 014, 016, 025, 028, 032, 035, 036,
question_039, 041, 048, 053, 059, 060, 062, 067, 069, 070,
question_074, 077, 084, 087, 088, 090, 094, 098, 104
```

### Análisis de errores

**Causa raíz**: Las 109 fotos se subieron en ráfaga al S3, lo que generó una ola de mensajes en SQS que la Lambda procesó con alta concurrencia (hasta 10 instancias paralelas, límite de la cuenta). Esto excedió el rate limit de Bedrock para Claude Haiku 4.5, provocando 290 `ThrottlingException`. El código actual (`processor.py` línea 153) relanza cualquier error sin manejo específico de throttling, por lo que los mensajes fallidos agotaron sus 4 reintentos y cayeron a la DLQ.

**Archivos no question procesados innecesariamente**:
- `INVENTORY.md` — procesado 4 veces con Rekognition (desperdicio de invocaciones)
- `general.pdf` — procesado vía Rekognition (extracción subóptima)

### Estado de infraestructura al cierre

| Servicio | Estado | Detalle |
|---|---|---|
| S3 | ✅ Saludable | 144 objetos, 6.22 MB total |
| SQS (main) | ✅ Vacía | 0 mensajes pendientes |
| SQS (DLQ) | ⚠️ 30 mensajes | Requiere reproceso o descarte |
| Lambda | ✅ Activa | 256 MB, timeout 30s, Python 3.12 |
| DynamoDB | ✅ Activa | 80 items, PAY_PER_REQUEST |
| Bedrock | ⚠️ Throttling | Rate limit excedido con concurrencia alta |
| CloudWatch | ✅ Logs disponibles | 223 invocaciones, 183 KB almacenados |

### Lecciones aprendidas

1. **La memoria no es el cuello de botella**: con 256 MB se usan ~105 MB; el cuello es el rate limit de Bedrock, no la capacidad de cómputo de la Lambda.
2. **La concurrencia sin control satura servicios downstream**: subir muchas fotos simultáneamente genera una bomba de concurrencia que Bedrock no puede absorber.
3. **El manejo de errores actual es insuficiente**: el `raise` incondicional convierte un throttle temporal en error de Lambda → reintentos SQS → pérdida en DLQ.
4. **El redrive de SQS no es suficiente para throttling**: con `maxReceiveCount=4` y un rate limit persistente, los mensajes fallidos no se recuperan automáticamente.
5. **Filtros de archivos faltantes**: el Lambda procesa cualquier objeto S3, incluyendo `.md` y `.pdf` que no son fotos de preguntas.

### Acciones correctivas (pendientes)

| Prioridad | Acción | Estado |
|---|---|---|
| Alta | Implementar exponential backoff + jitter en `processor.py` para `ThrottlingException` | Pendiente |
| Alta | Configurar `reserved_concurrent_executions` (3–4) en Lambda | Pendiente |
| Alta | Crear CloudWatch Alarm para DLQ (`ApproximateNumberOfMessagesVisible > 0`) | Pendiente |
| Media | Reprocesar 29 archivos de DLQ con concurrencia limitada | Pendiente |
| Media | Agregar filtro en `processor.py` para procesar solo `.png` y `.jpg` | Pendiente |
| Baja | Habilitar `deletion_protection_enabled = true` en DynamoDB | Pendiente |
| Baja | Escalar recursos IAM a ARNs específicos (evitar `Resource: "*"`) | Pendiente |

### Dashboard de análisis

Se generó un dashboard HTML interactivo con estos resultados en `doc/dashboard.html`. Incluye KPIs, gráficos de distribución y rendimiento, tabla de archivos fallidos, estado de infraestructura y recomendaciones priorizadas.

---

## Prueba de backoff con jitter — Lote 2026-08-16

### Contexto

Se implementó **botocore adaptive retry** en el cliente Bedrock de `processor.py` (PR #11):
- `max_attempts=6` (1 intento original + 5 reintentos)
- `mode='adaptive'` (backoff dinámico basado en throttling)

Objetivo: mitigar las 290 `ThrottlingException` del lote anterior (2026-08-15) que causaron 29 mensajes en DLQ y solo 73.4% de éxito.

### Cambio en `processor.py`

```python
bedrock_config = Config(
    retries={
        'max_attempts': 6,
        'mode': 'adaptive'
    }
)
bedrock_runtime = boto3.client('bedrock-runtime', config=bedrock_config)
```

### Métricas comparativas

| Métrica | Lote anterior (2026-08-15) | Lote actual (2026-08-16) | Cambio |
|---------|---------------------------|--------------------------|--------|
| Fotos enviadas | 109 | 109 | - |
| Items en DynamoDB | 80 (73.4%) | **109 (100%)** | +36.3% |
| Mensajes en DLQ | 30 | **5** | -83% |
| Invocaciones Lambda | 223 | 179 | -20% |
| ThrottlingException | 290 menciones | 92 eventos | -68% |
| Duración promedio | 7,772 ms | **18,928 ms** | +143% |
| Duración máxima | 12,707 ms | **30,000 ms** (timeout) | +136% |
| Memoria pico | ~105 MB | 104 MB | ~0% |
| Duplicados detectados | N/A | 86 | - |

### Análisis

**Mejoras:**
- Tasa de éxito: 73.4% → 100% (las 109 fotos están en DynamoDB)
- DLQ: 30 → 5 mensajes (83% reducción)
- ThrottlingException: 290 → 92 (68% reducción)
- Idempotencia funcionando: 86 duplicados detectados y omitidos correctamente

**Problemas:**
- Duración promedio duplicada: 7.7s → 18.9s (los 6 reintentos de botocore consumen tiempo)
- Timeouts: algunas invocaciones alcanzaron 30,000 ms (límite del timeout)
- Procesa archivos innecesarios: `INVENTORY.md` procesado 3 veces
- 5 mensajes en DLQ: probablemente `InvalidImageFormatException` (question_004.png)

### Hallazgos clave

1. **El backoff a nivel SDK (botocore) NO es suficiente**: con 6 reintentos y adaptive backoff, algunas invocaciones agotan el timeout de 30s antes de completar.
2. **Falta manejo a nivel de aplicación**: el `except Exception` en línea 158 sigue haciendo `raise` incondicional después de que botocore agota sus reintentos.
3. **La concurrencia sigue sin control**: `reserved_concurrent_executions` no está configurado, permitiendo hasta 10 Lambdas paralelas que saturan Bedrock.
4. **El filtro de archivos es necesario**: procesa `.md` y otros formatos no válidos.

### Acciones correctivas recomendadas

| Prioridad | Acción | Impacto esperado |
|-----------|--------|------------------|
| Alta | Implementar retry con jitter a nivel de aplicación para `ThrottlingException` | Reducir duración promedio |
| Alta | Reducir `max_attempts` de 6 a 3-4 en botocore | Evitar timeouts de 30s |
| ~~Alta~~ | ~~Configurar `reserved_concurrent_executions` = 3-4~~ | **Resuelto con `scaling_config.maximum_concurrency` en SQS ESM** |
| Media | Agregar filtro de archivos (solo `.png`, `.jpg`) | Evitar procesar INVENTORY.md |
| Media | Reprocesar 5 mensajes de DLQ manualmente | Recuperar datos perdidos |

---

## Error de concurrencia y solución — 2026-08-17

### Error

Al intentar aplicar `reserved_concurrent_executions = 3` en la Lambda, Terraform falló con:

```
InvalidParameterValueException: Specified ReservedConcurrentExecutions for function 
decreases account's UnreservedConcurrentExecution below its minimum value of [10].
```

### Causa raíz

La cuenta AWS tiene un límite de **10 concurrent executions** (tier gratuito). AWS requiere que el pool `UnreservedConcurrentExecution` sea **>= 10**. Al reservar 3 en la Lambda, el pool no reservado baja a 7, que es menor que el mínimo de 10.

```
Cuenta limit:    10
Reserved:        3  →  Unreserved = 7  ← ¡ERROR! (mínimo es 10)
```

### Solución: `scaling_config.maximum_concurrency` en SQS ESM

En lugar de `reserved_concurrent_executions` en la Lambda, se configuró **`maximum_concurrency`** en el Event Source Mapping de SQS. Esto controla cuántas instancias Lambda puede invocar SQS simultáneamente, SIN tocar el pool de concurrencia de la cuenta.

```hcl
resource "aws_lambda_event_source_mapping" "sqs_trigger" {
  event_source_arn = aws_sqs_queue.main_queue.arn
  function_name    = aws_lambda_function.processor.arn
  batch_size       = 1

  scaling_config {
    maximum_concurrency = 3
  }
}
```

### Por qué esta solución es mejor

| Aspecto | `reserved_concurrent_executions` | `scaling_config.maximum_concurrency` |
|---------|----------------------------------|--------------------------------------|
| Cuenta limit necesaria | > 10 (requiere increase) | **No necesita** |
| Controla concurrencia de | Todas las invocaciones de la Lambda | Solo invocaciones del SQS |
| Afecta otras funciones | Sí | No |
| Throttling | Puede causar throttling si el pool es bajo | **No causa throttling** |

### Resultado verificado

```json
{
    "UUID": "10193a3a-1718-4353-9a66-2b9b532b5acc",
    "State": "Enabled",
    "BatchSize": 1,
    "ScalingConfig": {
        "MaximumConcurrency": 3
    }
}
```

SQS ahora invoca máximo 3 instancias Lambda en paralelo, controlando el throttling de Bedrock sin necesitar aumento de límite de cuenta.

---

## Log de cambios

- **2026-08-13**: **Prueba de desempeño** — `memory_size` de la Lambda `mentoring-exam-processor` subido de 256 a 512 MB. Hipótesis: más CPU provisionada → menor `Duration` → coste neto igual o menor. **Línea base (256 MB) registrada** en la sección `Pruebas de desempeño`. Aplicado vía `terraform apply`.
- **2026-08-14**: **Resultado de la prueba 512 MB verificado en CloudWatch** — **no se confirma la hipótesis**: duración promedio no mejoró (contaminada por 17 `ThrottlingException` de Bedrock), memoria usada siguió en ~105 MB y el costo de Lambda se duplica. La causa raíz fue la ráfaga de 34 fotos con alta concurrencia (límite cuenta: 10) saturado el rate limit de Claude Haiku 4.5; `raise` incondicional en `processor.py` convirtió el throttle en errores Lambda y **1 mensaje (`07.png`) cayó a la DLQ** sin procesarse. Documentados problemas y soluciones propuestas en la sección `Pruebas de desempeño`.
- **2026-08-15**: vaciada la tabla `MentoringQuestions` (operación de datos vía AWS CLI, sin cambios en Terraform) para eliminar formatos heredados de versiones anteriores del prompt (items sin `Options`/`QuestionType` de antes del rediseño del 2026-08-12) y arrancar el lote real (~100 fotos) con datos 100% consistentes. `memory_size` de la Lambda revertido a 256 MB (PR #8) tras confirmar que 512 MB no mejoraba el desempeño.
- **2026-08-16**: implementado **botocore adaptive retry** en `processor.py` (PR #11) con `max_attempts=6` y `mode='adaptive'`. Resultado: tasa de éxito mejoró de 73.4% a 100% (109/109 fotos en DynamoDB), DLQ reducida de 30 a 5 mensajes, ThrottlingException reducidos de 290 a 92. **Problema**: duración promedio se duplicó de 7.7s a 18.9s debido a los 6 reintentos; algunas invocaciones alcanzaron timeout de 30s. Documentado en sección "Prueba de backoff con jitter — Lote 2026-08-16".
- **2026-08-17**: intento fallido de configurar `reserved_concurrent_executions = 3` en la Lambda (PR #12). Error: `InvalidParameterValueException` porque la cuenta tiene límite de 10 concurrent executions y reservar 3 reduce el pool no reservado por debajo del mínimo de 10. **Solución**: reemplazado por `scaling_config.maximum_concurrency = 3` en el Event Source Mapping de SQS, que controla la concurrencia SIN tocar el pool de la cuenta. Documentado en sección "Error de concurrencia y solución — 2026-08-17".
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