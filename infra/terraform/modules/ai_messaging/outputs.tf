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

output "delivery_settings" {
  description = "Contrato efetivo de polling, visibilidade, retenção e criptografia."
  value = {
    visibility_timeout_seconds    = aws_sqs_queue.processing.visibility_timeout_seconds
    receive_wait_time_seconds     = aws_sqs_queue.processing.receive_wait_time_seconds
    dead_letter_retention_seconds = aws_sqs_queue.dead_letter.message_retention_seconds
    processing_sse_enabled        = aws_sqs_queue.processing.sqs_managed_sse_enabled
    dead_letter_sse_enabled       = aws_sqs_queue.dead_letter.sqs_managed_sse_enabled
  }
}
