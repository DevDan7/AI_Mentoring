data "archive_file" "student_api_zip" {
  type        = "zip"
  source_file = "${path.module}/src/student_api.py"
  output_path = "${path.module}/student_api_function.zip"
}

resource "aws_lambda_function" "student_api" {
  filename      = data.archive_file.student_api_zip.output_path
  function_name = "mentoring-student-api"
  role          = aws_iam_role.student_api_role.arn
  handler       = "student_api.lambda_handler"
  runtime       = "python3.12"
  timeout       = 15
  memory_size   = 256

  source_code_hash = data.archive_file.student_api_zip.output_base64sha256

  environment {
    variables = {
      COGNITO_USER_POOL_ID = aws_cognito_user_pool.students.id
      COGNITO_CLIENT_ID    = aws_cognito_user_pool_client.student_app.id
      STUDENTS_TABLE       = aws_dynamodb_table.students.name
      COHORTS_TABLE        = aws_dynamodb_table.cohorts.name
      QUIZZES_TABLE        = aws_dynamodb_table.quizzes.name
    }
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Service     = "Students"
  }
}
