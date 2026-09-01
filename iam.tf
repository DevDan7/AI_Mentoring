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

# 4. GitHub Actions OIDC Configuration
data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_role" "github_actions" {
  name = "ai-mentoring-github-actions"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = data.aws_iam_openid_connect_provider.github.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          }
          StringLike = {
            "token.actions.githubusercontent.com:sub" = "repo:DevDan7@152210372/AI_Mentoring@1326486822:*"
          }
        }
      }
    ]
  })
}

# Nueva política para permitir despliegue mediante Terraform
resource "aws_iam_policy" "terraform_cicd_policy" {
  name        = "terraform-cicd-policy"
  description = "Permissions for Terraform CI/CD"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:*",
          "sqs:*",
          "sns:*",
          "lambda:*",
          "dynamodb:*",
          "apigateway:*",
          "cognito-idp:*",
          "cloudfront:*",
          "amplify:*",
          "logs:*",
          "iam:PassRole",
          "iam:CreateRole",
          "iam:DeleteRole",
          "iam:UpdateRole",
          "iam:AttachRolePolicy",
          "iam:PutRolePolicy",
          "iam:GetRole",
          "iam:ListRolePolicies",
          "iam:ListAttachedRolePolicies",
          "iam:GetRolePolicy",
          "iam:DetachRolePolicy",
          "iam:DeleteRolePolicy",
          "iam:CreatePolicyVersion",
          "iam:DeletePolicy",
          "iam:ListOpenIDConnectProviders",
          "iam:GetOpenIDConnectProvider"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "github_actions_deploy" {
  role       = aws_iam_role.github_actions.name
  policy_arn = aws_iam_policy.terraform_cicd_policy.arn
}

resource "aws_iam_role_policy_attachment" "github_actions_readonly" {
  role       = aws_iam_role.github_actions.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_role" "quiz_engine_role" {
  name = "quiz-engine-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_policy" "quiz_engine_policy" {
  name        = "quiz-engine-policy"
  description = "Permissions for the quiz_engine Lambda"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowReadQuestions"
        Effect = "Allow"
        Action = [
          "dynamodb:Query",
          "dynamodb:GetItem"
        ]
        Resource = [
          aws_dynamodb_table.mentoring_questions_table.arn,
          "${aws_dynamodb_table.mentoring_questions_table.arn}/index/*"
        ]
      },
      {
        Sid    = "AllowReadAndUpdateQuizzes"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem"
        ]
        Resource = aws_dynamodb_table.quizzes.arn
      },
      {
        Sid    = "AllowReadWriteQuizResults"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:Query"
        ]
        Resource = [
          aws_dynamodb_table.quiz_results.arn,
          "${aws_dynamodb_table.quiz_results.arn}/index/*"
        ]
      },
      {
        Sid    = "AllowUpdateStudentsInitialTest"
        Effect = "Allow"
        Action = [
          "dynamodb:UpdateItem"
        ]
        Resource = aws_dynamodb_table.students.arn
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

resource "aws_iam_role_policy_attachment" "quiz_engine_attach" {
  role       = aws_iam_role.quiz_engine_role.name
  policy_arn = aws_iam_policy.quiz_engine_policy.arn
}

# =============================================================
# Amplify Hosting — Rol + Política (Menor Privilegio)
# =============================================================

data "aws_caller_identity" "current" {}

resource "aws_iam_role" "amplify_role" {
  name = "mentoring-amplify-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "amplify.amazonaws.com"
      }
      Condition = {
        ArnLike = {
          "aws:SourceArn" = "arn:aws:amplify:${var.aws_region}:${data.aws_caller_identity.current.account_id}:apps/*"
        }
      }
    }]
  })

  tags = {
    Name        = "mentoring-amplify-role"
    Environment = var.environment
  }
}

resource "aws_iam_policy" "amplify_logging_policy" {
  name        = "mentoring-amplify-logging-policy"
  description = "Permisos mínimos para Amplify Hosting y envío de logs a CloudWatch"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/amplify/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "amplify_logs_attach" {
  role       = aws_iam_role.amplify_role.name
  policy_arn = aws_iam_policy.amplify_logging_policy.arn
}
