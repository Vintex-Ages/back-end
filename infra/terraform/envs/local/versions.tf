terraform {
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Sem backend remoto nesta sprint: o env local roda contra LocalStack e
  # MiniStack, nunca precisou de state compartilhado em S3. A estratégia de
  # backend para os envs de AWS real fica para a VE-27 (preparação para AWS
  # real), quando conta, região e orçamento estiverem formalizados.
}
