# Planos Terraform inteiramente mockados; nenhuma chamada a AWS ou emuladores.
mock_provider "aws" {}

override_resource {
  target          = module.network.aws_security_group.vpc_link
  override_during = plan
  values          = { id = "sg-vpc-link-test" }
}

override_resource {
  target          = module.network.aws_security_group.api
  override_during = plan
  values          = { id = "sg-api-test" }
}

run "rede_e_papel_minimos" {
  command = plan

  assert {
    condition     = output.network_vpc_cidr == "10.80.0.0/16"
    error_message = "A VPC local deve usar o CIDR reservado para este módulo."
  }

  assert {
    condition = output.network_egress_subnet_cidrs == {
      "us-east-2a" = "10.80.1.0/24"
      "us-east-2b" = "10.80.2.0/24"
    }
    error_message = "São necessárias duas subnets em zonas distintas."
  }

  assert {
    condition     = length(output.network_egress_subnet_ids) == 2
    error_message = "O módulo deve expor as duas subnets para ECS e VPC Link."
  }

  assert {
    condition     = alltrue([for enabled in values(output.network_egress_subnet_auto_public_ips) : !enabled])
    error_message = "As subnets não podem atribuir IP público automaticamente."
  }

  assert {
    condition     = output.network_internet_route_destination == "0.0.0.0/0"
    error_message = "A rota de saída deve apontar ao Internet Gateway."
  }

  assert {
    condition     = output.network_api_ingress_port == 8000
    error_message = "A API deve receber apenas na porta privada 8000."
  }

  assert {
    condition     = output.network_api_ingress_source_security_group_id == output.network_vpc_link_security_group_id
    error_message = "O ingress da API deve partir somente do security group do VPC Link."
  }

  assert {
    condition     = output.network_worker_https_egress_port == 443
    error_message = "O worker deve ter saída HTTPS controlada."
  }

  assert {
    condition     = output.network_vpc_link_egress_destination_security_group_id == output.network_api_security_group_id
    error_message = "O VPC Link deve ter saída somente para o grupo da API."
  }

  assert {
    condition     = output.ecs_execution_role_name == "vintex-local-ecs-execution"
    error_message = "Nome do papel de execução ECS inesperado."
  }

  assert {
    condition     = jsondecode(output.ecs_execution_role_trust_policy).Statement[0].Principal.Service == "ecs-tasks.amazonaws.com"
    error_message = "Somente tasks ECS devem assumir o papel de execução."
  }

  assert {
    condition     = output.ecs_execution_role_policy_arn == "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
    error_message = "O papel de execução deve receber somente a política gerenciada de ECR/logs."
  }
}

run "zonas_seguem_regiao_configurada" {
  command = plan

  variables {
    aws_region = "us-west-2"
  }

  assert {
    condition = output.network_egress_subnet_cidrs == {
      "us-west-2a" = "10.80.1.0/24"
      "us-west-2b" = "10.80.2.0/24"
    }
    error_message = "As zonas das subnets devem seguir a região configurada."
  }
}
