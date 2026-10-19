variable "expected_account_id" {
  type        = string
  description = "Conta dedicada ao projeto, confirmada via SSO."
  validation {
    condition     = can(regex("^[0-9]{12}$", var.expected_account_id))
    error_message = "Informe o ID da conta AWS com 12 dígitos."
  }
}

variable "shared_vpc_id" {
  type        = string
  description = "Output vpc_id do shared já aplicado."
  validation {
    condition     = can(regex("^vpc-[0-9a-f]{8,17}$", var.shared_vpc_id))
    error_message = "Informe o ID real da VPC shared."
  }
}

variable "shared_public_subnet_id" {
  type        = string
  description = "Output public_subnet_id do shared já aplicado."
  validation {
    condition     = can(regex("^subnet-[0-9a-f]{8,17}$", var.shared_public_subnet_id))
    error_message = "Informe o ID real da subnet shared."
  }
}
