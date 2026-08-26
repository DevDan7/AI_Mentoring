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
8. ~~**DynamoDB solo tiene la tabla de preguntas** — no exist todavía nada para "base de datos de alumnos" ni para relatorios/reportes de desempeño.~~ — **Parcialmente resuelto (2026-08-18):** creadas 3 tablas DynamoDB nuevas (`Students`, `Quizzes`, `QuizResults`) para soportar landing page, sistema de dudas y métricas de progreso. Pendiente: crear Lambdas de CRUD y lógica de negocio.
9. ~~**No hay capa de generación de "aulas" ni de reportes** — el pipeline actual solo ingiere y clasifica preguntas; falta toda la capa de negocio (alumnos, sesiones de mentoría, resultados de simulados, relatorios).~~ — **Parcialmente resuelto (2026-08-18):** modelo de datos diseñado con tablas `Students`, `Quizzes` y `QuizResults`. Pendiente: implementación de Lambdas y lógica de generación de aulas.
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
3. ~~Diseñar el modelo de datos de "alumnos" y "resultados de simulados"~~ — **Hecho (2026-08-18).**
4. CI/CD con `apply` (GitHub Environments con required reviewers).
5. Migración Frontend a Amplify.
6. Auto-registro de alumnos (SignUp Cognito + sincronización DynamoDB).
7. Refactor: AWS Step Functions para orquestación asíncrona.
8. Cleanup: Resolver avisos de depreciación (key_schema vs hash_key).

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

### Nota adicional — perfiles duplicados en Students

Se detectó, al inspeccionar las tablas, que existen 2 registros en `Students` para el mismo email, con `StudentID` (sub de Cognito) distintos, creados con ~3.5h de diferencia. Causa probable: `create_student` no valida unicidad por `Email`, solo por `StudentID`. No afecta el funcionamiento actual (todos los quizzes existentes usan el `StudentID` más reciente), pero es deuda pendiente: evaluar si conviene una validación adicional por `EmailIndex` antes de crear un perfil nuevo. Pendiente de decidir prioridad.

### Acciones correctivas recomendadas

| Prioridad | Acción | Impacto esperado |
|-----------|--------|------------------|
| Alta | Implementar retry con jitter a nivel de aplicación para `ThrottlingException` | Reducir duración promedio |
| Alta | Reducir `max_attempts` de 6 a 3-4 en botocore | Evitar timeouts de 30s |
| ~~Alta~~ | ~~Configurar `reserved_concurrent_executions` = 3-4~~ | **Resuelto con `scaling_config.maximum_concurrency` en SQS ESM** |
| Media | Agregar filtro de archivos (solo `.png`, `.jpg`) | Evitar procesar INVENTORY.md |
| ~~Media~~ | ~~Reprocesar 5 mensajes de DLQ manualmente~~ | **Resuelto: DLQ vacía (0 mensajes)** |

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

## Resultados del lote 3 — 2026-08-17 (con maximum_concurrency)

### Contexto

Tras aplicar `scaling_config.maximum_concurrency = 3` en el Event Source Mapping de SQS, se subieron nuevamente las 109 fotos para validar la mejora en el control de concurrencia.

### Métricas de procesamiento

| Métrica | Lote 1 (2026-08-15) | Lote 2 (2026-08-16) | **Lote 3 (2026-08-17)** |
|---------|---------------------|---------------------|------------------------|
| Fotos enviadas | 109 | 109 | **109** |
| Items DynamoDB | 80 (73.4%) | 109 (100%) | **109 (100%)** |
| ThrottlingException | 290 | 92 | **2** |
| Duración Promedio | 7,772 ms | 18,928 ms | **10,882 ms** |
| Duración P50 | ~5,000 ms | ~6,000 ms | **6,618 ms** |
| Duración P90 | ~8,000 ms | ~25,000 ms | **29,604 ms** |
| Duración Máxima | 12,707 ms | 30,000 ms | **30,000 ms** |
| Memoria Pico | ~105 MB | 104 MB | **106 MB** |
| DLQ Mensajes | 30 | 5 | **0** |
| Concurrencia | Sin límite | Sin límite | **Máx 3 (SQS ESM)** |

### Distribución de duración (Lote 3)

