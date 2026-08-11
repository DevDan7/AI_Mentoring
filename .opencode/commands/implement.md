---
description: Implementa una tarea aprobada. Sigue los patrones del repo, edita los archivos necesarios y verifica con terraform validate.
agent: developer
---

Implementa la siguiente tarea en el proyecto AI Mentoring:

**Solicitud:** $ARGUMENTS

## Proceso

1. Lee los archivos afectados y respeta sus convenciones.
2. Implementa el cambio mínimo que cumpla la solicitud.
3. Código de aplicación en `src/`; infraestructura en la raíz (`.tf`).
4. Usa referencias a recursos (`aws_recurso.nombre.atributo`), nunca ARNs hardcodeados ni datos sensibles en el código.
5. No dupliques recursos que gestionan el mismo objeto AWS.
6. Verifica: `terraform validate` (y `terraform plan` si hay credenciales).
7. Actualiza `doc/status.md` si el cambio impacta la arquitectura o el roadmap.

## Al terminar

- Resumen de cambios por archivo.
- Comandos de verificación ejecutados y resultado.
- Nota de cualquier hallazgo o deuda técnica detectada.
