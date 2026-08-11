---
name: ai-mentoring-architecture
description: Arquitectura y contexto del proyecto AI Mentoring. Usar cuando se trabaje en cualquier tarea relacionada con el proyecto: pipeline, servicios AWS, modelo de datos, roadmap o bitácora técnica.
---

# AI Mentoring — Arquitectura del Proyecto

Plataforma serverless event-driven que convierte fotos de preguntas de examen en un banco de preguntas estructurado para mentorías de certificación AWS en Escola da Nuvem.

## Pipeline actual (funcional)

```
S3 (foto examen) → S3 Event Notification → SQS (main_queue + DLQ)
   → Lambda (processor.py) → Rekognition (OCR) → Bedrock Claude → DynamoDB (MentoringQuestions)
```

## Servicios y roles

- **S3** — bucket `daniel-mentoring-exam-photos-edn-dev` recibe las fotos.
- **SQS** — desacopla la ingesta del procesamiento; DLQ con `maxReceiveCount=4`.
- **Lambda** — `src/processor.py` (Python 3.12, 256 MB, timeout 30s): OCR con Rekognition, prompt a Bedrock, limpieza de markdown y `PutItem` en DynamoDB.
- **Bedrock** — Claude Haiku 4.5 estructura la respuesta como JSON (`topic`, `explanation`, `difficulty`).
- **DynamoDB** — tabla `MentoringQuestions`: `QuestionID` (PK) + GSI `TopicIndex` por `Topic`, modo `PAY_PER_REQUEST`.
- **SNS** — notificación por email (suscripción `notification_email`) ante nuevas fotos; política restringida por `SourceArn` al bucket.
- **IAM** — rol `mentoring-processor-role` con permisos acotados; rol OIDC `github-actions` (solo lectura) para CI.

## Decisiones de arquitectura clave

- **Un solo `aws_s3_bucket_notification`**: AWS solo admite una configuración de notificaciones por bucket; `queue` y `topic` van en el mismo recurso.
- **ARNs derivados de recursos** (`aws_recurso.nombre.atributo`), nunca literales hardcodeados.
- **Secretos en `.tfvars`** (gitignored): valores sensibles van por variable; no sensibles pueden tener `default` en `variables.tf`.
- **Estado local** (Pendiente): evaluar backend remoto S3 + DynamoDB lock.

## Roadmap

1. Modelo de datos de alumnos y resultados de simulados.
2. Lambda/endpoint para registrar respuestas del alumno.
3. Generación de aulas por tema/dificultad filtrando temas débiles.
4. Reportes mensuales/anuales por alumno y aula.
5. Resolver manejo de duplicados; evaluar backend remoto.

## Fuentes

- `README.md` — documento público (reclutadores).
- `doc/status.md` — bitácora técnica interna: hallazgos, deuda y log de cambios.
