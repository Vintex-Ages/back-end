mock_provider "aws" {}
variables {
  expected_account_id    = "123456789012"
  deployment             = "staging"
  state_bucket           = "vintex-test-state"
  budget_email_addresses = ["infra@example.test"]
}
override_resource {
  target          = module.network[0].aws_vpc.this
  override_during = plan
  values          = { id = "vpc-00000000000000001" }
}
override_resource {
  target          = module.network[0].aws_subnet.public
  override_during = plan
  values          = { id = "subnet-00000000000000001" }
}
override_data {
  target          = module.host[0].data.aws_ssm_parameter.al2023
  override_during = plan
  values          = { value = "ami-00000000000000001" }
}
override_data {
  target          = module.host[0].data.aws_ami.al2023
  override_during = plan
  values          = { id = "ami-00000000000000001", architecture = "arm64" }
}
override_resource {
  target          = module.host[0].aws_instance.staging
  override_during = plan
  values = {
    id  = "i-00000000000000001"
    arn = "arn:aws:ec2:us-east-2:123456789012:instance/i-00000000000000001"
  }
}
override_resource {
  target          = module.services[0].module.messaging.aws_sqs_queue.processing
  override_during = plan
  values = {
    arn = "arn:aws:sqs:us-east-2:123456789012:vintex-ai-staging"
    url = "https://sqs.us-east-2.amazonaws.com/123456789012/vintex-ai-staging"
  }
}
run "staging_completa_conecta_runtime_e_agendamento" {
  command = plan
  assert {
    condition     = length(module.network) == 1 && length(module.registry) == 1 && length(module.budget) == 1
    error_message = "Staging deve incluir rede, registro e orçamento no mesmo state."
  }
  assert {
    condition     = output.instance_id == "i-00000000000000001" && output.runtime_resources.account_id == var.expected_account_id && output.runtime_resources.media_bucket == "vintex-media-staging-123456789012" && output.runtime_resources.queue_url == "https://sqs.us-east-2.amazonaws.com/123456789012/vintex-ai-staging" && output.runtime_resources.parameter_path == "/vintex/staging/" && output.runtime_resources.public_base_url == "http://localhost:8080"
    error_message = "Outputs devem conectar shared, staging e config.json da #273."
  }
  assert {
    condition     = length(output.log_groups) == 5 && length(output.schedules) == 3
    error_message = "Cinco serviços e três agendamentos devem compor o ambiente."
  }
}
run "ambiente_nao_suportado_recusado" {
  command = plan
  variables { deployment = "prod" }
  expect_failures = [var.deployment]
}
run "bucket_invalido_recusado" {
  command = plan
  variables { state_bucket = "INVALID" }
  expect_failures = [var.state_bucket]
}
run "conta_invalida" {
  command = plan
  variables { expected_account_id = "invalid" }
  expect_failures = [var.expected_account_id]
}
run "host_recebe_rede_e_ecr_dos_modulos" {
  command = plan
  assert {
    condition     = module.host[0].vpc_id == module.network[0].vpc_id && module.host[0].subnet_id == module.network[0].public_subnet_id
    error_message = "Host deve receber a rede do mesmo plano, sem IDs copiados ou remote state."
  }
  assert {
    condition     = output.infrastructure_layout == "staging-complete-v1"
    error_message = "State precisa identificar a composição completa."
  }
}
