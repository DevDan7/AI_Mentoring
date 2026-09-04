resource "aws_cognito_user_pool" "students" {
  name = "${var.project_name}-StudentsPool-${var.environment}"

  # Atributos requeridos del usuario
  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true

    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }

  schema {
    name                = "name"
    attribute_data_type = "String"
    required            = true
    mutable             = true

    string_attribute_constraints {
      min_length = 1
      max_length = 256
    }
  }

  # Permitir que el email sea usado como nombre de usuario para el login
  username_attributes = ["email"]

  # Confirmación automática vía email
  auto_verified_attributes = ["email"]

  # Política de contraseñas
  password_policy {
    minimum_length                   = 8
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = false
    require_uppercase                = true
    temporary_password_validity_days = 7
  }

  # Configuración del envío de emails de verificación
  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Service     = "Students"
  }
}

# 2. El App Client (Cliente para que el Frontend se conecte)
resource "aws_cognito_user_pool_client" "student_app" {
  name         = "${var.project_name}-StudentApp-${var.environment}"
  user_pool_id = aws_cognito_user_pool.students.id

  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_PASSWORD_AUTH"
  ]

  access_token_validity  = 1
  id_token_validity      = 1
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  allowed_oauth_flows_user_pool_client = true

  callback_urls = var.cognito_callback_urls
  logout_urls   = var.cognito_logout_urls

  prevent_user_existence_errors = "ENABLED"

}

# 3. Grupo de profesores para control de acceso
resource "aws_cognito_user_group" "teachers" {
  name         = "Teachers"
  user_pool_id = aws_cognito_user_pool.students.id
  description  = "Teachers group for mentoring platform - controls access to phase management endpoints"
  precedence   = 0
}