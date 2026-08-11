---
name: aws-serverless
description: Patrones y buenas prácticas de arquitectura serverless en AWS para este repo. Usar cuando se escriba o revise infraestructura Terraform (S3, SQS, Lambda, DynamoDB, SNS, IAM) o se diseñe el flujo de eventos.
---

# AWS Serverless — Patrones del Proyecto

## Servicios usados

- **Amazon S3**: almacenamiento de objetos; dispara eventos `s3:ObjectCreated:*`.
- **Amazon SQS**: cola principal + DLQ para desacoplar ingesta de procesamiento.
- **AWS Lambda**: procesador Python; trigger por evento source mapping de SQS.
- **Amazon DynamoDB**: almacenamiento de preguntas; `PAY_PER_REQUEST`; GSI para consultas por tema.
- **Amazon SNS**: notificaciones por email.
- **Amazon Rekognition**: OCR (`DetectText`).
- **Amazon Bedrock**: modelo Claude Haiku 4.5 para estructurar respuestas.
- **IAM**: roles con principio de menor privilegio; OIDC para GitHub Actions.

## Reglas de infraestructura (Terraform)

- **Nunca dos recursos gestionando el mismo objeto** (ej. un solo `aws_s3_bucket_notification` por bucket). Dos recursos causan que cada `apply` sobrescriba la configuración anterior.
- **Referencias por atributos**, no ARNs hardcodeados: `aws_bucket.recurso.arn`.
- **Permisos acotados**: cada statement IAM apunta al ARN del recurso específico; restringir con condiciones `aws:SourceArn` cuando el servicio recibe eventos de terceros.
- **Resiliencia**: DLQ con `maxReceiveCount` razonable; considerar idempotencia y manejo de duplicados.
- **Costos**: `PAY_PER_REQUEST` para DynamoDB, `memory_size` mínimo suficiente, sin recursos ociosos.
- Validar siempre con `terraform validate` (y `terraform plan` contra el estado real cuando haya credenciales).

## Trampas comunes

- Política SQS/SNS sin condición `aws:SourceArn` → cualquier recurso puede inyectar mensajes.
- Cambiar el nombre de un bucket en el estado sin actualizar las referencias literales.
- Timeouts de Lambda muy cortos para operaciones de IA (Bedrock/OCR).
- Provincias/servicios activados en una región distinta a `us-east-1`.
