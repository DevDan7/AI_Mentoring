---
description: Revisa cambios o un diff del proyecto buscando errores, seguridad y deuda técnica.
agent: reviewer
---

Revisa los siguientes cambios del proyecto AI Mentoring:

**Alcance:** $ARGUMENTS

## Proceso

1. Identifica los archivos y líneas afectadas.
2. Busca: errores funcionales (recursos duplicados, referencias rotas), fallas de seguridad (secretos, permisos amplios), deuda técnica (hardcodeos, código muerto) y desalineación con los patrones del repo.
3. Reporta con severidad (Crítico / Medio / Menor), archivo:línea, problema y solución sugerida.

## Salida

- Resumen del cambio.
- Hallazgos ordenados por severidad.
- Veredicto: aprobar / aprobar con cambios / rechazar.

No edites archivos durante la revisión.
