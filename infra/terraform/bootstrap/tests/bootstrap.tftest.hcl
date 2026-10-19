mock_provider "aws" {}

variables {
  expected_account_id = "123456789012"
  state_bucket        = "vintex-terraform-state-123456789012"
}

override_resource {
  target          = aws_s3_bucket.state
  override_during = plan
  values = {
    id  = "vintex-terraform-state-123456789012"
    arn = "arn:aws:s3:::vintex-terraform-state-123456789012"
  }
}

run "bucket_privado_versionado_criptografado_tls" {
  command = plan
  assert {
    condition = (!aws_s3_bucket.state.force_destroy &&
      aws_s3_bucket_public_access_block.state.block_public_acls &&
      aws_s3_bucket_public_access_block.state.block_public_policy &&
      aws_s3_bucket_public_access_block.state.ignore_public_acls &&
    aws_s3_bucket_public_access_block.state.restrict_public_buckets)
    error_message = "O state não pode ser público ou apagado à força."
  }
  assert {
    condition = (aws_s3_bucket_versioning.state.versioning_configuration[0].status == "Enabled" &&
    aws_s3_bucket_ownership_controls.state.rule[0].object_ownership == "BucketOwnerEnforced")
    error_message = "State deve ter versões e ACLs desabilitadas."
  }
  assert {
    condition = alltrue([
      for rule in aws_s3_bucket_server_side_encryption_configuration.state.rule :
      alltrue([for encryption in rule.apply_server_side_encryption_by_default : encryption.sse_algorithm == "AES256"])
    ])
    error_message = "Criptografia AES256 deve ser padrão."
  }
  assert {
    condition = (jsondecode(aws_s3_bucket_policy.state_tls.policy).Statement[0].Effect == "Deny" &&
      jsondecode(aws_s3_bucket_policy.state_tls.policy).Statement[0].Condition.Bool["aws:SecureTransport"] == "false" &&
    output.account_id == "123456789012" && output.aws_region == "us-east-2")
    error_message = "Negar HTTP e manter conta/região estipuladas."
  }
}

run "conta_invalida" {
  command = plan
  variables { expected_account_id = "invalid" }
  expect_failures = [var.expected_account_id]
}

run "bucket_invalido" {
  command = plan
  variables { state_bucket = "BUCKET_INVALIDO" }
  expect_failures = [var.state_bucket]
}
