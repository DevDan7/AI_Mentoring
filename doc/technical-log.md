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

### Prueba de Flujo de Usuario — 2026-08-31

**Contexto**: Validación del flujo completo de usuario nuevo: registro → quiz inicial → cierre de sesión → retorno.

**Escenario probado**: Usuario sin cohorte, verificación de persistencia de datos y retoma de quiz.

**Pasos ejecutados**:
1. Usuario creado en Cognito (`testflow02@gmail.com`)
2. Primer login: auto-creación de perfil en DynamoDB (sin `CohortID`)
3. Quiz inicial generado (20 preguntas)
4. Usuario respondió parcialmente el quiz
5. Cierre de navegador
6. Segundo login: verificación de retoma

**Resultado**: ✅ Flujo completo exitoso

| Criterio | Estado | Notas |
|----------|--------|-------|
| Auto-creación de perfil | ✅ | `ensureStudentProfile()` crea perfil sin cohorte |
| Quiz inicial generado | ✅ | 20 preguntas distribuidas por temas |
| Retoma después de cierre | ✅ | `HasTakenInitialTest = false` → retoma quiz |
| Dashboard sin cohorte | ✅ | Muestra "Sem turma" correctamente |
| Persistencia de datos | ✅ | Perfil, quiz y respuestas persisten en DynamoDB |

**Comportamiento verificado**:
- **Primera entrada**: Login → auto-creación perfil → redirect a `quiz.html`
- **Retorno después de cierre**: Login → `HasTakenInitialTest = false` → retoma quiz donde quedó
- **Después de completar quiz**: Login → `HasTakenInitialTest = true` → muestra dashboard

**Datos de prueba eliminados**: Cognito, DynamoDB (Students, Quizzes, QuizResults)

---

## Fase 7c — Historial de Quizzes (2026-09-01)

### Implementación

| Componente | Archivo | Descripción |
|------------|---------|-------------|
| IAM | `iam_student_api.tf` | Permiso `dynamodb:Query` sobre tabla Quizzes |
| Backend | `student_api.py` | Endpoint `GET /students/me/quizzes` |
| API Gateway | `api_gateway_routes.tf` | Ruta JWT para historial |
| Frontend | `api.js` + `dashboard.html` | Sección "Histórico de Simulados" con tabla |

### Problemas Detectados y Solucionados

#### Bug 1: Lambda `student_api` falla al iniciar
- **Síntoma**: `GET /students/me` retorna 500, perfil no carga
- **Causa**: `QUIZZES_TABLE` no estaba en variables de entorno de Lambda
- **Solución**: Agregar `QUIZZES_TABLE = aws_dynamodb_table.quizzes.name` en `lambda_student_api.tf`
- **Lección**: Variables de entorno nuevas deben agregarse en Terraform antes de usar en código

#### Bug 2: Score no aparece en historial
- **Síntoma**: Columna Score muestra `-` para todos los quizzes
- **Causa**: `complete_quiz()` no calculaba ni guardaba `ScorePercentage`
- **Solución**: Modificar `complete_quiz()` para calcular score desde `quiz_results` y guardarlo en el quiz

#### Bug 3: `TypeError: Float types are not supported`
- **Síntoma**: Internal Server Error al completar quiz
- **Causa**: Python `round()` retorna `float`, DynamoDB solo acepta `Decimal`
- **Solución**: `from decimal import Decimal` + `Decimal(str(round(...)))` 
- **Ubicación**: `quiz_engine.py:259`

#### Bug 4: `TypeError: Object of type Decimal is not JSON serializable`
- **Síntoma**: Internal Server Error persiste después del fix anterior
- **Causa**: `Decimal` es necesario para DynamoDB pero `json.dumps()` no lo serializa
- **Solución**: Convertir a `float()` antes de retornar en respuesta JSON
- **Ubicación**: `quiz_engine.py:288` + `student_api.py:188`

#### Bug 5: Amplify build falla (Job #19)
- **Síntoma**: `Unable to assume specified IAM Role`
- **Causa**: `Condition` con `ArnLike` sobre `aws:SourceArn` demasiado restrictiva en trust policy de Amplify
- **Solución**: Eliminar bloque `Condition` de `aws_iam_role.amplify_role`
- **Ubicación**: `iam.tf:262-266`

