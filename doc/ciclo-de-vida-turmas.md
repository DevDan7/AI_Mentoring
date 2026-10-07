# Ciclo de vida de turmas y métricas

Estado: diseño aprobado (2026-10-06). Fase 1 implementada (2026-10-06); fases 2-4 pendientes.

## Problema

- La turma es solo una etiqueta (`CohortID`); no existe "turma terminada".
- El vencimiento es individual y arbitrario: `AccessExpiresAt = creación del perfil + 30 días`
  (`src/student_api.py`). Consecuencias: G3 seguía activa una semana después del examen final y
  G4 vencería el 31/10 en mitad de la mentoría.
- No hay métricas consolidadas por turma ni anuales (roadmap: "Report Generator").
- No hay política de retención de datos personales (LGPD).

## Decisiones

| Tema | Decisión |
|---|---|
| Fin del acceso | **Manual.** Sin vencimiento automático (se elimina la regla de 30 días). Los alumnos no rinden el examen final en la misma fecha, así que ninguna regla fija sirve. |
| Encerrar ciclo | Botón del profesor **por turma**: corta el acceso de todos y registra `ClosedAt`, que delimita el ciclo para métricas. |
| Control por alumno | **Bloquear** (corta aunque la turma esté abierta), **Estender** (acceso hasta fecha X aunque la turma esté cerrada), **Recomeçar do zero** (ciclo nuevo, acceso reabierto). |
| Certificación real | Carga manual en el panel: aprobado / reprobado / no rindió + fecha. |
| Datos personales | Se conservan hasta generar el reporte anual; luego se anonimizan. |
| Turma de convidados | `Cohorts.Type = "convidados"`: sin vencimiento automático, el profesor bloquea/desbloquea manualmente; excluida de métricas, snapshots y reporte anual; sin límite de cupo. |
| Reintento | Acción "Recomeçar do zero" por alumno: abre un ciclo nuevo desde `initial`. El historial del ciclo anterior queda oculto para el alumno y visible para el profesor. |

## Ciclo de vida

```
ATIVA ──(profesor: "Encerrar ciclo")──► ENCERRADA ──(snapshot)──► ARQUIVADA ──(reporte anual)──► ANONIMIZADA
alumnos usan la app                    acceso cortado (403)      métricas congeladas en S3        sin nombre/email
```

## Regla de acceso (precedencia)

```
1. Students.AccessStatus = "blocked"                          → sin acceso
2. Students.AccessStatus = "open" y AccessUntil futura/ausente → con acceso (aunque la turma esté cerrada)
3. Cohorts.Status = "closed"                                  → sin acceso
4. Caso contrario                                             → con acceso
```
Una extensión vencida (`open` con `AccessUntil` pasada) vuelve a heredar el estado de la turma.
El profesor siempre ve el perfil de cualquier alumno; la regla solo aplica al propio alumno.

La verificación vive en el backend (`student_api` y `quiz_engine`), no solo en el frontend:
si estuviera solo en la UI, cualquiera la saltaría llamando a la API directamente.

## Turma de convidados

Amigos/desarrolladores que prueban la app y dan feedback (ej. Carlos, Grediana).

- `CohortID` fijo (ej. `CONVIDADOS`), `Type = "convidados"`, sin `MaxStudents` efectivo.
- Acceso activo hasta que el profesor lo bloquee; la turma nunca se cierra.
- Bloqueo/desbloqueo por persona o para toda la turma desde el panel.
- Fuera de toda estadística.
- Para que el mentor pruebe como alumno: segunda cuenta con alias Gmail (`usuario+teste@gmail.com`)
  en esta turma (la cuenta profesor siempre redirige a `teacher.html`).

## Reintentos (ciclos)

Ejemplo: alumna de G3 reprueba el examen final (63.1%) y rinde de nuevo en un mes.

```
Profesor encierra la turma ──► SNAPSHOT de la turma (congelado, ciclo 1; la alumna figura reprobada)
Profesor: "Recomeçar do zero" ──► ciclo 2: fase initial, examen final nuevo, acceso reabierto
Ciclo 2 termina ──► REGISTRO DE REINTENTO aparte: alumno · turma de origen · ciclo · score · fecha
```

- El snapshot de la turma **nunca se modifica**; el reintento es un registro separado ligado a la turma de origen.
- `Students.Cycle` (default 1) y `Quizzes.Cycle`: el alumno solo ve los quizzes de su ciclo actual;
  el profesor ve todos. No se borra nada.
