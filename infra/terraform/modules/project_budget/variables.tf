variable "account_id" {
  description = "Conta dedicada cujo custo mensal será acompanhado."
  type        = string
}

variable "email_addresses" {
  description = "Destinatários fornecidos pelo responsável localmente."
  type        = set(string)
}
