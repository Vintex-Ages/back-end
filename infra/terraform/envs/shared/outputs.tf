output "aws_region" {
  description = "Região dos recursos regionais compartilhados."
  value       = local.aws_region
}

output "account_id" {
  description = "Conta esperada, também restringida pelo provider."
  value       = var.expected_account_id
}

output "vpc_id" {
  description = "VPC dedicada, consumida por staging e futura produção."
  value       = module.network.vpc_id
}

output "public_subnet_id" {
  description = "Subnet pública compartilhada para os hosts EC2."
  value       = module.network.public_subnet_id
}

output "ecr_repositories" {
  description = "Mapa de nome para ARN e URL dos repositórios privados."
  value       = module.registry.repositories
}

output "budget" {
  description = "Nome e ARN do Budget mensal da conta Vintex."
  value       = module.budget.budget
}
