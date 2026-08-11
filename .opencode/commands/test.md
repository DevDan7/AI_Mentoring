---
description: Ejecuta las verificaciones del proyecto (terraform validate/plan, compilación Python, revisión de documentación).
agent: developer
---

Ejecuta las pruebas y verificaciones correspondientes en el proyecto AI Mentoring.

**Ámbito:** $ARGUMENTS

## Verificaciones según el ámbito

### Infraestructura
- `terraform validate` — sin errores.
- Si hay credenciales AWS: `terraform plan` — revisar que no destruya recursos ni cree duplicados (especialmente `aws_s3_bucket_notification`).

### Código Python
- `python -m py_compile src/processor.py` — sin errores de sintaxis.
- Revisión manual del flujo: parsing del evento SQS, OCR, prompt Bedrock, limpieza de markdown y `put_item`.

### Documentación
- `doc/status.md` coherente con el estado real del repo.
- `README.md` no promete funcionalidades inexistentes.

## Salida

- Lista de chequeos ejecutados y resultado (PASS/FAIL).
- Cualquier error encontrado con la corrección sugerida.
