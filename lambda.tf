# 1. Empaquetar el código automáticamente
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/src/processor.py"
  output_path = "${path.module}/lambda_function.zip"
}


# 2. Crear la función Lambda
resource "aws_lambda_function" "processor" {
  filename      = data.archive_file.lambda_zip.output_path
  function_name = "mentoring-exam-processor"
  role          = aws_iam_role.lambda_role.arn
  handler       = "processor.lambda_handler" # Archivo.Función
  runtime       = "python3.12"
  timeout       = 30 # La IA puede tardar, le damos tiempo
  memory_size   = 256
  reserved_concurrent_executions = 3

  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  # Variables de entorno para que el código sepa a dónde escribir
  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.mentoring_questions_table.name
    }
  }
}

# 3. El Disparador (Trigger): Conectar SQS con Lambda
resource "aws_lambda_event_source_mapping" "sqs_trigger" {
  event_source_arn = aws_sqs_queue.main_queue.arn
  function_name    = aws_lambda_function.processor.arn
  batch_size       = 1 # Procesamos una foto a la vez para no saturar
}