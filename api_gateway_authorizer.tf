data "aws_region" "current" {}

resource "aws_apigatewayv2_authorizer" "cognito" {
  api_id           = aws_apigatewayv2_api.mentoring_api.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "cognito-jwt-authorizer" # <-- Parámetro obligatorio faltante

  jwt_configuration {
    audience = [aws_cognito_user_pool_client.student_app.id]
    issuer   = "https://${aws_cognito_user_pool.students.endpoint}"
  }
}
