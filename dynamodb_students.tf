resource "aws_dynamodb_table" "students" {
  name           = "${var.project_name}-Students-${var.environment}"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "StudentID"
  attribute {
    name = "StudentID"
    type = "S"
  }
  attribute {
    name = "Email"
    type = "S"
  }
  attribute {
    name = "Name"
    type = "S"
  }

  attribute {
    name = "CreatedAt"
    type = "S"
  }

  attribute {
    name = "SessionExpiresAt"
    type = "S"
  }

  attribute {
    name = "TopicsWeak"
    type = "S"
  }

  attribute {
    name = "TotalQuizzes"
    type = "N"
  }

  attribute {
    name = "AvgScore"
    type = "N"
  }
  global_secondary_index {
    name            = "EmailIndex"
    projection_type = "ALL"
    key_schema {
      attribute_name = "Email"
      key_type       = "HASH"  
    }
  }
  tags = {
    Environment = var.environment
    Project     = var.project_name
    Service     = "Students"
  }
}