variable "name_prefix" {
  description = "Prefixo dos recursos de rede."
  type        = string
}

variable "vpc_cidr" {
  description = "Bloco IPv4 da VPC."
  type        = string
}

variable "availability_zones" {
  description = "Duas zonas distintas para as subnets de saída."
  type        = list(string)

  validation {
    condition     = length(var.availability_zones) == 2 && length(distinct(var.availability_zones)) == 2
    error_message = "Informe exatamente duas zonas de disponibilidade distintas."
  }
}

variable "public_subnet_cidrs" {
  description = "Dois blocos IPv4 distintos dentro da VPC, na ordem das zonas."
  type        = list(string)

  validation {
    condition     = length(var.public_subnet_cidrs) == 2 && length(distinct(var.public_subnet_cidrs)) == 2
    error_message = "Informe exatamente dois CIDRs de subnet distintos."
  }
}

variable "api_port" {
  description = "Porta privada da API, acessível somente pelo security group do VPC Link."
  type        = number
  default     = 8000

  validation {
    condition     = var.api_port >= 1 && var.api_port <= 65535
    error_message = "A porta da API deve estar entre 1 e 65535."
  }
}
