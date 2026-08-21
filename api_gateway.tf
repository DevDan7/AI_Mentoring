# 1. Grupo de logs para monitoreo de peticiones HTTP en CloudWatch
resource "aws_cloudwatch_log_group" "api_gw" {
  name              = "/aws/apigateway/${var.project_name}-api-${var.environment}"
  retention_in_days = 7

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

# 2. Definición principal de HTTP API Gateway
resource "aws_apigatewayv2_api" "mentoring_api" {
  name          = "${var.project_name}-api-${var.environment}"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers = ["Authorization", "Content-Type"]
    max_age       = 300
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

# 3. Stage por defecto ($default) con Throttling y Logs
resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.mentoring_api.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit  = 50
    throttling_burst_limit = 100
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gw.arn
    format = jsonencode({
      requestId               = "$context.requestId"
      ip                      = "$context.identity.sourceIp"
      requestTime             = "$context.requestTime"
      httpMethod              = "$context.httpMethod"
      routeKey                = "$context.routeKey"
      status                  = "$context.status"
      protocol                = "$context.protocol"
      responseLength          = "$context.responseLength"
      authorizerError         = "$context.authorizer.error"
      integrationErrorMessage = "$context.integrationErrorMessage"
    })
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}