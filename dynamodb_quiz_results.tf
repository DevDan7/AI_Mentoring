resource "aws_dynamodb_table" "quiz_results" {
  name         = "${var.project_name}-QuizResults-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "ResultID"

  attribute {
    name = "ResultID"
    type = "S"
  }

  attribute {
    name = "QuizID"
    type = "S"
  }

  attribute {
    name = "StudentID"
    type = "S"
  }

  attribute {
    name = "Timestamp"
    type = "S"
  }

  global_secondary_index {
    name            = "QuizIndex"
    hash_key        = "QuizID"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "StudentIndex"
    hash_key        = "StudentID"
    range_key       = "Timestamp"
    projection_type = "ALL"
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Service     = "QuizResults"
  }
}
