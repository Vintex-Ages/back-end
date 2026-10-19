output "instance_id" {
  value       = module.host.instance_id
  description = "Instância acessível somente por SSM; IP não é endpoint público."
}

output "instance_role_arn" {
  value = module.host.instance_role_arn
}

output "runtime_resources" {
  description = "Valores públicos para preencher config.json da #273. Não contém segredos."
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
