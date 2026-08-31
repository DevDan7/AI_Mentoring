data "archive_file" "quiz_engine_zip" {
  type        = "zip"
  source_file = "${path.module}/src/quiz_engine.py"
  output_path = "${path.module}/quiz_engine_function.zip"
}

resource "aws_lambda_function" "quiz_engine" {
  filename      = data.archive_file.quiz_engine_zip.output_path
  function_name = "quiz-engine"
  role          = aws_iam_role.quiz_engine_role.arn
  handler       = "quiz_engine.lambda_handler"
  runtime       = "python3.12"
  timeout       = 15
  memory_size   = 256

  source_code_hash = data.archive_file.quiz_engine_zip.output_base64sha256

  environment {
    variables = {
      QUESTIONS_TABLE    = aws_dynamodb_table.mentoring_questions_table.name
      QUIZZES_TABLE      = aws_dynamodb_table.quizzes.name
      QUIZ_RESULTS_TABLE = aws_dynamodb_table.quiz_results.name
      STUDENTS_TABLE     = aws_dynamodb_table.students.name
    }
  }
}