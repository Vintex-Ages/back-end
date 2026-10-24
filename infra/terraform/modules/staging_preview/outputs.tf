output "origin_dns" {
  description = "Nome DNS público estável da instância (origem do CloudFront)."
  value       = aws_eip.preview.public_dns
}
