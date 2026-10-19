output "instance_id" { value = aws_instance.staging.id }
output "instance_arn" { value = aws_instance.staging.arn }
output "instance_role_arn" { value = aws_iam_role.instance.arn }
