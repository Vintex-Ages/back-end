mock_provider "aws" {}
variables {
  expected_account_id     = "123456789012"
  shared_vpc_id           = "vpc-00000000000000001"
  shared_public_subnet_id = "subnet-00000000000000001"
}
override_data {
  target          = data.aws_vpc.shared
  override_during = plan
  values = {
    id       = "vpc-00000000000000001"
    owner_id = "123456789012"
    tags     = { Project = "Vintex", Environment = "shared" }
  }
}
override_data {
  target          = data.aws_subnet.shared
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
  target          = module.host.data.aws_ssm_parameter.al2023
  override_during = plan
  values          = { value = "ami-00000000000000001" }
}
override_data {
  target          = module.host.data.aws_ami.al2023
  override_during = plan
  values          = { id = "ami-00000000000000001", architecture = "arm64" }
}
override_resource {
  target          = module.host.aws_instance.staging
  override_during = plan
  values = {
    id  = "i-00000000000000001"
    arn = "arn:aws:ec2:us-east-2:123456789012:instance/i-00000000000000001"
  }
}
override_resource {
  target          = module.services.module.messaging.aws_sqs_queue.processing
  override_during = plan
  values = {
    arn = "arn:aws:sqs:us-east-2:123456789012:vintex-ai-staging"
    url = "https://sqs.us-east-2.amazonaws.com/123456789012/vintex-ai-staging"
  }
}
run "staging_conecta_shared_runtime_e_agendamento" {
  command = plan
  assert {
    condition     = output.instance_id == "i-00000000000000001" && output.runtime_resources.account_id == var.expected_account_id && output.runtime_resources.media_bucket == "vintex-media-staging-123456789012" && output.runtime_resources.queue_url == "https://sqs.us-east-2.amazonaws.com/123456789012/vintex-ai-staging" && output.runtime_resources.parameter_path == "/vintex/staging/" && output.runtime_resources.public_base_url == "http://localhost:8080"
    error_message = "Outputs devem conectar shared, staging e config.json da #273."
  }
  assert {
    condition     = length(output.log_groups) == 5 && length(output.schedules) == 3
    error_message = "Cinco serviços e três agendamentos devem compor o ambiente."
  }
}
run "conta_invalida" {
  command = plan
  variables { expected_account_id = "invalid" }
  expect_failures = [var.expected_account_id]
}
run "vpc_invalida" {
  command = plan
  variables { shared_vpc_id = "not-a-vpc" }
  expect_failures = [var.shared_vpc_id]
}
run "subnet_invalida" {
  command = plan
  variables { shared_public_subnet_id = "not-a-subnet" }
  expect_failures = [var.shared_public_subnet_id]
}
run "vpc_fora_do_projeto_recusada" {
  command = plan
  override_data {
    target          = data.aws_vpc.shared
    override_during = plan
    values = {
      id       = "vpc-00000000000000001"
      owner_id = "123456789012"
      tags     = { Project = "Other", Environment = "prod" }
    }
  }
  expect_failures = [data.aws_vpc.shared]
}
run "subnet_de_outra_vpc_recusada" {
  command = plan
  override_data {
    target          = data.aws_subnet.shared
    override_during = plan
    values = {
      id                      = "subnet-00000000000000001"
      vpc_id                  = "vpc-00000000000000002"
      owner_id                = "123456789012"
      map_public_ip_on_launch = true
      tags                    = { Environment = "shared" }
    }
  }
  expect_failures = [data.aws_subnet.shared]
}
run "subnet_sem_ipv4_publico_recusada" {
  command = plan
  override_data {
    target          = data.aws_subnet.shared
    override_during = plan
    values = {
      id                      = "subnet-00000000000000001"
      vpc_id                  = "vpc-00000000000000001"
      owner_id                = "123456789012"
      map_public_ip_on_launch = false
      tags                    = { Environment = "shared" }
    }
  }
  expect_failures = [data.aws_subnet.shared]
}
