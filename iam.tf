# 1. El Rol (La entidad que la Lambda asumirá)
resource "aws_iam_role" "lambda_role" {
  name = "mentoring-processor-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

# 2. La Política (Los permisos que listamos arriba)
resource "aws_iam_policy" "lambda_policy" {
  name        = "mentoring-processor-policy"
  description = "Permissions for the mentoring processor Lambda"

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [
      {
        Sid    = "AllowReadFromMainQueue"
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.main_queue.arn
      },
      {
        Sid    = "AllowReadFromPhotosBucket"
        Effect = "Allow"
        Action = [
          "s3:GetObject"
        ]
        Resource = "${aws_s3_bucket.mentoring_exam_photos_bucket.arn}/*"
      },
      {
        Sid    = "AllowIAAnalysis"
        Effect = "Allow"
        Action = [
          "rekognition:DetectText",
          "bedrock:InvokeModel"
        ]
        Resource = "*"
      },
      {
        Sid    = "AllowWriteToDynamoDB"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem"
        ]
        Resource = aws_dynamodb_table.mentoring_questions_table.arn
      },
      {
        Sid    = "AllowWriteLambdaLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# 3. Unir el Rol con la Política
resource "aws_iam_role_policy_attachment" "lambda_attach" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}