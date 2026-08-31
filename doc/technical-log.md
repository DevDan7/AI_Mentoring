# Technical Log — AI Mentoring

> Registro técnico de pruebas de rendimiento, problemas detectados, soluciones aplicadas y métricas de procesamiento.

---

## Resumen de Métricas por Lote

| Lote | Fecha | Fotos | Éxito | DLQ | Throttling | Duración Prom. | Concurrencia |
|------|-------|-------|-------|-----|------------|----------------|--------------|
| 1 | 2026-08-15 | 109 | 73.4% | 30 | 290 | 7,772 ms | Sin límite |
| 2 | 2026-08-16 | 109 | 100% | 5 | 92 | 18,928 ms | Sin límite |
| 3 | 2026-08-17 | 109 | 100% | 0 | 2 | 10,882 ms | Máx 3 |

**Evolución**: Concurrencia controlada (`maximum_concurrency=3`) eliminó DLQ y redujo throttling 99%.

---

## Pruebas de Desempeño

### Línea Base — 256 MB (2026-08-13)

| Métrica | Valor |
|---------|-------|
| Invocaciones | Ráfaga de ~35 |
| Duration (promedio) | 3,000–4,000 ms |
| Duration (picos) | hasta 8,800 ms |
| Errores | 0 |
| Concurrencia máx. | 2 (límite cuenta: 10) |
| Memoria pico usada | ~105 MB |
| Timeout | 30 s |

**Conclusión**: Función saludable; memoria no es cuello de botella (pico ~105 MB de 256 MB asignados).

### Comparación 512 MB (2026-08-14)

| Métrica | 256 MB (base) | 512 MB | Cambio |
|---------|---------------|--------|--------|
| Duration promedio | 5,453 ms | 6,865 ms | +26% |
| Duration pico | 6,133 ms | 13,325 ms | +117% |
| Errores | 0 | 17 (Throttling) | - |
| Memoria pico | ~105 MB | ~105 MB | 0% |

**Conclusión**: No hay mejora con 512 MB. La memoria jamás fue el cuello de botella. Costo se duplica sin beneficio. **Resuelto (2026-08-15): revertido a 256 MB.**

**Problema metodológico**: El test de 512 MB fue una ráfaga de 34 fotos que saturó el rate limit de Bedrock, contaminando los promedios.

---

## Subida Masiva de Fotos

### Lote 1 — 2026-08-15 (sin control de concurrencia)

| Métrica | Valor |
|---------|-------|
| Fotos enviadas | 109 |
| Items DynamoDB | 80 (73.4%) |
| DLQ | 30 mensajes |
| ThrottlingException | 290 menciones |
| Duración promedio | 7,772 ms |
| Duración máxima | 12,707 ms |
| Memoria pico | ~105 MB |

**Archivos fallidos (29)**: Todos por `ThrottlingException` tras agotar 4 reintentos de SQS.

```
question_002, 006, 011, 014, 016, 025, 028, 032, 035, 036,
question_039, 041, 048, 053, 059, 060, 062, 067, 069, 070,
question_074, 077, 084, 087, 088, 090, 094, 098, 104
```

**Causa raíz**: Ráfaga de 109 fotos → SQS entrega con alta concurrencia (hasta 10 Lambdas paralelas) → rate limit de Bedrock excedido.

**Archivos innecesarios procesados**: `INVENTORY.md` (4 veces), `general.pdf` (1 vez).

### Lote 2 — 2026-08-16 (botocore adaptive retry)

| Métrica | Lote 1 | Lote 2 | Cambio |
|---------|--------|--------|--------|
| Items DynamoDB | 80 (73.4%) | **109 (100%)** | +36% |
| DLQ | 30 | **5** | -83% |
| ThrottlingException | 290 | **92** | -68% |
| Duración promedio | 7,772 ms | **18,928 ms** | +143% |
| Duración máxima | 12,707 ms | **30,000 ms** | +136% |

**Mejora**: Tasa de éxito al 100%. Los 109 photos están en DynamoDB.

**Problema**: Duración promedio duplicada por 6 reintentos de botocore. Algunas invocaciones alcanzaron timeout de 30s.

