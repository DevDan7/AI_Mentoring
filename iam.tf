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
          "bedrock:InvokeModel"
        ]
        Resource = "*"
      },
      {
        Sid    = "AllowDynamoDBAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:Query"
        ]
        Resource = [
          aws_dynamodb_table.mentoring_questions_table.arn,
          "${aws_dynamodb_table.mentoring_questions_table.arn}/index/*"
        ]
      },
      {
        Sid    = "AllowPublishNotifications"
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = aws_sns_topic.AI_Mentoring_notifications.arn
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
          "iam:CreatePolicy",
          "iam:DeletePolicy",
          "iam:GetPolicy",
          "iam:ListPolicies",
          "iam:CreatePolicyVersion",
          "iam:DeletePolicyVersion",     # <-- FALTABA
          "iam:GetPolicyVersion",        # <-- FALTABA
          "iam:SetDefaultPolicyVersion", # <-- FALTABA
          "iam:ListPolicyVersions",      # <-- RECOMENDADO
          "iam:ListOpenIDConnectProviders",
          "iam:UpdateAssumeRolePolicy",
          "iam:GetOpenIDConnectProvider"
        ]
        Resource = "*"
      },
      {
        # Paso 1a (2026-10-01): presupuestos de AWS Budgets creados por Terraform (budgets.tf).
        # Mínimo privilegio: solo los budgets cuyo nombre empieza con "ai-mentoring-"; los
        # presupuestos creados a mano en la cuenta (Alerta Free Tear, pdv-dev-*) quedan fuera.
        # budgets:ModifyBudget cubre crear/actualizar/borrar; los *Tag* son para default_tags (paso 1b).
        Sid    = "ManageProjectBudgets"
        Effect = "Allow"
        Action = [
          "budgets:ModifyBudget",
          "budgets:ViewBudget",
          "budgets:TagResource",
          "budgets:UntagResource",
          "budgets:ListTagsForResource"
        ]
        Resource = "arn:aws:budgets::${data.aws_caller_identity.current.account_id}:budget/ai-mentoring-*"
      },
      {
        # Paso 1a (2026-10-01): poner el tag Project=AI_Mentoring (default_tags, paso 1b) en los
        # roles y políticas IAM del proyecto. Sin esto el apply del paso 1b falla en IAM.
        # Acotado a los nombres que maneja este repo (iam.tf, iam_student_api.tf).
        Sid    = "TagProjectIamResources"
        Effect = "Allow"
        Action = [
          "iam:TagRole",
          "iam:UntagRole",
          "iam:ListRoleTags",
          "iam:TagPolicy",
          "iam:UntagPolicy",
          "iam:ListPolicyTags"
        ]
        Resource = [
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/mentoring-*",
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/quiz-engine-role",
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/ai-mentoring-github-actions",
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/mentoring-*",
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/quiz-engine-policy",
          "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/terraform-cicd-policy"
        ]
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
          "dynamodb:GetItem",
          "dynamodb:BatchGetItem"
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
          "dynamodb:UpdateItem",
          "dynamodb:Query" # <-- Agregado
        ]
        Resource = [
          aws_dynamodb_table.quizzes.arn,
          "${aws_dynamodb_table.quizzes.arn}/index/*"
        ]
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
          "dynamodb:GetItem",
          "dynamodb:UpdateItem"
        ]
        Resource = aws_dynamodb_table.students.arn
      },
      {
        # Regla de acceso: leer el Status de la turma del alumno (turma cerrada = 403)
        Sid      = "AllowReadCohortStatus"
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem"]
        Resource = aws_dynamodb_table.cohorts.arn
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
        ArnLikeIfExists = {
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
