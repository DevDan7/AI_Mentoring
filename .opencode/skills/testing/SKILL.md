---
name: testing
description: Estrategia de verificación para este proyecto. Usar antes de declarar terminada cualquier tarea que toque infraestructura Terraform, código Python o documentación.
---

# Testing — Verificación del Proyecto

## Infraestructura (Terraform)

- Ejecutar siempre `terraform validate` tras cualquier cambio en `.tf`.
- Cuando haya credenciales AWS válidas, ejecutar `terraform plan` y revisar el diff: nada que destruya recursos por accidente, ningún recurso duplicado.
- Con el CI OIDC configurado, los PRs corren `terraform plan` automáticamente (solo lectura) — revisar el resultado en GitHub Actions.
- Confirmar que los cambios no alteran la configuración de notificaciones de S3 (un solo `aws_s3_bucket_notification`).

## Código Python (Lambda)

- Verificación estática: `python -m py_compile src/processor.py` para detectar errores de sintaxis.
- Revisar la lógica de parsing del JSON de Bedrock (limpieza de markdown) antes de `json.loads`.
- Probar localmente con un evento simulado de SQS si es posible.

## Documentación

- `doc/status.md` refleja el estado real: hallazgos resueltos marcados, nuevas deudas registradas, log de cambios actualizado con fecha.
- `README.md` no describe características que no existen.

## Checklist final de una tarea

1. `terraform validate` pasa sin errores.
2. Diff revisado (no hay destrucciones ni duplicados).
3. Sin secretos ni datos personales en código commiteado.
4. Bitácora `doc/status.md` actualizada.
