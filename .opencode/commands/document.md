---
description: Actualiza la documentación del proyecto (README, doc/status.md) reflejando los cambios recientes.
agent: developer
---

Actualiza la documentación del proyecto AI Mentoring.

**Solicitud:** $ARGUMENTS

## Reglas

- `README.md` es el documento público: arquitectura, stack y cómo deployar. Mantenerlo simple y preciso.
- `doc/status.md` es la bitácora técnica interna: hallazgos/deuda, brechas y log de cambios.
  - Marca como resueltos los hallazgos que ya se corrigieron (usando ~~tachado~~ y fecha).
  - Registra nueva deuda técnica detectada.
  - Añade entradas al "Log de cambios" con fecha y descripción de lo hecho.
  - Si hubo un problema de debugging interesante, añade un sub-bullet "Hallazgo de debugging".
- Nunca inventes cambios que no se hicieron ni fechas incorrectas.
- No crees documentos nuevos salvo que se pida explícitamente.

## Salida

- Lista de secciones editadas.
- Nota de cualquier inconsistencia detectada entre docs y código.
