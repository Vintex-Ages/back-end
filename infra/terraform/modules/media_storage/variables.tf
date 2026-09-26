variable "bucket_name" {
  description = "Nome globalmente único do bucket privado de mídia do ambiente."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.bucket_name))
    error_message = "Use um nome de bucket S3 válido, com 3 a 63 caracteres minúsculos."
  }
}
