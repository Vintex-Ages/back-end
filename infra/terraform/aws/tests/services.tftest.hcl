mock_provider "aws" {}
variables { account_id = "123456789012" }
override_resource {
  target          = module.messaging.aws_sqs_queue.processing
  override_during = plan
  values = {
    arn = "arn:aws:sqs:us-east-2:123456789012:vintex-ai-staging"
    url = "https://sqs.us-east-2.amazonaws.com/123456789012/vintex-ai-staging"
  }
}
override_resource {
  target          = module.messaging.aws_sqs_queue.dead_letter
  override_during = plan
  values = {
    arn = "arn:aws:sqs:us-east-2:123456789012:vintex-ai-staging-dlq"
    url = "https://sqs.us-east-2.amazonaws.com/123456789012/vintex-ai-staging-dlq"
  }
}

run "midia_privada_sem_acls_e_com_tls" {
  command = plan
  module { source = "../modules/staging_services" }
  assert {
    condition     = module.media.bucket_name == "vintex-media-staging-123456789012" && module.media.public_access_block.block_public_acls && module.media.public_access_block.block_public_policy && module.media.public_access_block.ignore_public_acls && module.media.public_access_block.restrict_public_buckets
    error_message = "Mídia deve estar em bucket próprio e privado."
  }
  assert {
    condition     = aws_s3_bucket_ownership_controls.media.rule[0].object_ownership == "BucketOwnerEnforced" && jsondecode(aws_s3_bucket_policy.media_tls.policy).Statement[0].Effect == "Deny" && jsondecode(aws_s3_bucket_policy.media_tls.policy).Statement[0].Condition.Bool["aws:SecureTransport"] == "false"
    error_message = "ACLs desativadas e HTTP recusado."
  }
}

run "fila_contrato_worker_e_dlq_14_dias" {
  command = plan
  module { source = "../modules/staging_services" }
  assert {
    condition = module.messaging.delivery_settings == {
      visibility_timeout_seconds    = 180
      receive_wait_time_seconds     = 20
      dead_letter_retention_seconds = 1209600
      processing_sse_enabled        = true
      dead_letter_sse_enabled       = true
    }
    error_message = "Worker requer polling 20s, visibilidade 180s e DLQ de 14 dias, ambas criptografadas."
  }
  assert {
    condition     = output.queue_arn == "arn:aws:sqs:us-east-2:123456789012:vintex-ai-staging" && module.messaging.max_receive_count == 3 && module.messaging.processing_queue_name == "vintex-ai-staging" && module.messaging.dead_letter_queue_name == "vintex-ai-staging-dlq"
    error_message = "Fila deve seguir o contrato existente e redrive com três tentativas."
  }
  assert {
    condition     = jsondecode(aws_sqs_queue_redrive_allow_policy.staging.redrive_allow_policy).sourceQueueArns == [output.queue_arn]
    error_message = "DLQ deve aceitar redrive somente da fila staging."
  }
}

run "parametros_e_logs_separados" {
  command = plan
  module { source = "../modules/staging_services" }
  assert {
    condition     = toset(keys(aws_ssm_parameter.runtime)) == toset(["db_password", "jwt_secret", "llm_encryption_key", "llm_admin_email", "llm_admin_password", "llm_api_key"]) && alltrue([for parameter in aws_ssm_parameter.runtime : parameter.type == "SecureString" && parameter.tier == "Standard" && startswith(parameter.name, "/vintex/staging/") && parameter.value == "REPLACE_MANUALLY_BEFORE_DEPLOY"])
    error_message = "Parâmetros devem ser provisórios, criptografados e no caminho staging."
  }
  assert {
    condition     = toset(keys(aws_cloudwatch_log_group.runtime)) == toset(["proxy", "api", "worker", "freellmapi", "db"]) && alltrue([for service, group in aws_cloudwatch_log_group.runtime : group.name == "/vintex/staging/${service}" && group.retention_in_days == 7])
    error_message = "Cinco grupos alinhados ao Compose e retenção de sete dias."
  }
}
