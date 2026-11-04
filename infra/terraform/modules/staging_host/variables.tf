variable "account_id" { type = string }
variable "vpc_id" { type = string }
variable "subnet_id" { type = string }
variable "media_bucket" { type = string }
variable "queue_arn" { type = string }
variable "ecr_repository_arns" { type = list(string) }
variable "log_group_arns" { type = list(string) }

# Preview aberto: libera a porta 80 somente para o CloudFront. Desligado por
# padrão; sem ele o security group continua sem nenhum ingress.
variable "public_http_from_cloudfront" {
  type    = bool
  default = false
}
