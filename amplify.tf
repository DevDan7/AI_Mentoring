# =============================================================
# AWS Amplify Hosting — Frontend estatico
# Reemplaza la infraestructura anterior (S3 + CloudFront).
# Cada push a la rama 'main' activa build + deploy automatico.
# =============================================================

resource "aws_amplify_app" "frontend" {
  name       = "${var.project_name}-frontend-${var.environment}"
  repository = "https://github.com/DevDan7/AI_Mentoring"

  # GitHub Personal Access Token (scope: repo)
  # Permite a Amplify clonar el repo y hacer deploy
  access_token = var.github_access_token

  # Build spec para sitio estatico (HTML puro, sin framework)
  # Amplify ejecuta esto en cada push a una rama conectada
  build_spec = <<-EOT
    version: 1
    frontend:
      phases:
        preBuild:
          commands: []
        build:
          commands:
            - echo "Static site - copying files"
        postBuild:
          commands: []
      artifacts:
        baseDirectory: src/frontend
        files:
          - "**/*"
  EOT

  # Variables de entorno inyectadas al frontend
  # Reemplazan el config.js hardcodeado
  environment_variables = {
    API_URL              = var.api_gateway_url
    COGNITO_REGION       = var.aws_region
    COGNITO_USER_POOL_ID = var.cognito_user_pool_id
    COGNITO_CLIENT_ID    = var.cognito_client_id
  }

  # Build automatico en cada push a ramas conectadas
  enable_branch_auto_build = true

  # Sitio estatico (no SSR)
  platform = "WEB"

  tags = {
    Name        = "${var.project_name}-frontend"
    Environment = var.environment
  }
}

# Rama principal conectada a produccion
resource "aws_amplify_branch" "main" {
  app_id      = aws_amplify_app.frontend.id
  branch_name = "main"

  enable_auto_build = true
  stage             = "PRODUCTION"

  tags = {
    Environment = var.environment
  }
}
