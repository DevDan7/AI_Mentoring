# Reglas de Arquitectura — AI Mentoring

Reglas no negociables de diseño y evolución de la arquitectura. Deben cumplirse en toda tarea que toque diseño o infraestructura.

## Patrones de referencia

- Pipeline de referencia en `.opencode/skills/ai-mentoring-architecture/SKILL.md` y `doc/status.md`.
- Toda evolución debe documentarse en `doc/status.md`.

## Reglas

1. **Un recurso AWS por objeto gestionado**: jamás dos `aws_*_notification`, configs o settings que apunten al mismo objeto (AWS sobrescribe configuraciones completas).
2. **Referencias, no literales**: todo ARN se deriva de un recurso (`aws_recurso.nombre.atributo`). Prohibido hardcodear ARNs o nombres de bucket.
3. **Desacoplamiento**: la ingesta (S3) nunca habla directo con el procesador (Lambda); siempre vía cola SQS.
4. **Resiliencia**: toda cola de eventos tiene DLQ; el procesador debe soportar reintentos sin romperse.
5. **Costos**: DynamoDB en `PAY_PER_REQUEST`; recursos efímeros o sin estado ocioso; evaluar costo antes de añadir servicios.
6. **Menor privilegio**: cada permiso IAM acotado al ARN del recurso; condiciones `aws:SourceArn` para servicios que reciben eventos de terceros.
7. **Single source of truth**: la configuración de un servicio vive en el recurso que lo define; nada duplicado entre archivos.
8. **Sensible ≠ repo**: secretos y datos personales viajan por variables `.tfvars` (gitignored), jamás en código o estado commiteado.
9. **Verificación obligatoria**: `terraform validate` antes de declarar terminado; `terraform plan` cuando haya credenciales.
