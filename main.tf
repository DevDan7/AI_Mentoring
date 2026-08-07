# Create an SQS queue and a dead-letter queue

resource "aws_sqs_queue" "main_queue" {
  name = "mentoring-main-queue"
}

resource "aws_sqs_queue" "dlq" {
  name = "mentoring-dlq"
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue",
    sourceQueueArns   = [aws_sqs_queue.main_queue.arn]
  })
}

resource "aws_sqs_queue_redrive_policy" "main_queue_redrive_policy" {
  queue_url = aws_sqs_queue.main_queue.id
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 4
  })
}

# Create an S3 bucket 

resource "aws_s3_bucket" "mentoring_exam_photos_bucket" {
  bucket = "daniel-mentoring-exam-photos-edn-dev"

  tags = {
    Name        = "mentoring-exam-photos-bucket"
    Environment = "dev"
    Project     = "mentoring"
    ManagedBy   = "terraform"
  }
}

resource "aws_sqs_queue_policy" "allow_s3_to_send_messages" {
  queue_url = aws_sqs_queue.main_queue.id

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [{
      Sid    = "AllowS3ToSendMessages"
      Effect = "Allow"

      Principal = {
        Service = "s3.amazonaws.com"
      }

      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.main_queue.arn

      Condition = {
        ArnLike = {
          "aws:SourceArn" = aws_s3_bucket.mentoring_exam_photos_bucket.arn
        }
      }
    }]
  })
}

resource "aws_s3_bucket_notification" "mentoring_exam_photos_notification" {
  bucket = aws_s3_bucket.mentoring_exam_photos_bucket.id

  queue {
    queue_arn = aws_sqs_queue.main_queue.arn
    events    = ["s3:ObjectCreated:*"]

  }

  depends_on = [
    aws_sqs_queue_policy.allow_s3_to_send_messages
  ]
}

# github_oidc.tf

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
            "token.actions.githubusercontent.com:sub" = "repo:DevDan7/AI_Mentoring:*"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "github_actions_readonly" {
  role       = aws_iam_role.github_actions.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

