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

output "network_vpc_id" {
  description = "VPC do módulo de rede."
  value       = module.network.vpc_id
}

output "network_vpc_cidr" {
  description = "CIDR da VPC do módulo de rede."
  value       = module.network.vpc_cidr
}

output "network_egress_subnet_ids" {
  description = "Subnets de saída por zona para tasks ECS e VPC Link."
  value       = module.network.egress_subnet_ids
}

output "network_egress_subnet_cidrs" {
  description = "CIDRs das subnets de saída por zona."
  value       = module.network.egress_subnet_cidrs
}

output "network_egress_subnet_auto_public_ips" {
  description = "Atribuição automática de IP público por subnet."
  value       = module.network.egress_subnet_auto_public_ips
}

output "network_internet_route_destination" {
  description = "Destino da rota do Internet Gateway."
  value       = module.network.internet_route_destination
}

output "network_api_security_group_id" {
  description = "Grupo de segurança da API."
  value       = module.network.api_security_group_id
}

output "network_worker_security_group_id" {
  description = "Grupo de segurança do worker."
  value       = module.network.worker_security_group_id
}

output "network_vpc_link_security_group_id" {
  description = "Grupo de segurança do VPC Link."
  value       = module.network.vpc_link_security_group_id
}

output "network_api_ingress_port" {
  description = "Porta privada liberada ao VPC Link."
  value       = module.network.api_ingress_port
}

output "network_api_ingress_source_security_group_id" {
  description = "Grupo autorizado a chegar na API."
  value       = module.network.api_ingress_source_security_group_id
}

output "network_worker_https_egress_port" {
  description = "Porta liberada para saída do worker."
  value       = module.network.worker_https_egress_port
}

output "network_vpc_link_egress_destination_security_group_id" {
  description = "Único grupo de destino do VPC Link."
  value       = module.network.vpc_link_egress_destination_security_group_id
}

output "ecs_execution_role_arn" {
  description = "Papel de execução ECS, sem permissões de aplicação."
  value       = module.ecs_execution_role.arn
}

output "ecs_execution_role_name" {
  description = "Nome do papel de execução ECS."
  value       = module.ecs_execution_role.name
}

output "ecs_execution_role_trust_policy" {
  description = "Política de confiança do papel de execução ECS."
  value       = module.ecs_execution_role.trust_policy
}

output "ecs_execution_role_policy_arn" {
  description = "Política gerenciada anexada ao papel de execução ECS."
  value       = module.ecs_execution_role.execution_policy_arn
}
