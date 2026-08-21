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