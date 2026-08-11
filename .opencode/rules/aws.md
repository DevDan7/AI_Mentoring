# Reglas AWS — AI Mentoring

Reglas de uso de servicios AWS en este proyecto.

## Configuración

- **Región**: `us-east-1` (definida en `provider.tf`).
- **Provider AWS** `~> 6.0`; provider `archive` `~> 2.4`.
- Infraestructura 100% IaC con Terraform; sin recursos creados a mano en la consola.

## Servicios

- **S3**: bucket `daniel-mentoring-exam-photos-edn-dev`. Una sola configuración de notificaciones (SQS + SNS juntos en `aws_s3_bucket_notification`).
- **SQS**: cola `mentoring-main-queue` con DLQ `mentoring-dlq` (`maxReceiveCount=4`); política de cola restringida por `aws:SourceArn` al bucket.
- **Lambda**: `mentoring-exam-processor`, Python 3.12, 256 MB, timeout 30s, trigger SQS con `batch_size=1`.
- **DynamoDB**: tabla `MentoringQuestions`, `QuestionID` (PK) + GSI `TopicIndex`, `PAY_PER_REQUEST`.
- **SNS**: tópico `AI-Mentoring-notifications-dev-daniel`; suscripción email vía variable `notification_email`; política restringida por `aws:SourceArn`.
- **Bedrock**: modelo Claude Haiku 4.5 (`us.anthropic.claude-haiku-4-5-20251001-v1:0`).
- **Rekognition**: `DetectText` para OCR.

## CI/CD

- GitHub Actions autentica por OIDC con el rol `ai-mentoring-github-actions` (solo lectura, `ReadOnlyAccess`).
- El rol asume el claim `repo:DevDan7@152210372/AI_Mentoring@1326486822:*` — no alterar sin verificar CloudTrail.

## Prohibido

- Crear recursos fuera de Terraform.
- Cambiar región sin actualizar `provider.tf` y revisar el resto de referencias.
- Modificar la trust policy OIDC a ciegas (usar CloudTrail para confirmar claims).
