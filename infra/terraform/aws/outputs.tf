output "aws_region" {
  value = local.aws_region
}

output "account_id" {
  value = var.expected_account_id
}

output "vpc_id" {
  value = module.network.vpc_id
}

output "public_subnet_id" {
  value = module.network.public_subnet_id
}

output "ecr_repositories" {
  value = module.registry.repositories
}

output "budget" {
  value = one(module.budget[*].budget)
}

output "instance_id" {
  description = "Instância acessível somente por SSM; IP não é endpoint público."
  value       = module.host.instance_id
}

output "instance_role_arn" {
  value = module.host.instance_role_arn
}

output "runtime_resources" {
  description = "Configuração pública do runtime da #273. Sem segredos."
  value = {
    account_id      = var.expected_account_id
    media_bucket    = module.services.media_bucket
    queue_url       = module.services.queue_url
    public_base_url = "http://localhost:8080"
    parameter_path  = "/vintex/staging/"
  }
}

output "dead_letter_queue_url" {
  value = module.services.dead_letter_queue_url
}

output "log_groups" {
  value = module.services.log_group_names
}

output "schedules" {
  value = module.scheduler.schedules
}

output "infrastructure_layout" {
  description = "Identifica o state completo da staging, sem state shared separado."
  value       = "staging-complete-v1"
}

output "preview_origin_dns" {
  description = "DNS estável da origem do preview aberto; null com public_preview desligado."
  value       = one(module.preview[*].origin_dns)
}