| Rango | Cantidad | Porcentaje |
|-------|----------|------------|
| 2-4s | 1 | 0.8% |
| 4-6s | 45 | **34.9%** |
| 6-8s | 30 | **23.3%** |
| 8-10s | 12 | 9.3% |
| 10-15s | 13 | 10.1% |
| 15-30s | 16 | 12.4% |
| >30s (timeout) | 12 | 9.3% |

### Análisis

**Mejoras respecto al lote 2:**
- **ThrottlingException: -99%** (de 92 a 2)
- **DLQ: -100%** (de 5 a 0 mensajes)
- **Duración promedio: -40%** (de 18.9s a 10.9s)

**Problema persistente:**
- **12 invocaciones (9.3%) alcanzan timeout de 30s** — causado por 2 ThrottlingException que agotan los 6 reintentos de botocore
- El P90 es 29,604 ms (casi timeout), indicando que las invocaciones con throttling son las más lentas

**Causa raíz de los timeouts:**
Las 12 invocaciones con timeout son las que enfrentaron ThrottlingException. Botocore reintenta 6 veces con backoff exponencial, consumiendo los 30s del timeout de Lambda.

### Dashboard

Se generó un dashboard HTML interactivo en `doc/dashboard.html` con KPIs, comparación de lotes, distribución de duración, estado de infraestructura y recomendaciones.

---

## Modelo de datos — Alumnos, Simulados y Resultados (2026-08-18)

### Contexto

Para soportar la landing page, sistema de dudas y métricas de progreso, se crearon 3 tablas DynamoDB nuevas. El pipeline existente (`MentoringQuestions`) se mantiene intacto para la ingesta de fotos.

### Tablas creadas

| Tabla | PK | GSIs | Propósito |
|-------|-----|------|-----------|
| `Students` | `StudentID` | `EmailIndex` (Email) | Perfil del alumno, tracking de sesión |
| `Quizzes` | `QuizID` | `StudentIndex` (StudentID) | Simulados generados |
| `QuizResults` | `ResultID` | `QuizIndex` (QuizID), `StudentIndex` (StudentID + Timestamp) | Respuestas del alumno |

### Estructura de cada tabla

**Students:**
```
StudentID (PK) | Email | Name | CreatedAt | SessionExpiresAt | TopicsWeak[] | TotalQuizzes | AvgScore
```

**Quizzes:**
```
QuizID (PK) | StudentID | Topic | Difficulty | QuestionCount | Score | Status | CreatedAt
```

**QuizResults:**
```
ResultID (PK) | QuizID | StudentID | QuestionID | GivenAnswer | IsCorrect | Timestamp
```

### Decisiones de diseño

1. **Schema mínimo en Terraform**: DynamoDB es schema-only; solo se declaran atributos que son PK, SK o están en un GSI. Los demás campos se crean dinámicamente al hacer `put_item`.
2. **SessionExpiresAt**: Campo para tracking de última actividad del alumno.
3. **GSIs múltiples en QuizResults**: `QuizIndex` permite ver todas las respuestas de un simulado; `StudentIndex` con sort key `Timestamp` permite ver historial cronológico de un alumno.
4. **PAY_PER_REQUEST**: Sin compromisos de capacidad, escala con la demanda.

### Error resuelto — Unused attributes

**Problema**: al agregar las 3 tablas, GitHub Actions falló con:
```
Error: all attributes must be indexed. Unused attributes: ["GivenAnswer" "IsCorrect" "QuestionID" "QuizID"]
```

**Causa raíz**: DynamoDB/Terraform rechaza atributos definidos en el bloque `attribute` que no son Partition Key, Sort Key ni están en un GSI. Se definieron campos como `Name`, `CreatedAt`, `Topic`, `Difficulty`, etc., que no son keys ni indexados.

**Solución**: eliminar del `attribute` todos los atributos que no sean PK, SK o GSI. DynamoDB crea esos campos dinámicamente cuando se insertan con `put_item` desde Python.

**Archivos corregidos**: `dynamodb_students.tf` (-6 atributos), `dynamodb_quizzes.tf` (-6 atributos), `dynamodb_quiz_results.tf` (-3 atributos). Commits en PR #14.

### Archivos Terraform creados

| Archivo | Contenido |
|---------|-----------|
| `dynamodb_students.tf` | Tabla Students + EmailIndex |
| `dynamodb_quizzes.tf` | Tabla Quizzes + StudentIndex |
| `dynamodb_quiz_results.tf` | Tabla QuizResults + QuizIndex + StudentIndex |

