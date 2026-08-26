---
description: Planifica una tarea antes de implementarla. Investiga el estado actual, propone el enfoque y espera confirmación.
agent: architect
---

Planifica la siguiente tarea del proyecto AI Mentoring:

**Solicitud:** $ARGUMENTS

## Restricciones de Alcance

- **NO toques** archivos en `.opencode/agents/`, `.opencode/commands/`, `.opencode/rules/` a menos que la solicitud lo pida explícitamente.
- **NO crees** archivos nuevos sin que la solicitud lo indique.
- **NO modifiqués** `AGENTS.md`, `opencode.json`, ni ningún archivo de configuración de OpenCode.
- **NO toques** `src/processor.py` u otros archivos de código a menos que la tarea sea específicamente sobre ellos.
- Tu trabajo es **planificar**, no implementar. Presenta el plan y espera confirmación.

## Proceso

1. Lee el contexto necesario: `README.md`, `doc/status.md`, y los archivos afectados.
2. Analiza el estado actual y qué exige el cambio.
3. Propón un plan concreto: archivos a tocar, pasos, servicios AWS implicados y consideraciones de seguridad/costo.
4. Enumera los riesgos y alternativas si existen.
5. **No implementes nada**: presenta el plan y espera la aprobación antes de continuar.

## Formato de salida

- Objetivo del cambio.
- Análisis breve del estado actual.
- Plan paso a paso.
- Riesgos / consideraciones.
