variable "deployment" {
  type = string
  validation {
    condition     = contains(["shared", "staging"], var.deployment)
    error_message = "Selecione shared ou staging pelo arquivo de variáveis."
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

variable "budget_email_addresses" {
  type    = set(string)
  default = []
  validation {
    condition = var.deployment != "shared" || (
      length(var.budget_email_addresses) > 0 && length(var.budget_email_addresses) <= 10 && alltrue([
        for email in var.budget_email_addresses : can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", email))
      ])
    )
    error_message = "Shared exige entre 1 e 10 e-mails válidos para os alertas do Budget."
  }
}