### Próximos pasos

- Configurar Cognito para autenticación de alumnos
- Crear Lambda `student_api.py` para CRUD de alumnos
- ~~Crear Lambda `quiz_engine.py` para generación de simulados y registro de respuestas~~ — **Resuelto (2026-08-21)**
- Desarrollar landing page (HTML/React)

---

## Log de cambios

- **2026-07-18**: análisis inicial del proyecto.
- **2026-08-07**: repo creado en GitHub, primer push. Lambda vacía eliminada. README separado de esta bitácora. Trust role OIDC para GitHub Actions creado (solo lectura por ahora).
- **2026-08-08**: GitHub Actions (`terraform-plan.yml`) funcionando con autenticación OIDC — sin credenciales de larga duración guardadas en GitHub.
- **2026-08-10/11**: consolidado el statement duplicado de `bedrock:InvokeModel` en `iam.tf`. Agregado notificación por email (SNS) sobre nuevas fotos subidas a S3, con política de tópico restringida por `SourceArn` al bucket. Confirmado funcionando el flujo PR → `terraform plan` automático vía GitHub Actions (rol de solo lectura, no aplica cambios). Movido bloque OIDC de `main.tf` a `iam.tf`. Creado `variables.tf` con variables no sensibles (`aws_region`, `environment`, `project_name`, `bucket_name`) y `notification_email` como sensible, con valor real en `terraform.tfvars` (excluido del repo).
- **2026-08-11**: configurado el entorno de desarrollo de opencode para el proyecto (`.opencode/`): agentes (`architect`, `developer`, `reviewer`), skills (`ai-mentoring-architecture`, `aws-serverless`, `python-lambda`, `testing`), comandos (`plan`, `implement`, `test`, `review`, `document`) y reglas (`architecture`, `aws`, `python`, `security`). Se codificaron como reglas los patrones y hallazgos clave del proyecto (un solo `aws_s3_bucket_notification`, referencias en vez de ARNs hardcodeados, secretos en `.tfvars`, menor privilegio) para que futuras sesiones de IA las respeten sin re-descubrirlos.
- **2026-08-12**: rediseñado el prompt de Bedrock en `src/processor.py` para responder preguntas completas de examen: estructura en inglés con opciones A–F, `question_type`, `correct_count`, y por opción (`text`, `is_correct`, `explanation`, `keywords`). El `put_item` en DynamoDB se actualizó a los nuevos campos (`QuestionText`, `QuestionType`, `CorrectCount`, `Options`).
- **2026-08-13**: implementada idempotencia en `src/processor.py` (hallazgo #7). `QuestionID` = `eTag` del objeto S3 (sin comillas) con fallback a `uuid.uuid4()`; `ConditionExpression='attribute_not_exists(QuestionID)'` en `put_item`; `ConditionalCheckFailedException` capturada y omitida silenciosamente. Limitación documentada: multipart upload genera eTag compuesto (`hex-N`), pierde deduplicación entre subidas distintas.
- **2026-08-13**: **Prueba de desempeño** — `memory_size` de la Lambda `mentoring-exam-processor` subido de 256 a 512 MB. Hipótesis: más CPU provisionada → menor `Duration` → coste neto igual o menor. **Línea base (256 MB) registrada** en la sección `Pruebas de desempeño`. Aplicado vía `terraform apply`.
- **2026-08-14**: **Resultado de la prueba 512 MB verificado en CloudWatch** — **no se confirma la hipótesis**: duración promedio no mejoró (contaminada por 17 `ThrottlingException` de Bedrock), memoria usada siguió en ~105 MB y el costo de Lambda se duplica. La causa raíz fue la ráfaga de 34 fotos con alta concurrencia (límite cuenta: 10) saturado el rate limit de Claude Haiku 4.5; `raise` incondicional en `processor.py` convirtió el throttle en errores Lambda y **1 mensaje (`07.png`) cayó a la DLQ** sin procesarse. Documentados problemas y soluciones propuestas en la sección `Pruebas de desempeño`.
- **2026-08-15**: vaciada la tabla `MentoringQuestions` (operación de datos vía AWS CLI, sin cambios en Terraform) para eliminar formatos heredados de versiones anteriores del prompt (items sin `Options`/`QuestionType` de antes del rediseño del 2026-08-12) y arrancar el lote real (~100 fotos) con datos 100% consistentes. `memory_size` de la Lambda revertido a 256 MB (PR #8) tras confirmar que 512 MB no mejoraba el desempeño.
- **2026-08-16**: implementado **botocore adaptive retry** en `processor.py` (PR #11) con `max_attempts=6` y `mode='adaptive'`. Resultado: tasa de éxito mejoró de 73.4% a 100% (109/109 fotos en DynamoDB), DLQ reducida de 30 a 5 mensajes, ThrottlingException reducidos de 290 a 92. **Problema**: duración promedio se duplicó de 7.7s a 18.9s debido a los 6 reintentos; algunas invocaciones alcanzaron timeout de 30s. Documentado en sección "Prueba de backoff con jitter — Lote 2026-08-16".
- **2026-08-17**: intento fallido de configurar `reserved_concurrent_executions = 3` en la Lambda (PR #12). Error: `InvalidParameterValueException` porque la cuenta tiene límite de 10 concurrent executions y reservar 3 reduce el pool no reservado por debajo del mínimo de 10. **Solución**: reemplazado por `scaling_config.maximum_concurrency = 3` en el Event Source Mapping de SQS, que controla la concurrencia SIN tocar el pool de la cuenta. Documentado en sección "Error de concurrencia y solución — 2026-08-17".
- **2026-08-18**: creadas 3 tablas DynamoDB (`Students`, `Quizzes`, `QuizResults`) con schema mínimo (solo PK + GSIs) para soportar landing page, sistema de dudas y métricas de progreso. Error de `Unused attributes` resuelto eliminando atributos no indexados del bloque `attribute` en Terraform. Auth planificada con Amazon Cognito. PR #14.
- **2026-08-21**: creada Lambda `quiz_engine.py` con 3 acciones:
  - `generate_quiz`: selecciona preguntas de `MentoringQuestions` por Topic (GSI TopicIndex), crea registro en `Quizzes` con `Status: in_progress`.
  - `submit_answer`: registra respuesta individual en `QuizResults` con `IsCorrect`, `GivenAnswer` y `Timestamp`.
  - `get_results`: consulta quiz y respuestas, calcula métricas (total_questions, correct_answers, score_percentage).
  - IAM: permisos mínimos — `Query` en MentoringQuestions, `GetItem/PutItem/UpdateItem` en Quizzes, `GetItem/PutItem/Query` en QuizResults + indices.
  - Test: ejecutado exitosamente con topic "AWS Well-Architected Framework", 3 preguntas, 1 respuesta registrada, score 100%.
  - Dashboard: `doc/quiz-results-dashboard.html` con KPIs, tabla de resultados y barra de progreso.
  - PR #16 merged.
- **2026-08-21**: creada Lambda `student_api.py` con CRUD completo y validación de tokens Cognito:
  - `create_student`: crea perfil de alumno en DynamoDB después del registro en Cognito.
  - `get_student`: obtiene perfil por `StudentID`.
  - `update_student`: actualiza nombre, cohort, etc.
  - `get_student_by_email`: busca alumno por email usando `EmailIndex` GSI.
  - Validación de token: `cognito-idp:GetUser` contra User Pool.
  - Cognito User Pool desplegado: `us-east-1_YolmrF9tp` con App Client para frontend.
  - IAM: permisos mínimos — DynamoDB (Students) + Cognito GetUser.
  - Tests: 5/5 pasados (create, get, update, get_by_email, token inválido).
  - Archivos: `src/student_api.py`, `lambda_student_api.tf`, `iam_student_api.tf`.
- **2026-08-21**: desplegado API Gateway HTTP API con JWT Authorizer:
  - Archivos creados: `api_gateway.tf` (HTTP API + Stage + Throttling 100 rps/burst 200), `api_gateway_authorizer.tf` (JWT Authorizer con Cognito User Pool), `api_gateway_routes.tf` (7 rutas + 2 integraciones + 2 permisos Lambda).
  - 7 rutas protegidas con JWT: `POST /students`, `GET /students/me`, `PUT /students/me`, `GET /students/{studentId}`, `POST /quizzes/generate`, `POST /quizzes/submit`, `GET /quizzes/{quizId}/results`.
  - Lambdas adaptadas al formato API Gateway v2.0: `student_api.py` y `quiz_engine.py` ahora leen `requestContext.authorizer.jwt.claims` en lugar de `action` del body. Routing por HTTP method + path.
  - `student_api.py`: nuevos endpoints `GET /students/me` y `PUT /students/me` que usan `sub` del JWT claims. `create_student` extrae `email` y `name` del JWT claims.
  - `quiz_engine.py`: `generate_quiz` extrae `student_id` del JWT claims (no del body). `get_results` valida que el quiz pertenezca al alumno autenticado.
  - Outputs: `api_gateway_url` y `api_gateway_id` agregados a `outputs.tf`.
  - Test events creados en `events/apigw/` con formato API Gateway v2.0 (6 archivos).
  - Test script `scripts/test_api.sh`: 7/7 endpoints probados exitosamente.
  - **Error IAM resuelto**: `submit_answer` fallaba con `AccessDeniedException: dynamodb:GetItem on MentoringQuestions`. El policy de `quiz_engine` solo tenía `dynamodb:Query` en `MentoringQuestions`, pero `submit_answer` necesita `dynamodb:GetItem` para verificar la respuesta. Agregado `GetItem` al statement `AllowReadQuestions` en `iam.tf`.
- **2026-08-21**: desplegado la Landing Page con S3 + CloudFront:
  - Frontend: 4 páginas HTML (`index.html`, `dashboard.html`, `quiz.html`, `results.html`) con Pico.css vía CDN.
  - JS modules: `config.js` (variables de entorno), `auth.js` (login, refresh token, logout, token expiry check), `api.js` (wrapper fetch con auto-refresh en 401).
  - Hosting: S3 bucket `ai-mentoring-frontend-*` + CloudFront distribution (`d2dsobmtfi3ppb.cloudfront.net`).
  - Terraform: `landing.tf` con S3 bucket, website configuration, bucket policy pública, CloudFront distribution con redirect a HTTPS.
  - Outputs: `cloudfront_url`, `frontend_s3_bucket_name` agregados a `outputs.tf`.
  - **Bug fix**: `quiz_engine.py` línea 97 buscaba campo `Statement` pero en DynamoDB el campo es `QuestionText`. Corregido `q.get('Statement', '')` → `q.get('QuestionText', '')`.
  - PR #16 merged.
- **2026-08-21**: Bug fix: `quiz_engine.py` (mapeo `QuestionType` corregido).
- **2026-08-21**: Implementación soporte *Multiple Choice*: Backend (`submit_answer` con sets) y Frontend (UI dinámica radio/checkbox).
- **2026-08-21**: Fix: Bucle infinito en login/dashboard por sesión expirada en `auth.js`.
- **2026-08-21**: Hallazgo: Fragmentación de tópicos (109 preguntas, 84 temas distintos). Decisión: Normalización a taxonomía cerrada (pendiente de ejecución).
- **2026-08-22**: Normalización de tópicos (109 registros):
  - **Diagnóstico**: ~84 tópicos fragmentados detectados tras escaneo de `MentoringQuestions`.
  - **Acción**: Ejecución de script de migración (`scripts/normalizar_temas.py`) con mapa de mapeo en `scripts/mapa_temas.json`.
  - **Resultado**: 109 ítems normalizados a 9 categorías canónicas. Preservación del valor original en atributo `OriginalTopic` (idempotente). Respaldo pre-migración generado.
  - **Categorías resultantes**: Cloud Concepts & Well-Architected (34), General / Otros Servicios (16), Compute & Containers (12), Security, Identity & Compliance (12), Storage & Database (12), Billing, Cost Management & Support (10), Networking & Content Delivery (9), Management, Governance & DevOps (3), Application Integration & Serverless Architecture (1).
- **2026-08-22**: Blindaje de taxonomía en `processor.py` (pipeline de ingesta):
  - **Problema**: El prompt original de Bedrock usaba classificación de texto libre para el campo `topic`, lo que podía generar nuevos tópicos no canónicos con cada foto procesada.
  - **Acción**: Tres cambios en `src/processor.py`:
    1. Constante `CANONICAL_TOPICS` con las 9 categorías canónicas (línea 13-24).
    2. Prompt de Bedrock reescrito con instrucción explícita de mapear a una de las 9 categorías, con descripción de qué entra en cada una (línea 96-128).
    3. Validación defensiva post-Bedrock: si el topic devuelto no está en `CANONICAL_TOPICS`, se reasigna automáticamente a `General / Otros Servicios` con log de advertencia (línea 160-166).
  - **Resultado**: Nuevas fotos se clasifican en la taxonomía cerrada "por diseño". La base de datos queda blindada a futuras inserciones fuera de las 9 categorías canónicas.
- **2026-08-22**: Corrección de taxonomía canónica (servicios → funcional):
  - **Problema**: La taxonomía implementada en `processor.py` usaba categorías basadas en servicios (`Amazon EC2`, `Amazon S3`, etc.) que no coincidían con las categorías funcionales definidas en `scripts/mapa_temas.json` y ya aplicadas a los 109 registros existentes.
  - **Acción**: Reemplazadas las 9 categorías de servicios por las 10 categorías funcionales de `mapa_temas.json`:
    - `Cloud Concepts & Well-Architected`
    - `Security, Identity & Compliance`
    - `Compute & Containers`
    - `Storage & Database`
    - `Networking & Content Delivery`
    - `Data, Analytics & Machine Learning`
    - `Management, Governance & DevOps`
    - `Billing, Cost Management & Support`
    - `Application Integration & Serverless Architecture`
    - `General / Otros Servicios`
  - **Archivos modificados**:
    - `src/processor.py`: `CANONICAL_TOPICS` + prompt de Bedrock actualizado con descripciones de cada categoría funcional.
    - `src/frontend/dashboard.html`: `<select>` actualizado con las 10 categorías funcionales.
  - **Resultado**: Pipeline de ingesta y frontend ahora son consistentes con la taxonomía funcional existente en DynamoDB.

  ## Evaluacion — Migracion Rekognition a Textract (2026-08-24)

### Contexto
Se evaluo migrar el OCR de Rekognition a Textract, motivado por Textract 
estar mas especializado en documentos estructurados.

### Metodologia
Script de comparacion aislado (`scripts/test_ocr_comparison.py`, rama 
`test/ocr-comparison-textract`), sin tocar infraestructura ni Lambda de 
produccion. Probado contra 5 fotos reales (`question_001.png` a `005.png`).

### Resultado
- Calidad de deteccion: equivalente entre ambos servicios para texto 
  impreso claro (tipo de imagen que procesa este proyecto).
- Complejidad de parsing: Rekognition devuelve una lista plana (`LINE`/`WORD`); 
  Textract requiere reconstruir el orden de lectura navegando `Relationships` 
  entre bloques `PAGE`/`LINE`/`WORD` -- notablemente mas complejo.
- Costo: diferencia imperceptible al volumen actual (~$0.001/pregunta).

### Decision
Mantener Rekognition. La refactorizacion de `processor.py` que exigiria 
Textract no se justifica sin un problema real de calidad de OCR -- que no 
existe hoy. Textract queda evaluado y descartado por ahora; se reconsiderara 
si el proyecto necesita procesar documentos complejos (tablas, formularios, 
multi-columna) que Rekognition no maneje bien.

## Automatización CI/CD con `terraform apply` (2026-08-24)

- **Contexto**: Implementación de despliegue automático mediante GitHub Actions para el comando `terraform apply`.
- **Arquitectura**: Configuración de `GitHub Environments` (`production`) con protección de *Required Reviewers*. Uso de OIDC para autenticación segura en AWS.
- **Problemas enfrentados**:
    - **Bloqueos de IAM (Huevo/Gallina)**: El rol de GitHub Actions inicial no tenía permisos suficientes (ni para crear recursos, ni para listar proveedores OIDC).
- **Proceso de resolución**:
    1. Ejecución manual de `terraform apply` local (con credenciales de administrador) para "bootstrapear" la política `terraform-cicd-policy`.
    2. Corrección iterativa de permisos en `iam.tf` (`iam:ListOpenIDConnectProviders`, `iam:GetOpenIDConnectProvider`).
    3. Consolidación de ramas y verificación final de privilegios.
- **Estado final**: Pipeline funcional. Los cambios en `main` disparan automáticamente el workflow, que se pausa esperando aprobación manual en el entorno `production`.

## CI/CD — Automatizacion de GitHub Actions con apply + aprobacion manual (2026-08-24)

### Objetivo
Automatizar `terraform apply` en el push a `main`, sin revertir la autenticacion 
OIDC ya implementada (rechazado explicitamente: volver a `AWS_ACCESS_KEY_ID`/`SECRET` 
como secretos de GitHub). Diseño aprobado: ampliar permisos del rol OIDC existente 
+ GitHub Environment (`production`) con "Required reviewers" como gate de aprobacion 
manual antes de que el `apply` real se ejecute.

### Intento 1 — Fallo en cascada (avalancha de "already exists")
Al ejecutar el primer `apply` automatico, fallaron ~10 recursos distintos con 
errores `ResourceInUseException`/`EntityAlreadyExists`/`BucketAlreadyExists` 
(tablas DynamoDB, roles IAM, bucket S3, log group). 

**Causa raiz:** el `tfstate` vivia solo en la maquina local (excluido de git por 
`.gitignore`, correctamente, por contener ARNs/IDs sensibles). GitHub Actions 
corre en una maquina limpia en cada ejecucion — sin acceso a ese estado, Terraform 
no tenia forma de saber que los recursos ya existian, e intento crearlos todos 
desde cero. Confirmado que ningun recurso real se duplico ni se perdio (los 
errores ocurrieron antes de completar ninguna creacion).

Error adicional detectado en el mismo intento: paradoja de arranque en 
`iam:CreatePolicy` — el rol de GitHub Actions (con permisos de solo lectura en 
ese momento) no podia crear la politica que le daria permisos de escritura a 
si mismo. Resuelto aplicando ese cambio puntual manualmente, con credenciales 
propias, desde la terminal local.

### Solucion — Backend remoto de Terraform (hallazgo pendiente desde 2026-07-18, 
### finalmente resuelto)
- Creado bucket S3 (`daniel-mentoring-terraform-state-853106001369`) con 
  versionado activado, y migrado el estado local al bucket via 
  `terraform init -reconfigure`. Verificado con `terraform plan`: 
  `0 to add, 1 to change, 0 to destroy` — cero recursos recreados, migracion 
  exitosa.
- Bloqueo de estado implementado con `use_lockfile = true` (mecanismo nativo 
  de S3, generalmente disponible desde Terraform 1.11), en vez del patron 
  tradicional de tabla DynamoDB dedicada — mas simple, una pieza menos de 
  infraestructura que mantener. Se creo una tabla DynamoDB de bloqueo como 
  respaldo durante la transicion, pero no se usa activamente; candidata a 
  eliminarse en el futuro.

### Incidente secundario — Scope creep de agente IA durante /implement
Al pedirle a opencode que actualizara 3 skills puntuales, el comando `/implement` 
(que le da acceso de lectura a todo el repo "para contexto") interpreto deuda 
tecnica ya documentada en `status.md`/`roadmap.html` (ej. `deletion_protection_enabled`, 
alarma de CloudWatch para DLQ) como parte de la tarea, y modifico 24 archivos en 
vez de los 3 pedidos (incluyendo `src/processor.py`, la Lambda mas critica del 
proyecto, sin que se solicitara). Ningun cambio llego a aplicarse a AWS (verificado 
con `aws dynamodb describe-table` antes de descartar). Revertido selectivamente 
con `git checkout --` a los archivos no solicitados, preservando unicamente el 
trabajo real (backend remoto + las skills pedidas). 

**Leccion:** la instruccion "Minimal Target Change" en el prompt del comando es 
una sugerencia de comportamiento, no una restriccion tecnica dura. Para acotar 
el alcance de un agente con acceso amplio al repo, hay que ser explicito en la 
tarea puntual (ej. "modifica unicamente estos archivos, no toques nada mas aunque 
detectes deuda tecnica en el camino"), no basta con que el comando lo sugiera 
en general.

### Incidente final — Drift de permisos IAM
Al implementar `terraform-cicd-policy` (permisos de escritura para el rol de 
GitHub Actions), la politica `ReadOnlyAccess` quedo desadjuntada del rol 
(causa exacta no confirmada — probablemente durante la implementacion manual 
inicial). Esto bloqueaba el `terraform plan` con errores de `iam:GetPolicy` y 
`cloudfront:GetOriginAccessControl` denegados, ya que un `plan` necesita leer 
el estado de *todos* los recursos gestionados, no solo los del cambio en curso.

Resuelto reconectando `ReadOnlyAccess` manualmente via CLI 
(`aws iam attach-role-policy`). El rol de GitHub Actions ahora combina 
`ReadOnlyAccess` (lectura amplia) + `terraform-cicd-policy` (escritura acotada).

**Pendiente (proxima sesion):** reflejar este attachment en `iam.tf` 
(`aws_iam_role_policy_attachment` faltante) para eliminar el drift entre 
el codigo y el estado real en AWS.

### Estado actual
- PR #33 (`chore/remote-backend-and-opencode-skills`): `terraform plan` en 
  verde. Pendiente de merge.
- Workflow de `apply` automatico con gate de aprobacion manual (`environment: 
  production`): implementado, pero aun no probado de punta a punta con el 
  backend remoto ya funcionando — se validara en el proximo merge a `main`.

### Leccion general de la sesion
Automatizar CI/CD para infraestructura real expone dependencias que un flujo 
manual esconde (estado local, permisos incrementales, orden de bootstrap). 
Cada fallo fue diagnosticable y reversible porque se verifico contra AWS real 
antes de asumir nada (`aws dynamodb describe-table`, `terraform state list`, 
`aws iam list-attached-role-policies`) en vez de confiar solo en el codigo o 
en los mensajes de error de la superficie.

---

## Reestructuración de configuración OpenCode (2026-08-25)

### Objetivo
Alinear la configuración de `.opencode/` con las mejores prácticas oficiales de OpenCode, corregir problemas de estructura y agregar funcionalidades nuevas.

### Cambios realizados

| Archivo | Acción | Descripción |
|---------|--------|-------------|
| `agents.md` → `AGENTS.md` | Renombrado + Fusión | Migrado a formato estándar OpenCode; contenido de `.opencode/rules/*.md` fusionado |
| `opencode.json` | Creado | Políticas de permisos tipo IAM: bloquea `git push`, `terraform apply`, `terraform destroy` |
| `.opencode/agents/architect.md` | Corregido | Agregado frontmatter YAML válido (description, mode, temperature, permission) |
| `.opencode/agents/reviewer.md` | Corregido | Agregado frontmatter YAML válido |
| `.opencode/commands/promts.md` → `prompts.md` | Renombrado + Corregido | Fix typo; agente cambiado de `architect` a `developer`; contenido actualizado en español con opciones numeradas |
| `.opencode/commands/infra-eval.md` | Creado | Nuevo comando para evaluación experta de cambios de infraestructura AWS |
| `.opencode/skills/testing/SKILL.md` | Corregido | Name cambiado de `ai-engineering-skills` a `testing` para coincidir con directorio |
| `.opencode/rules/` | Eliminado | Contenido migrado a `AGENTS.md` (estándar OpenCode) |
| `.opencode/commands/plan.md` | Corregido | Agregadas restricciones de alcance explícitas |
| `.opencode/commands/implement.md` | Corregido | Agregadas restricciones de alcance explícitas (CRÍTICO) |

### Problemas resueltos
1. **`agents.md` no era detectado por OpenCode** — Solo `AGENTS.md` (mayúsculas) es reconocido automáticamente.
2. **Agents sin frontmatter YAML** — `architect.md` y `reviewer.md` carecían de metadatos válidos.
3. **`rules/` no es estructura válida** — OpenCode no reconoce carpetas `rules/`; las reglas van en `AGENTS.md` o se referencian via `instructions`.
4. **Name mismatch en skills** — `testing/SKILL.md` tenía `name: ai-engineering-skills` en vez de `name: testing`.
5. **Sin control de permisos** — No había `opencode.json` para definir qué puede/no puede hacer la IA.
6. **Scope creep en `/implement`** — Agregadas restricciones de alcance explícitas para prevenir que agentes toquen archivos no solicitados.

### Lecciones aprendidas
- La documentación oficial de OpenCode es la fuente de verdad para estructura de archivos.
- `AGENTS.md` (mayúsculas) es el nombre estándar; `agents.md` (minúsculas) no funciona.
- Los permisos en `opencode.json` son equivalentes a políticas IAM pero para la IA.
- El agente asignado a un comando determina sus capacidades (developer tiene permisos de edición, architect no).
- Las restricciones de alcance en commands deben ser explícitas, no implícitas.

### Próximos pasos
- [ ] Probar comando `/prompts` en TUI después de reiniciar OpenCode
- [ ] Probar comando `/infra-eval` con un ejemplo real
- [ ] Verificar que permisos de `opencode.json` funcionan correctamente