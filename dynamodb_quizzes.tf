resource "aws_dynamodb_table" "quizzes" {
  name           = "${var.project_name}-Quizzes-${var.environment}"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "QuizID"
  attribute {
    name = "QuizID"
    type = "S"
  }
  attribute {
    name = "StudentID"
    type = "S"
  }
  attribute {
    name = "Topic"
    type = "S"
  }

  attribute {
    name = "Difficulty"
    type = "S"
  }

  attribute {
    name = "QuestionCount"
    type = "N"
  }

  attribute {
    name = "Score"
    type = "N"
  }

  attribute {
    name = "Status"
    type = "S"
  }

  attribute {
    name = "CreatedAt"
    type = "S"
  }
  global_secondary_index {
    name            = "StudentIndex"
    projection_type = "ALL"
    key_schema {
      attribute_name = "StudentID"
      key_type       = "HASH"      # Partition Key del GSI
    }
  }
  tags = {
    Environment = var.environment
    Project     = var.project_name
    Service     = "Quizzes"
  }
}