**5 mensajes en DLQ**: Probablemente `InvalidImageFormatException` (question_004.png).

### Lote 3 — 2026-08-17 (maximum_concurrency=3)

| Métrica | Lote 1 | Lote 2 | **Lote 3** |
|---------|--------|--------|------------|
| Items DynamoDB | 80 | 109 | **109** |
| DLQ | 30 | 5 | **0** |
| ThrottlingException | 290 | 92 | **2** |
| Duración promedio | 7,772 ms | 18,928 ms | **10,882 ms** |

**Distribución de duración:**

| Rango | Cantidad | Porcentaje |
|-------|----------|------------|
| 2-4s | 1 | 0.8% |
| 4-6s | 45 | 34.9% |
| 6-8s | 30 | 23.3% |
| 8-10s | 12 | 9.3% |
| 10-15s | 13 | 10.1% |
| 15-30s | 16 | 12.4% |
| >30s (timeout) | 12 | 9.3% |

**Análisis**:
- ThrottlingException: -99% (de 92 a 2)
- DLQ: -100% (de 5 a 0)
- Duración promedio: -40% (de 18.9s a 10.9s)
- **12 invocaciones (9.3%) alcanzan timeout de 30s** — causado por 2 ThrottlingException que agotan los 6 reintentos de botocore

---

## Problemas Detectados

### 1. ThrottlingException de Bedrock

**Problema**: Las ráfagas de fotos generan alta concurrencia en Lambda, excediendo el rate limit de Bedrock para Claude Haiku 4.5.

**Síntomas**:
- `ThrottlingException: Too many requests, please wait before trying again`
- `reached max retries: 4` (botocore)
- Mensajes caen a DLQ tras agotar reintentos

**Soluciones aplicadas**:
1. `botocore adaptive retry` con `max_attempts=6` (2026-08-16)
2. `scaling_config.maximum_concurrency = 3` en SQS ESM (2026-08-17)

**Resultado**: ThrottlingException reducidos de 290 a 2. DLQ eliminada.

**Pendiente**: Reducir `max_attempts` de 6 a 3-4 para evitar timeouts de 30s.

### 2. Procesamiento de Archivos Innecesarios

**Problema**: El Lambda procesa cualquier objeto S3, incluyendo `.md` y `.pdf` que no son fotos de preguntas.

**Archivos detectados**:
- `INVENTORY.md` — procesado 4 veces con Rekognition (desperdicio)
- `general.pdf` — procesado vía Rekognition (extracción subóptima)

**Solución pendiente**: Agregar filtro en `processor.py` para procesar solo `.png` y `.jpg`.

### 3. Perfiles Duplicados en Students

**Problema**: 2 registros en `Students` para el mismo email, con `StudentID` (sub de Cognito) distintos.

**Causa probable**: `create_student` no valida unicidad por `Email`, solo por `StudentID`.

**Impacto**: No afecta funcionamiento actual (todos los quizzes usan el `StudentID` más reciente).

**Solución pendiente**: Evaluar validación adicional por `EmailIndex` antes de crear perfil nuevo.

### 4. Timeouts de 30s

**Problema**: 9.3% de invocaciones alcanzan el timeout de 30s.

**Causa raíz**: ThrottlingException que agota los 6 reintentos de botocore, consumiendo los 30s del timeout.

**Solución pendiente**:
- Reducir `max_attempts` de 6 a 3-4
- O implementar retry a nivel de aplicación con timeout menor

### 5. Perfiles Duplicados en Students

**Problema**: 2 registros en `Students` para el mismo email, con `StudentID` (sub de Cognito) distintos.

**Causa probable**: `create_student` no valida unicidad por `Email`, solo por `StudentID`.

**Impacto**: No afecta funcionamiento actual (todos los quizzes usan el `StudentID` más reciente).

**Solución pendiente**: Evaluar validación adicional por `EmailIndex` antes de crear perfil nuevo.

---

## Problemas Resueltos

### 1. Concurrencia sin Control

**Problema**: Hasta 10 Lambdas paralelas saturaban Bedrock.

**Solución**: `scaling_config.maximum_concurrency = 3` en Event Source Mapping de SQS.

