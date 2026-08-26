---
description: Implementa una tarea aprobada. Sigue los patrones del repo, edita los archivos necesarios y verifica con terraform validate.
agent: developer
---

Implementa la siguiente tarea en el proyecto AI Mentoring:

**Solicitud:** $ARGUMENTS

## Restricciones de Alcance (CRÍTICO)

- **NO toques** archivos en `.opencode/agents/`, `.opencode/commands/`, `.opencode/skills/` a menos que la solicitud lo pida explícitamente.
- **NO crees** archivos nuevos sin que la solicitud lo indique.
- **NO modifiqués** `AGENTS.md`, `opencode.json`, ni ningún archivo de configuración de OpenCode.
- **NO modifiqués** `src/processor.py` u otros archivos de código a menos que la tarea sea específicamente sobre ellos.
- **NO detectes** deuda técnica en otros archivos y la corrijas sin que se te pida. Mantén el foco en la solicitud exacta.
- Si necesitas modificar un archivo fuera del alcance, **detente y pregunta** antes de continuar.

## Proceso

1. Lee **únicamente** los archivos mencionados en la solicitud o directamente necesarios para ella.
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
