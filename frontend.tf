# =============================================================
# Frontend hosting — migrado a AWS Amplify Hosting (amplify.tf)
#
# La infraestructura anterior (S3 + CloudFront + OAC + bucket
# policy) fue eliminada y reemplazada por aws_amplify_app +
# aws_amplify_branch en amplify.tf.
#
# Deploy: cada push a la rama 'main' activa build + deploy
# automatico via Amplify Hosting.
# =============================================================
