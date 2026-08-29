resource "aws_dynamodb_table" "students" {
  name         = "${var.project_name}-Students-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "StudentID"

  attribute {
    name = "StudentID"
    type = "S"
  }

  attribute {
    name = "Email"
    type = "S"
  }

  attribute {
    name = "CohortID"
    type = "S"
  }

  global_secondary_index {
    name            = "EmailIndex"
    hash_key        = "Email"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "CohortIndex"
    hash_key        = "CohortID"
    projection_type = "ALL"
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Service     = "Students"
  }
}