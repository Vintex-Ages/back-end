mock_provider "aws" {}
variables {
  expected_account_id = "123456789012"
  deployment          = "staging"
  state_bucket        = "vintex-test-state"
}
override_data {
  target = data.terraform_remote_state.shared[0]
  values = { outputs = {
    account_id = "123456789012", aws_region = "us-east-2"
    vpc_id     = "vpc-00000000000000001", public_subnet_id = "subnet-00000000000000001"
  } }
}
override_data {
  target          = data.aws_vpc.shared[0]
  override_during = plan
  values = {
    id       = "vpc-00000000000000001"
    owner_id = "123456789012"
    tags     = { Project = "Vintex", Environment = "shared" }
  }
}
override_data {
  target          = data.aws_subnet.shared[0]
  override_during = plan
  values = {
    id                      = "subnet-00000000000000001"
    vpc_id                  = "vpc-00000000000000001"
    owner_id                = "123456789012"
    map_public_ip_on_launch = true
    tags                    = { Environment = "shared" }
  }
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
run "staging_conecta_shared_runtime_e_agendamento" {
  command = plan
  assert {
    condition     = length(module.network) == 0 && length(module.registry) == 0 && length(module.budget) == 0
    error_message = "Staging não pode recriar os recursos compartilhados."
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
run "shared_de_outra_conta_recusado" {
  command = plan
  override_data {
    target = data.terraform_remote_state.shared[0]
    values = { outputs = {
      account_id = "999999999999", aws_region = "us-east-2"
      vpc_id     = "vpc-00000000000000001", public_subnet_id = "subnet-00000000000000001"
    } }
  }
  expect_failures = [data.terraform_remote_state.shared[0]]
}
run "shared_de_outra_regiao_recusado" {
  command = plan
  override_data {
    target = data.terraform_remote_state.shared[0]
    values = { outputs = {
      account_id = "123456789012", aws_region = "us-east-1"
      vpc_id     = "vpc-00000000000000001", public_subnet_id = "subnet-00000000000000001"
    } }
  }
  expect_failures = [data.terraform_remote_state.shared[0]]
}
run "vpc_fora_do_projeto_recusada" {
  command = plan
  override_data {
    target          = data.aws_vpc.shared[0]
    override_during = plan
    values = {
      id       = "vpc-00000000000000001"
      owner_id = "123456789012"
      tags     = { Project = "Other", Environment = "prod" }
    }
  }
  expect_failures = [data.aws_vpc.shared[0]]
}
run "subnet_de_outra_vpc_recusada" {
  command = plan
  override_data {
    target          = data.aws_subnet.shared[0]
    override_during = plan
    values = {
      id                      = "subnet-00000000000000001"
      vpc_id                  = "vpc-00000000000000002"
      owner_id                = "123456789012"
      map_public_ip_on_launch = true
      tags                    = { Environment = "shared" }
    }
  }
  expect_failures = [data.aws_subnet.shared[0]]
}
run "subnet_sem_ipv4_publico_recusada" {
  command = plan
  override_data {
    target          = data.aws_subnet.shared[0]
    override_during = plan
    values = {
      id                      = "subnet-00000000000000001"
      vpc_id                  = "vpc-00000000000000001"
      owner_id                = "123456789012"
      map_public_ip_on_launch = false
      tags                    = { Environment = "shared" }
    }
  }
  expect_failures = [data.aws_subnet.shared[0]]
}
