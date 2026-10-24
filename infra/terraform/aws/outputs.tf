output "aws_region" {
  value = local.aws_region
}

output "account_id" {
  value = var.expected_account_id
}

output "vpc_id" {
  value = module.network[0].vpc_id
}

output "public_subnet_id" {
  value = module.network[0].public_subnet_id
}

output "ecr_repositories" {
  value = module.registry[0].repositories
}

output "budget" {
  value = module.budget[0].budget
}

output "instance_id" {
  description = "Instância acessível somente por SSM; IP não é endpoint público."
  value       = module.host[0].instance_id
}

output "instance_role_arn" {
  value = module.host[0].instance_role_arn
}

output "runtime_resources" {
  description = "Configuração pública do runtime da #273. Sem segredos."
  value = {
    account_id      = var.expected_account_id
    media_bucket    = module.services[0].media_bucket
    queue_url       = module.services[0].queue_url
    public_base_url = "http://localhost:8080"
    parameter_path  = "/vintex/staging/"
  }
}

output "dead_letter_queue_url" {
  value = module.services[0].dead_letter_queue_url
}

output "log_groups" {
  value = module.services[0].log_group_names
}

output "schedules" {
  value = module.scheduler[0].schedules
}

output "infrastructure_layout" {
  description = "Identifica o state completo da staging, sem state shared separado."
  value       = "staging-complete-v1"
}
