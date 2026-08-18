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
    name = "QuestionID"
    type = "S"
  }

  attribute {
    name = "GivenAnswer"
    type = "S"
  }

  attribute {
    name = "IsCorrect"
    type = "S"
  }
  attribute {
  name = "Timestamp"
  type = "S"
}
global_secondary_index {
    name            = "StudentResultsIndex"
    projection_type = "ALL"

    key_schema {
      attribute_name = "StudentID"
      key_type       = "HASH"      # Partition Key del GSI
    }

    key_schema {
      attribute_name = "Timestamp"
      key_type       = "RANGE"     # Sort Key del GSI
    }
  }
  tags = {
    Environment = var.environment
    Project     = var.project_name
    Service     = "QuizResults"
  }
}