resource "aws_dynamodb_table" "mentoring_questions_table" {
  name         = "MentoringQuestions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "QuestionID"

  attribute {
    name = "QuestionID"
    type = "S"
  }

  attribute {
    name = "Topic"
    type = "S"
  }

  global_secondary_index {
    name            = "TopicIndex"
    projection_type = "ALL"
    key_schema {
      attribute_name = "Topic"
      key_type       = "HASH"     
    }
  }

  tags = {
    Name        = "mentoring-questions-table"
    Environment = "dev"
  }
}