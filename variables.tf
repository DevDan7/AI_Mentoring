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