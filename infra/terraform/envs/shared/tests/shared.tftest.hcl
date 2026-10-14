# Todos os planos usam o provider mockado: nenhuma credencial ou API AWS.
mock_provider "aws" {}

variables {
  expected_account_id    = "123456789012"
  budget_email_addresses = ["infra@example.test"]
}

override_resource {
  target          = module.network.aws_vpc.this
  override_during = plan
  values          = { id = "vpc-shared-test" }
}

override_resource {
  target          = module.network.aws_subnet.public
  override_during = plan
  values          = { id = "subnet-shared-test" }
}

override_resource {
  target          = module.registry.aws_ecr_repository.this["vintex-backend"]
  override_during = plan
  values = {
    arn            = "arn:aws:ecr:us-east-2:123456789012:repository/vintex-backend"
    repository_url = "123456789012.dkr.ecr.us-east-2.amazonaws.com/vintex-backend"
  }
}

override_resource {
  target          = module.registry.aws_ecr_repository.this["freellmapi"]
  override_during = plan
  values = {
    arn            = "arn:aws:ecr:us-east-2:123456789012:repository/freellmapi"
    repository_url = "123456789012.dkr.ecr.us-east-2.amazonaws.com/freellmapi"
  }
}

run "shared_outputs_para_staging" {
  command = plan

  assert {
    condition     = output.aws_region == "us-east-2" && output.account_id == var.expected_account_id
    error_message = "Shared deve usar Ohio e expor a conta esperada."
  }
  assert {
    condition     = output.vpc_id == "vpc-shared-test" && output.public_subnet_id == "subnet-shared-test"
    error_message = "A staging deve receber os IDs da rede compartilhada."
  }
  assert {
    condition     = toset(keys(output.ecr_repositories)) == toset(["vintex-backend", "freellmapi"])
    error_message = "São necessários exatamente dois repositórios."
  }
  assert {
    condition = alltrue([
      for name, repo in output.ecr_repositories :
      repo.name == name && repo.url == "123456789012.dkr.ecr.us-east-2.amazonaws.com/${name}" &&
      repo.arn == "arn:aws:ecr:us-east-2:123456789012:repository/${name}"
    ])
    error_message = "Nomes, ARNs e URLs devem corresponder aos repositórios compartilhados."
  }
  assert {
    condition     = output.budget.name == "vintex-monthly"
    error_message = "O Budget do projeto deve ser único."
  }
}

run "conta_invalida_recusada" {
  command = plan
  variables {
    expected_account_id = "conta-invalida"
  }
  expect_failures = [var.expected_account_id]
}

run "emails_obrigatorios" {
  command = plan
  variables {
    budget_email_addresses = []
  }
  expect_failures = [var.budget_email_addresses]
}

run "email_invalido_recusado" {
  command = plan
  variables {
    budget_email_addresses = ["nao-e-email"]
  }
  expect_failures = [var.budget_email_addresses]
}

run "limite_de_destinatarios" {
  command = plan
  variables {
    budget_email_addresses = [for i in range(11) : "infra${i}@example.test"]
  }
  expect_failures = [var.budget_email_addresses]
}
