variable "notification_email" {
  description = "Email para notificaciones de SNS"
  type        = string
  sensitive   = true
}

variable "project_name" {
  description = "Name of the project used in resource naming"
  type        = string
}

variable "environment" {
  description = "Deployment environment used in resource naming"
  type        = string
}

variable "cognito_callback_urls" {
  description = "URLs de callback permitidas para Cognito OAuth"
  type        = list(string)
  default     = ["http://localhost:3000/callback"]
}

variable "cognito_logout_urls" {
  description = "URLs de logout permitidas para Cognito OAuth"
  type        = list(string)
  default     = ["http://localhost:3000/logout"]
}

# =============================================================
# Amplify Hosting
# =============================================================

variable "github_access_token" {
  description = "GitHub Personal Access Token para Amplify (scope: repo)"
  type        = string
  sensitive   = true
}

variable "aws_region" {
  description = "Region de AWS para Cognito y servicios backend"
  type        = string
  default     = "us-east-1"
}

variable "api_gateway_url" {
  description = "URL base del API Gateway HTTP API"
  type        = string
}

variable "cognito_user_pool_id" {
  description = "ID del User Pool de Cognito para el frontend"
  type        = string
}

variable "cognito_client_id" {
  description = "ID del App Client de Cognito para el frontend"
  type        = string
}

variable "gh_repository" {
  description = "GitHub repository URL for the Amplify app"
  type        = string
}