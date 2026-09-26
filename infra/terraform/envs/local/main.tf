# Env local: aponta o provider AWS para LocalStack e MiniStack, nunca para
# a AWS real. Rede e papel de execução ECS são planejados na VE-14; os módulos
# de banco, mensageria, worker e computação entram nas issues seguintes.

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
    ec2              = var.ministack_endpoint
    ecs              = var.ministack_endpoint
    servicediscovery = var.ministack_endpoint
    apigatewayv2     = var.ministack_endpoint
    ecr              = var.ministack_endpoint
  }
}

module "network" {
  source = "../../modules/network"

  name_prefix         = "vintex-${var.environment}"
  vpc_cidr            = "10.80.0.0/16"
  availability_zones  = ["${var.aws_region}a", "${var.aws_region}b"]
  public_subnet_cidrs = ["10.80.1.0/24", "10.80.2.0/24"]
}

module "ecs_execution_role" {
  source      = "../../modules/ecs_execution_role"
  name_prefix = "vintex-${var.environment}"
}

module "media_storage" {
  source      = "../../modules/media_storage"
  bucket_name = "vintex-${var.environment}-media"
}
