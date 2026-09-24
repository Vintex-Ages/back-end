# Teste mockado (VE-13): não sobe LocalStack/MiniStack, não toca a AWS real.
# mock_provider substitui completamente o provider "aws" por um dublê do
# Terraform — plan roda em memória, sem nenhuma chamada de rede.

mock_provider "aws" {}

run "environment_e_endpoints_default_corretos" {
  command = plan

  assert {
    condition     = output.environment == "local"
    error_message = "Env local deveria sempre reportar environment = \"local\"."
  }

  assert {
    condition     = output.aws_region == "us-east-1"
    error_message = "Região default inesperada."
  }

  assert {
    condition     = output.localstack_endpoint == "http://localhost:4566"
    error_message = "Endpoint default do LocalStack deveria ser http://localhost:4566."
  }

  assert {
    condition     = output.ministack_endpoint == "http://localhost:4567"
    error_message = "Endpoint default do MiniStack deveria ser http://localhost:4567."
  }
}

run "endpoints_customizaveis_por_variavel" {
  command = plan

  variables {
    localstack_endpoint = "http://localstack:4566"
    ministack_endpoint  = "http://ministack:4567"
  }

  assert {
    condition     = output.localstack_endpoint == "http://localstack:4566"
    error_message = "Endpoint do LocalStack deveria refletir a variável, para uso dentro da rede vintex-infra-net."
  }

  assert {
    condition     = output.ministack_endpoint == "http://ministack:4567"
    error_message = "Endpoint do MiniStack deveria refletir a variável, para uso dentro da rede vintex-infra-net."
  }
}
