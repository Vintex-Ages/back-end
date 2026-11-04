output "vpc_id" {
  description = "ID da VPC dedicada."
  value       = aws_vpc.this.id
}

output "public_subnet_id" {
  description = "ID da subnet com saída pelo Internet Gateway."
  value       = aws_subnet.public.id
}
