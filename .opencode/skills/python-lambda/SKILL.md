---
name: python-lambda
description: Patrones de código para las AWS Lambdas en Python de este repo. Usar cuando se escriba o modifique código en src/ (handlers, boto3, manejo de errores, parsing de respuestas de Bedrock).
---

# Python Lambda — Patrones del Proyecto

## Estructura del handler

- Runtime **Python 3.12**; archivo `src/processor.py` con función `lambda_handler(event, context)`.
- Clientes boto3 inicializados a nivel de módulo (reutilización en invocaciones en caliente).
- Configuración vía variables de entorno (`TABLE_NAME`), con valor por defecto seguro.
- Logs con `print()` para CloudWatch (sin secretos).

## Manejo de eventos

- Los triggers de SQS entregan `event['Records']`; cada record tiene `body` (JSON).
- Saltar mensajes de prueba/invalidos sin texto detectado (`continue` en vez de fallar).
- Des-URL-encodear la key de S3 con `urllib.parse.unquote_plus`.
- Rescatar la respuesta de IA entre bloques markdown (```json ... ```) antes de `json.loads`.
- Error: loggear `str(e)` y re-lanzar para que SQS reintente según la política de la cola.

## Flujo del procesador

1. Parsear mensaje SQS → confirmar que trae un evento S3.
2. Rekognition `detect_text` sobre el objeto S3 → concatenar líneas (`Type == 'LINE'`).
3. Prompt a Bedrock (Claude) pidiendo JSON estricto: `topic`, `explanation`, `difficulty`.
4. Limpiar y parsear el JSON de la respuesta.
5. `put_item` en DynamoDB con `QuestionID` (UUID) + `CreatedAt` (ISO).

## Reglas

- No loggear datos personales ni claves.
- Usar `datetime.now().isoformat()` para timestamps.
- Mantener cada paso en bloques pequeños y legibles; sin comentarios que repitan el código.
