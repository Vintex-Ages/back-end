output "aws_region" {
  value = local.aws_region
}

output "account_id" {
  value = var.expected_account_id
}

output "vpc_id" {
  value = local.shared ? module.network[0].vpc_id : null
}

output "public_subnet_id" {
  value = local.shared ? module.network[0].public_subnet_id : null
}

output "ecr_repositories" {
  value = local.shared ? module.registry[0].repositories : null
}

output "budget" {
  value = local.shared ? module.budget[0].budget : null
}

output "instance_id" {
  description = "Instância acessível somente por SSM; IP não é endpoint público."
  value       = local.shared ? null : module.host[0].instance_id
}

output "instance_role_arn" {
  value = local.shared ? null : module.host[0].instance_role_arn
}

output "runtime_resources" {
  description = "Configuração pública do runtime da #273. Sem segredos."
  value = local.shared ? null : {
    account_id      = var.expected_account_id
    media_bucket    = module.services[0].media_bucket
    queue_url       = module.services[0].queue_url
    public_base_url = "http://localhost:8080"
    parameter_path  = "/vintex/staging/"
  }
}

output "dead_letter_queue_url" {
  value = local.shared ? null : module.services[0].dead_letter_queue_url
}

output "log_groups" {
  value = local.shared ? null : module.services[0].log_group_names
}

output "schedules" {
  value = local.shared ? null : module.scheduler[0].schedules
}
