resource "aws_iam_role" "student_api_role" {
  name = "mentoring-student-api-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_policy" "student_api_policy" {
  name        = "mentoring-student-api-policy"
  description = "Permissions for student API Lambda"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowReadStudents"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query"
        ]
        Resource = [
          aws_dynamodb_table.students.arn,
          "${aws_dynamodb_table.students.arn}/index/*"
        ]
      },
      {
        Sid    = "AllowWriteStudents"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:UpdateItem"
        ]
        Resource = aws_dynamodb_table.students.arn
      },
      {
        Sid    = "AllowCognitoRead"
        Effect = "Allow"
        Action = [
          "cognito-idp:GetUser"
        ]
        Resource = aws_cognito_user_pool.students.arn
      },
      {
        Sid    = "AllowReadCohorts"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem"
        ]
        Resource = aws_dynamodb_table.cohorts.arn
      },
      {
        Sid    = "AllowLambdaLogs"
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

resource "aws_iam_role_policy_attachment" "student_api_attach" {
  role       = aws_iam_role.student_api_role.name
  policy_arn = aws_iam_policy.student_api_policy.arn
}
