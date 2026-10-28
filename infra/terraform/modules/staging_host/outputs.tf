output "instance_id" { value = aws_instance.staging.id }
output "instance_arn" { value = aws_instance.staging.arn }
output "instance_role_arn" { value = aws_iam_role.instance.arn }

output "vpc_id" { value = var.vpc_id }
output "subnet_id" { value = var.subnet_id }
