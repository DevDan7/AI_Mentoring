resource "aws_dynamodb_table" "cohorts" {
  name         = "${var.project_name}-Cohorts-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "CohortID"

  attribute {
    name = "CohortID"
    type = "S"
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Service     = "Cohorts"
  }
}
