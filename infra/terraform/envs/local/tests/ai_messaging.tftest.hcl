# Plano mockado; a integração real com SQS é verificada contra o LocalStack.
mock_provider "aws" {}

override_resource {
  target          = module.ai_messaging.aws_sqs_queue.dead_letter
  override_during = plan
  values = {
    arn = "arn:aws:sqs:us-east-2:000000000000:vintex-local-image-analysis-dlq"
  }
}

run "fila_de_analise_com_dlq" {
  command = plan

  assert {
    condition     = output.image_analysis_queue_name == "vintex-local-image-analysis"
    error_message = "A fila deve usar o nome compartilhado com o Compose local."
  }

  assert {
    condition     = output.image_analysis_dlq_name == "vintex-local-image-analysis-dlq"
    error_message = "A DLQ deve usar o nome compartilhado com o Compose local."
  }

  assert {
    condition     = output.image_analysis_max_receive_count == 3
    error_message = "A tarefa deve ser encaminhada após três entregas."
  }

  assert {
    condition     = tonumber(jsondecode(output.image_analysis_redrive_policy).maxReceiveCount) == 3
    error_message = "A política da fila deve limitar as entregas a três."
  }

  assert {
    condition     = jsondecode(output.image_analysis_redrive_policy).deadLetterTargetArn == output.image_analysis_dlq_arn
    error_message = "A fila de processamento deve redirecionar para a DLQ do módulo."
  }
}
