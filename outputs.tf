output "cognito_user_pool_id" {
  description = "ID del User Pool de Cognito"
  value       = aws_cognito_user_pool.students.id
}

output "cognito_client_id" {
  description = "ID del App Client de Cognito"
  value       = aws_cognito_user_pool_client.student_app.id
}

output "cognito_user_pool_arn" {
  description = "ARN del User Pool para configurar el Authorizer de API Gateway"
  value       = aws_cognito_user_pool.students.arn
}

output "api_gateway_url" {
  description = "URL base pública de la HTTP API Gateway"
  value       = aws_apigatewayv2_api.mentoring_api.api_endpoint
}

output "api_gateway_id" {
  description = "ID de la API Gateway para configurar el frontend"
  value       = aws_apigatewayv2_api.mentoring_api.id
}