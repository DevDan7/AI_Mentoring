resource "aws_dynamodb_table" "quizzes" {
  name         = "${var.project_name}-Quizzes-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "QuizID"

  attribute {
    name = "QuizID"
    type = "S"
  }

  attribute {
    name = "StudentID"
    type = "S"
  }

  global_secondary_index {
    name            = "StudentIndex"
    hash_key        = "StudentID"
    projection_type = "ALL"
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Service     = "Quizzes"
  }
}
