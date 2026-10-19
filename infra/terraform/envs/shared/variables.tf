variable "expected_account_id" {
  description = "Conta AWS dedicada ao Vintex, confirmada pelo responsável via SSO."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "Informe o ID da conta AWS esperada com 12 dígitos."
  }
}

variable "budget_email_addresses" {
  description = "E-mails de AGES III/IV para os alertas; fornecidos localmente."
  type        = set(string)

  validation {
    condition = length(var.budget_email_addresses) > 0 && length(var.budget_email_addresses) <= 10 && alltrue([
      for email in var.budget_email_addresses : can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", email))
    ])
    error_message = "Informe entre 1 e 10 e-mails válidos para os alertas de orçamento."
  }
}