### Resultado del Test

Sección "Histórico de Simulados" muestra correctamente:

| Tipo | Tema | Status | Score | Fecha |
|------|------|--------|-------|-------|
| Simulado Livre | Cloud Concepts | completed | 66.7% | 01/09/2026 |
| Simulado Livre | General / Otros | completed | 100% | 01/09/2026 |
| Diagnóstico | initial | completed | 75.0% | 31/08/2026 |

---

## Bloque 1 — Protecciones Básicas (2026-09-01)

### Implementación

| Componente | Archivo | Descripción |
|------------|---------|-------------|
| Backend | `student_api.py` | Validación MaxStudents + AccessExpiresAt |
| Backend | `quiz_engine.py` | Función `check_student_access()` + checks en generate/submit |
| IAM | `iam.tf` | `dynamodb:GetItem` sobre Students para quiz_engine |

### Cambios Detallados

#### `student_api.py`
- Importación de `timedelta` para cálculo de expiración
- `create_student()`: Valida `MaxStudents` antes de insertar nuevo alumno
  - Cuenta alumnos actuales por `CohortIndex`
  - Si `current_count >= MaxStudents`, retorna 403
- `create_student()`: Agrega `AccessExpiresAt` = `CreatedAt + 30 días`
- `get_student()`: Verifica `AccessExpiresAt` antes de retornar perfil
  - Si expiró, retorna 403 con mensaje de contacto al profesor

#### `quiz_engine.py`
- Nueva función `check_student_access(student_id)`:
  - Obtiene `AccessExpiresAt` desde Students
  - Si expiró, retorna dict con `'error'`
- `generate_quiz()`: Llama `check_student_access()` antes de generar
- `submit_answer()`: Llama `check_student_access()` antes de procesar

#### `iam.tf`
- `quiz_engine_policy`: Agregado `dynamodb:GetItem` sobre Students
  - Necesario para `check_student_access()` en quiz_engine

### Decisiones Técnicas

#### MaxStudents — Sin bloqueo optimista
- Dos registros simultáneos podrían pasar la validación
- Aceptado para volumen actual (< 100 alumnos/turma)
- Futura mejora: `ConditionExpression` con contador atómico

#### AccessExpiresAt — 30 días por defecto
- Renovación manual vía CLI por ahora
- Futura interfaz de admin para profesor

### Turma Real Creada

| Campo | Valor |
|-------|-------|
| CohortID | `BRSAO251/G3` |
| Name | `BRSAO 251 - Maio 2026 - Grupo 3` |
| MaxStudents | 7 |
| PeriodStart | 2026-09-01 |
| PeriodEnd | 2026-09-29 |
| Link | `https://main.d1jhem8rxt5h6t.amplifyapp.com/?turma=BRSAO251/G3` |

### Pruebas de Validación de Cupo (03 Sep 2026)

| # | Prueba | Estado | Notas |
|---|--------|--------|-------|
| 1 | Alumno nuevo puede registrarse en turma | ✅ Completada | Registro exitoso con `?turma=BRSAO251/G3` |
| 2 | Alumno es rechazado cuando turma está llena | ✅ Completada | Mensaje "Turma lotada" funciona correctamente |
| 3 | Alumno con AccessExpiresAt vencido recibe 403 | ✅ Completada | Todos los endpoints retornan 403 correctamente |

#### Bugs Encontrados y Corregidos

1. **Decimal is not JSON serializable**: `MaxStudents` de DynamoDB viene como `Decimal`, no se podía serializar a JSON. Corregido con `int()`.

2. **apiCall() redirige durante registro**: `checkCohortCapacity()` usaba `apiCall()` que requería token. El usuario no tiene token durante registro, entonces `logout()` redirigía a index.html. Corregido con endpoint público sin auth.

3. **Formulario de confirmación no aparecía**: Debido al bug anterior, `signUp()` se ejecutaba pero `confirmForm` no se mostraba.

#### Endpoint Público Agregado

- `GET /public/cohorts/{cohortId}/capacity` — Consulta de cupo sin autenticación
- Retorna: `{ cohort_id, current_count, max_students, is_full }`
- Usado por frontend antes de registrar en Cognito

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
