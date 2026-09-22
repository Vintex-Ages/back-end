variable "environment" {
  description = "Nome do ambiente. Neste env é sempre \"local\" — existe como variável para os módulos reaproveitarem a mesma interface dos envs futuros (staging/prod)."
  type        = string
  default     = "local"

  validation {
    condition     = var.environment == "local"
    error_message = "Este env é exclusivo para desenvolvimento/teste local; use outro env para staging/prod."
  }
}

variable "aws_region" {
  description = "Região AWS declarada ao provider. LocalStack/MiniStack não validam a região de verdade, mas o provider exige um valor."
  type        = string
  default     = "us-east-1"
}

variable "localstack_endpoint" {
  description = "Endpoint do LocalStack (S3, SQS, Secrets Manager, IAM, STS). Alias vintex-infra-net entre containers, localhost fora deles."
  type        = string
  default     = "http://localhost:4566"
}

variable "ministack_endpoint" {
  description = "Endpoint do MiniStack (ECS, Cloud Map, API Gateway, ECR, VPC Link). Alias vintex-infra-net entre containers, localhost fora deles."
  type        = string
  default     = "http://localhost:4567"
}
