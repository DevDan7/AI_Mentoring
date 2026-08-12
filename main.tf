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

resource "aws_sqs_queue_policy" "allow_sns_to_send_messages" {
  queue_url = aws_sqs_queue.main_queue.id

  policy = jsonencode({
    Version = "2012-10-17"

    Statement = [{
      Sid    = "AllowSNSToSendMessages"
      Effect = "Allow"

      Principal = {
        Service = "sns.amazonaws.com"
      }

      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.main_queue.arn

      Condition = {
        ArnEquals = {
          "aws:SourceArn" = aws_sns_topic.s3_notifications.arn
        }
      }
    }]
  })
}

# 1. El Tema de SNS y la Suscripción por Email
resource "aws_sns_topic" "AI_Mentoring_notifications" {
  name = "AI-Mentoring-notifications-dev-daniel"
}

resource "aws_sns_topic_subscription" "email_sub" {
  topic_arn = aws_sns_topic.AI_Mentoring_notifications.arn
  protocol  = "email"
  endpoint  = "danielsvillegas17@gmail.com"
}

# 2. Política del Tema SNS para permitir que S3 publique eventos
resource "aws_sns_topic_policy" "allow_s3_publish" {
  arn = aws_sns_topic.AI_Mentoring_notifications.arn

  policy = data.aws_iam_policy_document.sns_topic_policy.json
}

data "aws_iam_policy_document" "sns_topic_policy" {
  statement {
    sid     = "AllowS3ToPublishToSNS"
    effect  = "Allow"
    actions = ["sns:Publish"]

    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }

    resources = [aws_sns_topic.AI_Mentoring_notifications.arn]

    # Buena práctica de seguridad: restringir la publicación solo a tu bucket específico
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = [aws_s3_bucket.mentoring_exam_photos_bucket.arn]
    }
  }
}

# 3. Configuración consolidada de eventos dentro del Bucket de S3
resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = aws_s3_bucket.mentoring_exam_photos_bucket.id

  queue {
    queue_arn = aws_sqs_queue.main_queue.arn
    events    = ["s3:ObjectCreated:*"]
  }

  topic {
    topic_arn = aws_sns_topic.AI_Mentoring_notifications.arn
    events    = ["s3:ObjectCreated:*"]
  }

  depends_on = [
    aws_sqs_queue_policy.allow_s3_to_send_messages,
    aws_sns_topic_policy.allow_s3_publish
  ]
}

