output "origin_dns" {
  description = "Nome DNS público estável da instância (origem do CloudFront)."
  value       = aws_eip.preview.public_dns
}

output "public_url" {
  description = "URL pública do preview (certificado padrão do CloudFront)."
  value       = "https://${aws_cloudfront_distribution.preview.domain_name}"
}

output "distribution_id" {
  value = aws_cloudfront_distribution.preview.id
}

output "origin_verify_parameter" {
  description = "Parâmetro SecureString com o segredo que o Nginx exige do CloudFront."
  value       = aws_ssm_parameter.origin_verify.name
}
