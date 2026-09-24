output "environment" {
  description = "Nome do ambiente ativo."
  value       = var.environment
}

output "aws_region" {
  description = "Região declarada ao provider AWS."
  value       = var.aws_region
}

output "localstack_endpoint" {
  description = "Endpoint do LocalStack usado pelos módulos de S3/SQS/Secrets/IAM/STS."
  value       = var.localstack_endpoint
}

output "ministack_endpoint" {
  description = "Endpoint do MiniStack usado pelos módulos de ECS/Cloud Map/API Gateway/ECR."
  value       = var.ministack_endpoint
}
