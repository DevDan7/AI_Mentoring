output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.students.id
}

output "cognito_client_id" {
  value = aws_cognito_user_pool_client.student_app.id
}

output "cognito_user_pool_arn" {
  description = "ARN del User Pool para configurar el Authorizer de API Gateway"
  value       = aws_cognito_user_pool.students.arn
}