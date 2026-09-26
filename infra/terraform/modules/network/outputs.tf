output "vpc_id" {
  description = "VPC das futuras tasks ECS e do VPC Link."
  value       = aws_vpc.this.id
}

output "vpc_cidr" {
  description = "Bloco IPv4 da VPC."
  value       = aws_vpc.this.cidr_block
}

output "egress_subnet_ids" {
  description = "Subnets por zona; tasks Fargate devem solicitar IP publico explicitamente para usar o Internet Gateway."
  value       = { for zone, subnet in aws_subnet.egress : zone => subnet.id }
}

output "egress_subnet_cidrs" {
  description = "CIDRs das subnets por zona."
  value       = { for zone, subnet in aws_subnet.egress : zone => subnet.cidr_block }
}

output "egress_subnet_auto_public_ips" {
  description = "Atribuição automática de IP público por subnet; deve ficar desabilitada."
  value       = { for zone, subnet in aws_subnet.egress : zone => subnet.map_public_ip_on_launch }
}

output "internet_route_destination" {
  description = "Destino da rota de saída pelo Internet Gateway."
  value       = aws_route.internet.destination_cidr_block
}

output "api_security_group_id" {
  description = "Grupo da API; ingress somente do VPC Link na porta privada."
  value       = aws_security_group.api.id
}

output "worker_security_group_id" {
  description = "Grupo do worker; nenhum ingress."
  value       = aws_security_group.worker.id
}

output "vpc_link_security_group_id" {
  description = "Grupo do VPC Link; egress somente para a API privada."
  value       = aws_security_group.vpc_link.id
}

output "api_ingress_port" {
  description = "Porta permitida do VPC Link para a API."
  value       = aws_vpc_security_group_ingress_rule.api_from_vpc_link.from_port
}

output "api_ingress_source_security_group_id" {
  description = "Origem permitida para o ingress da API."
  value       = aws_vpc_security_group_ingress_rule.api_from_vpc_link.referenced_security_group_id
}

output "worker_https_egress_port" {
  description = "Porta de saída permitida ao worker."
  value       = aws_vpc_security_group_egress_rule.worker_https.from_port
}

output "vpc_link_egress_destination_security_group_id" {
  description = "Único destino permitido ao VPC Link."
  value       = aws_vpc_security_group_egress_rule.vpc_link_to_api.referenced_security_group_id
}
