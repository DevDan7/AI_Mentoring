data "archive_file" "quiz_engine_zip" {
  type             = "zip"
  source_file      = "${path.module}/src/quiz_engine.py"
  output_path      = "${path.module}/quiz_engine_function.zip"
  output_file_mode = "0644" # hash determinista: no depende del umask local (CI usa 0644)
}

resource "aws_lambda_function" "quiz_engine" {
  filename      = data.archive_file.quiz_engine_zip.output_path
  function_name = "quiz-engine"
  role          = aws_iam_role.quiz_engine_role.arn
  handler       = "quiz_engine.lambda_handler"
  runtime       = "python3.12"
  timeout       = 25   # < 30 s de API Gateway; ver GENERATION_LOCK_STALE_SECONDS en quiz_engine.py
  memory_size   = 1024 # CPU escala con la memoria: con 256 MB el examen final superaba el timeout (30-Sep)

  source_code_hash = data.archive_file.quiz_engine_zip.output_base64sha256

  environment {
    variables = {
      QUESTIONS_TABLE    = aws_dynamodb_table.mentoring_questions_table.name
      QUIZZES_TABLE      = aws_dynamodb_table.quizzes.name
      QUIZ_RESULTS_TABLE = aws_dynamodb_table.quiz_results.name
      STUDENTS_TABLE     = aws_dynamodb_table.students.name
      COHORTS_TABLE      = aws_dynamodb_table.cohorts.name
    }
  }
}