- El alumno sigue perteneciendo a su turma de origen; no ocupa cupo ni cuenta en métricas de otra turma.
- Reporte anual: **aprobación al 1er intento** (snapshot) y **aprobación final con reintentos** (snapshot + reintentos).
- Aplica a cualquier alumno de cualquier turma regular.

## Fases

### Fase 1 — Acceso manual, encerrar ciclo, convidados y reintento ✅
- `create_student`: sin `AccessExpiresAt`, con `Cycle = 1`. El `AccessExpiresAt` heredado se ignora.
- `Cohorts`: `Type` (`regular` por defecto | `convidados`), `Status` (`active` por defecto | `closed`),
  `ClosedAt`, `ClosedBy`, `ReopenedAt`. Convidados: sin tope de cupo, no se pueden cerrar.
- `Students`: `AccessStatus` (`blocked` | `open` | ausente = hereda la turma), `AccessUntil`, `Cycle`.
- `Quizzes.Cycle`: lo graban los quizzes nuevos; sin campo = ciclo 1.
- `evaluate_access()` duplicada idéntica en `student_api.py` y `quiz_engine.py` (un .py por Lambda).
  Se aplica en `GET /students/me`, `POST /quizzes/generate` y `POST /quizzes/submit`.
- Endpoints profesor (`student_api`):
  - `PUT /cohorts/{cohortId}/status` `{status: "closed" | "active"}` — encerrar / reabrir ciclo.
  - `PUT /students/{studentId}/access` `{action: "block" | "unblock" | "open", until?}`.
  - `POST /students/{studentId}/restart` — `Cycle + 1`, fase `initial`, `HasTakenInitialTest = false`,
    quita `FinalExamReleaseDate`/`InitialTestQuizID`/`AccessUntil`, `AccessStatus = open`. Condicional
    sobre el ciclo anterior (doble click → 409).
- Ciclos: historial del alumno filtrado por ciclo actual; examen final e inicial "en curso" por ciclo
  (un ciclo nuevo habilita otro examen final). La anti-repetición de preguntas cruza ciclos a propósito.
- Panel del profesor: columna "Acesso", selector "Ações…" por alumno (Histórico, data do exame, resetar
  tentativa, Bloquear/Desbloquear, Estender, Recomeçar do zero) y sección Turmas con "Encerrar ciclo"/"Reabrir".
- Terraform: 3 rutas; `student_api` + `UpdateItem` en Cohorts; `quiz_engine` + `GetItem` en Cohorts y
  env `COHORTS_TABLE`.
- Migración: `content/scripts-manuales/migrar_ciclo_vida.py` (dry-run por defecto): crea `CONVIDADOS`,
  mueve a los alumnos sin turma, quita `AccessExpiresAt`, pone `Cycle = 1`.

### Fase 2 — Cierre de turma y snapshot
- `Cohorts.Status` suma `archived` cuando el snapshot existe.
- El snapshot se calcula con los datos del ciclo hasta `ClosedAt` (reproducible) y se guarda en `s3://<bucket>/reports/<año>/<CohortID>.json`:
  - diagnóstico inicial vs examen final (por alumno y promedio de mejora)
  - tasa de aprobación del examen final (≥ 70%)
  - dominios con más errores (alimenta `content/conceitos/` y aulas)
  - engagement: simulados por alumno, días activos
  - certificación real (si fue cargada)
- Al terminar un ciclo de reintento: registro `s3://<bucket>/reports/<año>/<CohortID>/retakes/<StudentID>-c<N>.json`.
- Campo en Students: `Certification` `{status, date}` editable por el profesor.

### Fase 3 — Reporte anual
- Agrega los snapshots + registros de reintento del año (no depende de DynamoDB): totales, evolución entre turmas,
  temas críticos, aprobación al 1er intento vs con reintentos. Turmas `convidados` excluidas.
- Salida HTML + narrativa con Bedrock (Report Generator del roadmap).

### Fase 4 — Anonimización (LGPD)
- Tras el reporte anual: borrar nombre/email en Students, eliminar usuarios de Cognito,
  mantener métricas con ID anónimo.
- Script manual con dry-run; nunca en CI/CD.

## Por qué snapshot en S3 y no consultar DynamoDB al final del año
Con ~7 alumnos por turma el volumen y el costo son irrelevantes. El snapshot existe para **desacoplar
métricas de datos operativos**: permite anonimizar o borrar alumnos sin perder estadísticas, y congela
la foto de la turma en el momento del cierre (resets y correcciones posteriores no la alteran).
