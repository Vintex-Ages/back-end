variable "name_prefix" {
  description = "Prefixo dos nomes da rede compartilhada."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR IPv4 da VPC dedicada."
  type        = string
}

variable "subnet_cidr" {
  description = "CIDR IPv4 da única subnet pública."
  type        = string
}

variable "availability_zone" {
  description = "Zona da subnet pública."
  type        = string
}