**Resultado**: Máximo 3 instancias Lambda en paralelo.

### 2. Falta de Idempotencia

**Problema**: Cada foto generaba un `QuestionID` nuevo aunque fuera la misma pregunta reprocesada.

**Solución**: `QuestionID` derivado del `eTag` del objeto S3 con `ConditionExpression='attribute_not_exists(QuestionID)'`.

**Resultado**: Duplicados detectados y omitidos silenciosamente.

### 3. Memoria Desperdiciada

**Problema**: Lambda configurada a 512 MB pero solo usaba ~105 MB.

**Solución**: Revertido a 256 MB.

**Resultado**: Costo reducido a la mitad sin impacto en desempeño.

### 4. Error de Concurrencia en Lambda

**Problema**: `reserved_concurrent_executions` causaba error porque la cuenta tiene límite de 10.

**Error**: `InvalidParameterValueException: decreases account's UnreservedConcurrentExecution below its minimum value of [10]`

**Solución**: Reemplazado por `scaling_config.maximum_concurrency` en SQS ESM.

**Resultado**: Concurrencia controlada sin tocar el pool de la cuenta.

---

### Prueba de Cohortes — 2026-08-29/30

**Contexto**: Validación end-to-end de la funcionalidad de cohortes después de implementar la tabla `Cohorts` y el enrollment vía URL.

**Pasos ejecutados**:
1. Cohorte `BRSAO236` creada vía CLI (`put-item`)
2. Alumno registrado con link `?turma=BRSAO236`
3. Verificación en DynamoDB: `CohortID` asignado correctamente

**Resultado**: ✅ Funcional (con bugs detectados y corregidos)

| Criterio | Estado | Notas |
|----------|--------|-------|
| Cohorte creada | ✅ | `get-item` retorna datos correctos |
| URL capturada | ✅ | Session Storage tiene `pending_cohort_id` |
| Alumno registrado | ✅ | Cognito tiene nuevo usuario |
| CohortID asignado | ✅ | DynamoDB `Students` tiene `CohortID: BRSAO236` |
| CohortIndex GSI | ✅ | Query por `CohortID` retorna el alumno |
| Dashboard muestra turma | ✅ | Corregido (ver bug abaixo) |

**Bug detectado**: Dashboard mostraba `undefined` en Email, ID do Estudante y `Sem turma` en Turma.

**Causa raíz**:
1. `ensureStudentProfile()` retornaba respuesta de `createStudentProfile()` (campos en minúsculas: `student_id`, `email`, `name`) en vez del perfil completo de DynamoDB (PascalCase: `StudentID`, `Email`, `Name`)
2. Dashboard leía `data.Cohort` (string vacío) en vez de `data.CohortID` (valor real)

**Fix aplicado**:
- `api.js`: Después de crear perfil, llamar `getStudent()` para obtener datos completos
- `dashboard.html`: Cambiar `data.Cohort` por `data.CohortID || data.Cohort`

---

## Acciones Correctivas Pendientes

| Prioridad | Acción | Impacto Esperado |
|-----------|--------|------------------|
| Alta | Reducir `max_attempts` de 6 a 3-4 en botocore | Evitar timeouts de 30s |
| Alta | Agregar filtro en `processor.py` (solo `.png`, `.jpg`) | Evitar procesar archivos innecesarios |
| Media | Reprocesar 5 mensajes de DLQ (si quedan) | Recuperar preguntas perdidas |
| Media | Evaluar validación de unicidad por Email en Students | Evitar perfiles duplicados |
| Baja | Habilitar `deletion_protection_enabled = true` en DynamoDB | Protección contra eliminación accidental |
| Baja | Escalar recursos IAM a ARNs específicos | Reducir uso de `Resource: "*"` |
| Baja | Auditar cohortes vacías | Limpiar datos de prueba |

---

## Dashboard Histórico

Se generaron dashboards HTML interactivos para análisis de lotes:
- `doc/dashboard.html` — Análisis del lote 1 (temporal, eliminado)
- `doc/quiz-results-dashboard.html` — Resultados de quizzes (temporal, eliminado)

Los dashboards fueron creados temporalmente para análisis puntual y posteriormente eliminados.
