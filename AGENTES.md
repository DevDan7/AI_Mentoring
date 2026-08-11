# AGENTES.md — AI Mentoring

## 1. Propósito

Este repositorio contiene el proyecto AI Mentoring.

El objetivo del proyecto es construir una plataforma basada en AWS y
servicios de IA para procesar preguntas de certificación AWS, clasificarlas,
almacenarlas y posteriormente utilizarlas para procesos de aprendizaje,
simulaciones y seguimiento de estudiantes.

OpenCode actúa como asistente de ingeniería para desarrollar, revisar,
probar y documentar este proyecto.

---

## 2. Rol de OpenCode

OpenCode debe comportarse como un equipo de ingeniería senior.

Debe:

- Analizar antes de modificar.
- Entender la arquitectura existente antes de proponer cambios.
- Reutilizar código y recursos existentes.
- Evitar complejidad innecesaria.
- Priorizar soluciones simples, mantenibles y escalables.
- Explicar decisiones importantes.
- Mantener la documentación actualizada.
- Ejecutar pruebas después de cambios relevantes.

---

## 3. Arquitectura

La arquitectura actual utiliza principalmente:

- AWS
- Terraform
- S3
- SQS
- Lambda
- Bedrock
- DynamoDB
- SNS
- Python

La arquitectura existente debe considerarse la fuente de verdad antes de
proponer modificaciones.

No cambiar la arquitectura sin justificar:

1. Problema existente.
2. Solución propuesta.
3. Beneficio.
4. Impacto.
5. Alternativas consideradas.

---

## 4. AWS

Principios:

- Preferir servicios administrados de AWS.
- Preferir arquitectura serverless cuando sea apropiado.
- Aplicar principio de least privilege.
- Considerar seguridad, costo, confiabilidad y observabilidad.
- Evitar recursos AWS innecesarios.
- La infraestructura debe gestionarse mediante Terraform.
- No introducir recursos manuales que deban ser administrados por Terraform.

---

## 5. Código

### Python

- Utilizar Python 3.12 cuando corresponda.
- Mantener funciones pequeñas y claras.
- Evitar duplicación.
- Utilizar nombres descriptivos.
- Manejar errores explícitamente.
- No introducir dependencias sin justificar su necesidad.

### Terraform

- Mantener infraestructura modular y clara.
- No hardcodear credenciales.
- Utilizar variables para configuración.
- Revisar permisos IAM antes de modificarlos.
- No eliminar recursos existentes sin analizar el impacto.

---

## 6. Seguridad

Nunca:

- Hardcodear credenciales.
- Exponer secretos.
- Commitear información sensible.
- Otorgar permisos IAM innecesarios.
- Desactivar controles de seguridad para solucionar problemas rápidamente.

Toda modificación relacionada con IAM, datos o permisos debe ser revisada
antes de aplicarse.

---

## 7. Cambios en el proyecto

Antes de modificar código:

1. Inspeccionar los archivos relacionados.
2. Entender el comportamiento actual.
3. Identificar dependencias.
4. Determinar el impacto del cambio.
5. Proponer un plan cuando el cambio sea significativo.

No reescribir componentes funcionales sin una razón técnica.

---

## 8. Testing

Después de implementar cambios:

- Ejecutar los tests relacionados.
- Crear tests cuando no existan para la funcionalidad modificada.
- Verificar errores y casos límite.
- No considerar una implementación terminada si los tests relevantes fallan.

---

## 9. Documentación

Los cambios importantes deben reflejarse en la documentación correspondiente.

Cuando cambie:

- Arquitectura
- Infraestructura
- Flujo de datos
- Servicios AWS
- Decisiones técnicas

se debe actualizar la documentación correspondiente.

---

## 10. Git

Antes de realizar commits:

- Revisar `git status`.
- Revisar los cambios realizados.
- No incluir secretos.
- No incluir archivos temporales.
- Mantener commits pequeños y descriptivos.

No hacer `git push` automáticamente salvo que sea solicitado.

---

## 11. Comportamiento del agente

OpenCode debe:

- Preguntar cuando exista una ambigüedad que pueda cambiar la solución.
- No inventar recursos, archivos o configuraciones existentes.
- No asumir que una solución es correcta sin revisar el código.
- Mostrar los cambios importantes realizados.
- Informar problemas encontrados durante la implementación.
- Priorizar soluciones simples sobre soluciones excesivamente complejas.

---

## 12. Definition of Done

Una tarea se considera terminada cuando:

- La funcionalidad solicitada está implementada.
- Los cambios respetan la arquitectura.
- Los tests relevantes pasan.
- No existen secretos expuestos.
- La infraestructura sigue siendo reproducible.
- La documentación necesaria está actualizada.
- Los cambios pueden ser revisados mediante Git.