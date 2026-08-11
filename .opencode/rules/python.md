# Reglas Python — AI Mentoring

Reglas de estilo y estructura para el código de aplicación (Lambdas en `src/`).

## Entorno

- **Python 3.12**; virtualenv `.venv` (no commitear).
- Dependencias en `requirements.txt`; paquetes mínimos (boto3).

## Estructura

- Handlers en `src/` como `processor.py` con `lambda_handler(event, context)`.
- Clientes boto3 inicializados a nivel de módulo, una sola vez.
- Configuración por variables de entorno con fallback seguro (ej. `os.environ.get('TABLE_NAME', '...')`).

## Estilo

- Imports de la stdlib primero, luego boto3/terceros.
- Sin comentarios que repitan el código; solo contexto de negocio si aporta.
- `print()` para logging en CloudWatch; nunca loggear secretos ni datos personales.
- Nombres descriptivos en inglés (el proyecto mezcla ES en comentarios de IaC; en código, inglés).

## Manejo de errores

- Validar mensajes de prueba/eventos inválidos y saltarlos (`continue`).
- En el handler Lambda: loggear el error y re-lanzar para que SQS reintente según la política de la cola.
- Des-URL-encodear keys de S3 (`urllib.parse.unquote_plus`).
- Parsear respuestas de Bedrock tras limpiar fences de markdown (```json).

## Verificación

- `python -m py_compile src/processor.py` sin errores.
- Revisar que el JSON del prompt de Bedrock pida estructura estricta y el código la valide antes de `put_item`.
