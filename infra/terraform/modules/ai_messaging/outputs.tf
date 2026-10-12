output "processing_queue_name" {
  description = "Nome da fila SQS de processamento."
  value       = aws_sqs_queue.processing.name
}

output "processing_queue_url" {
  description = "URL da fila SQS de processamento."
  value       = aws_sqs_queue.processing.url
}

output "processing_queue_arn" {
  description = "ARN da fila SQS de processamento."
  value       = aws_sqs_queue.processing.arn
}

output "dead_letter_queue_name" {
  description = "Nome da DLQ."
  value       = aws_sqs_queue.dead_letter.name
}

output "dead_letter_queue_url" {
  description = "URL da DLQ."
  value       = aws_sqs_queue.dead_letter.url
}

output "dead_letter_queue_arn" {
  description = "ARN da DLQ."
  value       = aws_sqs_queue.dead_letter.arn
}

output "max_receive_count" {
  description = "Limite configurado para o redrive à DLQ."
  value       = var.max_receive_count
}

output "redrive_policy" {
  description = "Política que conecta a fila de processamento à DLQ."
  value       = aws_sqs_queue.processing.redrive_policy
}
