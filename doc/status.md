# Bitácora técnica — AI Mentoring

> Este documento es de uso interno: hallazgos, deuda técnica y decisiones de arquitectura. No está pensado para reclutadores — para eso está el `README.md`.

## Análisis del proyecto (2026-07-18)

### Qué hace hoy (pipeline funcional)

Arquitectura event-driven serverless en AWS:

```
S3 (foto examen) → S3 Event Notification → SQS (main_queue, con DLQ)
   → Lambda (processor.py) → Rekognition (OCR) → Bedrock (Claude Haiku 4.5) → DynamoDB
```

- **S3**: bucket `daniel-mentoring-exam-photos-edn-dev` recibe fotos de preguntas de examen.
- **SQS**: desacopla la ingesta; tiene DLQ con `maxReceiveCount=4` — buen patrón de resiliencia.
- **Lambda `processor.py`**: OCR con Rekognition → prompt a Bedrock pidiendo JSON estructurado (`topic`, `explanation`, `difficulty`) → limpieza de markdown → `PutItem` en DynamoDB.
- **DynamoDB** `MentoringQuestions`: `QuestionID` (PK) + GSI por `Topic`, modo `PAY_PER_REQUEST`.
- **IAM**: rol y política dedicados, permisos acotados a los recursos necesarios (aunque con dos statements duplicados para `bedrock:InvokeModel`, ver hallazgos).

Esto ya cubre, parcialmente, el objetivo de "base de datos de simulados": convierte fotos de preguntas en registros estructurados con tema y dificultad.

### Hallazgos y deuda técnica

1. **`iam.tf`**: los statements `AllowIAAnalysis` y `AllowBedrockInvokeModel` se solapan (ambos dan `bedrock:InvokeModel` sobre `*`) — es redundante, se puede consolidar en uno. **Pendiente.**
2. ~~`lambda_processor.py` (raíz, vacío) es un artefacto muerto~~ — **Resuelto (2026-08-07): eliminado.**
3. ~~`README.md` estaba vacío~~ — **Resuelto (2026-08-07): README reescrito, separado de esta bitácora.**
4. ~~Sin control de versiones real~~ — **Resuelto (2026-08-07): repo creado en GitHub (`DevDan7/AI_Mentoring`), primer push hecho.**
5. **`terraform.tfstate` y `.tfstate.backup` sin backend remoto** — riesgo si esto llega a un repo remoto sin `.gitignore` (el state puede contener ARNs/IDs sensibles). Confirmar que quedaron excluidos del repo; evaluar backend remoto (S3 + DynamoDB lock) más adelante para colaboración/recuperación segura. **Pendiente.**
6. ~~`.venv` y `.terraform` sin excluir~~ — **Resuelto (2026-08-07): agregados al `.gitignore`.**
7. **Sin manejo de duplicados**: cada foto genera un `QuestionID` nuevo aunque sea la misma pregunta reprocesada (ej. reintento desde DLQ) — puede generar duplicados en la tabla. **Pendiente.**
8. **DynamoDB solo tiene la tabla de preguntas** — no existe todavía nada para "base de datos de alumnos" ni para relatorios/reportes de desempeño. Es el mayor gap frente al objetivo del proyecto. **Pendiente.**
9. **No hay capa de generación de "aulas" ni de reportes** — el pipeline actual solo ingiere y clasifica preguntas; falta toda la capa de negocio (alumnos, sesiones de mentoría, resultados de simulados, relatorios). **Pendiente.**

### Brecha entre lo que existe y el objetivo real

El objetivo tiene 3 piezas: (1) BD de alumnos, (2) generación de aulas desde un banco de simulados, (3) relatorios. Hoy solo existe la mitad de la pieza (2): la ingesta/clasificación de preguntas. Faltan:

- **Tabla de alumnos** (DynamoDB o RDS) con perfil, progreso, temas débiles.
- **Tabla de resultados de simulados** (respuestas del alumno, correctas/incorrectas, timestamp) vinculada por `AlumnoID` + `QuestionID`.
- **Lógica de generación de "aula"**: query a `MentoringQuestions` por `Topic`/`Difficulty` (ya existe el GSI para eso) filtrando por temas débiles del alumno.
- **Generación de relatorios**: otra Lambda o job (podría ser Bedrock de nuevo) que agregue resultados por alumno y genere un resumen/PDF/reporte.
- **Alguna interfaz de entrada** para que el alumno responda las preguntas generadas (hoy el flujo es unidireccional: foto → clasificación, no hay feedback loop del alumno).

### Próximos pasos sugeridos (orden recomendado)

1. ~~Limpiar deuda técnica rápida (lambda vacía, README, primer commit)~~ — **Hecho.**
2. Configurar GitHub Actions con OIDC (validación de Terraform vía `plan` en PRs) — **En curso.**
3. Diseñar el modelo de datos de "alumnos" y "resultados de simulados".
4. Añadir una Lambda/endpoint para registrar respuestas del alumno y actualizar progreso.
5. Añadir una Lambda de relatorios que consuma ambas tablas.
6. Resolver el manejo de duplicados (hallazgo #7) antes de escalar el volumen de fotos procesadas.
7. Evaluar backend remoto de Terraform (hallazgo #5).

---

## Log de cambios

- **2026-07-18**: análisis inicial del proyecto.
- **2026-08-07**: repo creado en GitHub, primer push. Lambda vacía eliminada. README separado de esta bitácora. Trust role OIDC para GitHub Actions creado (solo lectura por ahora).