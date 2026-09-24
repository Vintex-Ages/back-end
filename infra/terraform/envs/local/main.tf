# Env local: aponta o provider AWS para LocalStack e MiniStack, nunca para
# a AWS real. Nenhum recurso é declarado aqui ainda — os módulos de feature
# (rede, banco, storage, mensageria, worker, computação) entram quando VE-14
# a VE-19 saírem do hold; este arquivo só fornece o provider já configurado
# para eles importarem depois.

provider "aws" {
  region = var.aws_region

  # Credenciais fake fixas: LocalStack/MiniStack aceitam qualquer valor e
  # não existe conta AWS real associada a este env. Não é segredo.
  access_key = "test"
  secret_key = "test"

  s3_use_path_style           = true
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    # LocalStack — serviços gratuitos no plano Community.
    s3             = var.localstack_endpoint
    sqs            = var.localstack_endpoint
    secretsmanager = var.localstack_endpoint
    iam            = var.localstack_endpoint
    sts            = var.localstack_endpoint

    # MiniStack — cobre o que o LocalStack Community não emula mais de graça
    # (ECS/Fargate, Cloud Map, API Gateway HTTP API, VPC Link, ECR).
    ecs              = var.ministack_endpoint
    servicediscovery = var.ministack_endpoint
    apigatewayv2     = var.ministack_endpoint
    ecr              = var.ministack_endpoint
  }
}
