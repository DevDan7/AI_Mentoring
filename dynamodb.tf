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
    hash_key        = "Topic"
    projection_type = "ALL"
  }

  tags = {
    Name        = "mentoring-questions-table"
    Environment = "dev"
  }
}