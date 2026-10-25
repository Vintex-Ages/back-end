variable "deployment" {
  type = string
  validation {
    condition     = var.deployment == "staging"
    error_message = "Selecione staging pelo arquivo de variáveis."
  }
}

variable "expected_account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "Informe a conta AWS esperada com 12 dígitos."
  }
}

variable "state_bucket" {
  type = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.state_bucket))
    error_message = "Informe um nome válido para o bucket do state."
  }
}

# Desligue (false) se a política da conta não permitir criar Budgets.
variable "enable_budget" {
  type    = bool
  default = true
}

variable "budget_email_addresses" {
  type    = set(string)
  default = []
  validation {
    condition = !var.enable_budget || (
      length(var.budget_email_addresses) > 0 && length(var.budget_email_addresses) <= 10 && alltrue([
        for email in var.budget_email_addresses : can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", email))
      ])
    )
    error_message = "Com enable_budget=true, informe entre 1 e 10 e-mails válidos para os alertas do Budget."
  }
}

# Abre a staging ao público durante a janela de funcionamento, por CloudFront.
# Desligado por padrão: a staging continua sem ingress e acessível por SSM.
variable "public_preview" {
  type    = bool
  default = false
}
