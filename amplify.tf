# =============================================================
# AWS Amplify Hosting — Frontend Estático
# =============================================================
resource "aws_amplify_app" "frontend" {
  name       = "${var.project_name}-frontend-${var.environment}"
  repository = var.gh_repository

  access_token         = var.github_access_token
  iam_service_role_arn = aws_iam_role.amplify_role.arn

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

  environment_variables = {
    API_URL              = var.api_gateway_url
    COGNITO_REGION       = var.aws_region
    COGNITO_USER_POOL_ID = var.cognito_user_pool_id
    COGNITO_CLIENT_ID    = var.cognito_client_id
  }

  enable_branch_auto_build = true
  platform                 = "WEB"

  tags = {
    Name        = "${var.project_name}-frontend"
    Environment = var.environment
  }
}

resource "aws_amplify_branch" "main" {
  app_id      = aws_amplify_app.frontend.id
  branch_name = "main"

  enable_auto_build = true
  stage             = "PRODUCTION"

  tags = {
    Environment = var.environment
  }
}
