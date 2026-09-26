output "arn" {
  description = "ARN do papel de execução ECS; não é papel de aplicação."
  value       = aws_iam_role.this.arn
}

output "name" {
  description = "Nome do papel de execução ECS."
  value       = aws_iam_role.this.name
}

output "trust_policy" {
  description = "Política de confiança do papel, útil para auditoria do plano mockado."
  value       = aws_iam_role.this.assume_role_policy
}

output "execution_policy_arn" {
  description = "Política gerenciada anexada ao papel de execução."
  value       = aws_iam_role_policy_attachment.execution.policy_arn
}
