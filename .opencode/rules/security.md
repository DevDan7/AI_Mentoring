# Reglas de Seguridad — AI Mentoring

Reglas no negociables de seguridad para este repositorio.

## Secretos y datos personales

1. **Prohibido** commitear secretos, credenciales, emails personales o tokens en cualquier archivo.
2. Valores sensibles van en `variables.tf` (con `sensitive = true`) y el valor real en `terraform.tfvars` (excluido por `.gitignore` con `*.tfvars`).
3. Verificar `git status` y `git diff` antes de commitear para confirmar que ningún secreto entró al repo.
4. Si un secreto se expone: rotarlo e historizar el incidente en `doc/status.md`.

## Estado de Terraform

- `terraform.tfstate` y `.tfstate.backup` contienen ARNs/IDs sensibles: **no** commitearlos. Backend remoto (S3 + DynamoDB lock) pendiente — evaluar.
- `.terraform/` y `.venv/` no se commitear.

## IAM y políticas

- Principio de menor privilegio: cada statement acotado a los ARNs necesarios.
- Servicios que reciben eventos de terceros (SQS, SNS) restringen con condición `aws:SourceArn` al bucket exacto.
- El rol de CI (`github-actions`) es de **solo lectura**; no debe poder aplicar cambios.

## CI/CD (OIDC)

- Sin credenciales de larga duración en GitHub Secrets para Terraform; usar OIDC.
- Trust policy del rol OIDC con `aud` y `sub` exactos; verificar claims con CloudTrail ante fallos de asunción.
