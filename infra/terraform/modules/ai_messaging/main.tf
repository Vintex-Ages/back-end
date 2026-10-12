resource "aws_sqs_queue" "dead_letter" {
  name = var.dead_letter_queue_name
}

resource "aws_sqs_queue" "processing" {
  name = var.processing_queue_name

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead_letter.arn
    maxReceiveCount     = var.max_receive_count
  })
}
