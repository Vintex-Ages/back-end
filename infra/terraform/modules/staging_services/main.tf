locals {
  services = toset(["proxy", "api", "worker", "freellmapi", "db"])
  parameters = toset([
    "db_password", "jwt_secret", "llm_encryption_key",
    "llm_admin_email", "llm_admin_password", "llm_api_key"
  ])
}

module "media" {
  source      = "../media_storage"
  bucket_name = "vintex-media-staging-${var.account_id}"
}

resource "aws_s3_bucket_ownership_controls" "media" {
  bucket = module.media.bucket_name
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_policy" "media_tls" {
  bucket = module.media.bucket_name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "RequireTLS"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = ["arn:aws:s3:::${module.media.bucket_name}", "arn:aws:s3:::${module.media.bucket_name}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}

module "messaging" {
  source                        = "../ai_messaging"
  processing_queue_name         = "vintex-ai-staging"
  dead_letter_queue_name        = "vintex-ai-staging-dlq"
  max_receive_count             = 3
  visibility_timeout_seconds    = 180
  receive_wait_time_seconds     = 20
  dead_letter_retention_seconds = 1209600
}

resource "aws_sqs_queue_redrive_allow_policy" "staging" {
  queue_url = module.messaging.dead_letter_queue_url
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [module.messaging.processing_queue_arn]
  })
}

resource "aws_ssm_parameter" "runtime" {
  for_each = local.parameters
  name     = "/vintex/staging/${each.value}"
  type     = "SecureString"
  tier     = "Standard"
  value    = "REPLACE_MANUALLY_BEFORE_DEPLOY"
  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_cloudwatch_log_group" "runtime" {
  for_each          = local.services
  name              = "/vintex/staging/${each.value}"
  retention_in_days = 7
}
