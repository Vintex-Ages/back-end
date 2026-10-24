mock_provider "aws" {}
override_data {
  target          = data.aws_ssm_parameter.al2023
  override_during = plan
  values          = { value = "ami-00000000000000001" }
}
override_data {
  target          = data.aws_ami.al2023
  override_during = plan
  values          = { id = "ami-00000000000000001", architecture = "arm64" }
}
variables {
  account_id          = "123456789012"
  vpc_id              = "vpc-00000000000000001"
  subnet_id           = "subnet-00000000000000001"
  media_bucket        = "vintex-media-staging-123456789012"
  queue_arn           = "arn:aws:sqs:us-east-2:123456789012:vintex-ai-staging"
  ecr_repository_arns = ["arn:aws:ecr:us-east-2:123456789012:repository/vintex-backend", "arn:aws:ecr:us-east-2:123456789012:repository/freellmapi"]
  log_group_arns      = ["arn:aws:logs:us-east-2:123456789012:log-group:/vintex/staging/api"]
}

run "host_arm64_sem_ingress" {
  command = plan
  module { source = "../modules/staging_host" }
  assert {
    condition     = aws_instance.staging.instance_type == "t4g.small" && aws_instance.staging.ami == data.aws_ami.al2023.id && data.aws_ami.al2023.architecture == "arm64"
    error_message = "Host deve ser t4g.small com AMI ARM64 Amazon Linux."
  }
  assert {
    condition     = aws_instance.staging.subnet_id == var.subnet_id && aws_security_group.staging.vpc_id == var.vpc_id && aws_instance.staging.associate_public_ip_address
    error_message = "Host deve usar subnet/VPC shared com IPv4 automático."
  }
  assert {
    condition     = length(aws_security_group.staging.ingress) == 0 && one(aws_security_group.staging.egress).from_port == 443 && one(aws_security_group.staging.egress).to_port == 443 && one(aws_security_group.staging.egress).protocol == "tcp" && toset(one(aws_security_group.staging.egress).cidr_blocks) == toset(["0.0.0.0/0"])
    error_message = "Nenhum ingress; saída somente TCP 443."
  }
  assert {
    condition     = one(aws_instance.staging.root_block_device).volume_size == 10 && one(aws_instance.staging.root_block_device).volume_type == "gp3" && one(aws_instance.staging.root_block_device).encrypted && one(aws_instance.staging.root_block_device).delete_on_termination
    error_message = "Disco descartável gp3 criptografado de 10 GB."
  }
  assert {
    condition     = aws_instance.staging.metadata_options[0].http_tokens == "required" && aws_instance.staging.metadata_options[0].http_put_response_hop_limit == 2 && aws_instance.staging.metadata_options[0].http_protocol_ipv6 == "disabled"
    error_message = "IMDSv2 obrigatório com hop limit 2, IPv6 desativado."
  }
  assert {
    condition     = aws_instance.staging.tags.Environment == "staging" && aws_instance.staging.tags.Project == "Vintex" && aws_instance.staging.iam_instance_profile == aws_iam_instance_profile.staging.name && aws_instance.staging.credit_specification[0].cpu_credits == "standard"
    error_message = "Host staging deve usar seu instance profile e evitar créditos CPU pagos."
  }
  assert {
    condition     = strcontains(aws_instance.staging.user_data, "Requires=vintex-imds-guard.service") && strcontains(aws_instance.staging.user_data, "sha256sum --check --status") && strcontains(aws_instance.staging.user_data, "python3.12 -m venv") && strcontains(aws_instance.staging.user_data, "fallocate -l 1G")
    error_message = "Bootstrap deve instalar guard, Compose verificado, Python e swap sem deploy."
  }
}

run "iam_isola_staging_inclusive_policy_ssm" {
  command = plan
  module { source = "../modules/staging_host" }
  assert {
    condition     = jsondecode(aws_iam_role.instance.assume_role_policy).Statement[0].Principal.Service == "ec2.amazonaws.com" && aws_iam_role_policy_attachment.ssm.policy_arn == "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
    error_message = "Role deve ser de EC2 com agente SSM."
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.runtime.policy).Statement[0].Resource == "*" && jsondecode(aws_iam_role_policy.runtime.policy).Statement[0].Action == ["ecr:GetAuthorizationToken"] && toset(jsondecode(aws_iam_role_policy.runtime.policy).Statement[1].Resource) == toset(var.ecr_repository_arns)
    error_message = "Somente autenticação ECR permite wildcard; pull limitado aos dois repositórios."
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.runtime.policy).Statement[2].Resource == "arn:aws:s3:::${var.media_bucket}" && jsondecode(aws_iam_role_policy.runtime.policy).Statement[3].Resource == "arn:aws:s3:::${var.media_bucket}/*" && jsondecode(aws_iam_role_policy.runtime.policy).Statement[4].Resource == var.queue_arn
    error_message = "Mídia e fila devem ser somente staging, sem DLQ ou backups."
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.runtime.policy).Statement[5].Resource == "arn:aws:ssm:us-east-2:${var.account_id}:parameter/vintex/staging/*" && jsondecode(aws_iam_role_policy.runtime.policy).Statement[6].Effect == "Deny" && jsondecode(aws_iam_role_policy.runtime.policy).Statement[6].NotResource == "arn:aws:ssm:us-east-2:${var.account_id}:parameter/vintex/staging/*" && jsondecode(aws_iam_role_policy.runtime.policy).Statement[6].Action == ["ssm:GetParameter*"]
    error_message = "Negação explícita precisa limitar também o GetParameter irrestrito da policy gerenciada SSM."
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.runtime.policy).Statement[7].Resource == ["arn:aws:logs:us-east-2:123456789012:log-group:/vintex/staging/api:log-stream:*"] && !strcontains(aws_iam_role_policy.runtime.policy, "vintex-prod") && !strcontains(aws_iam_role_policy.runtime.policy, "ecr:PutImage") && !strcontains(aws_iam_role_policy.runtime.policy, "iam:PassRole")
    error_message = "Logs restritos e sem poderes de produção, push de imagem ou IAM."
  }
}

run "preview_aberto_libera_so_http_do_cloudfront" {
  command = plan
  module { source = "../modules/staging_host" }
  variables { public_http_from_cloudfront = true }
  assert {
    condition     = length(aws_security_group.staging.ingress) == 1 && one(aws_security_group.staging.ingress).from_port == 80 && one(aws_security_group.staging.ingress).to_port == 80 && one(aws_security_group.staging.ingress).protocol == "tcp"
    error_message = "O preview deve abrir somente a porta 80/TCP."
  }
  assert {
    condition     = length(one(aws_security_group.staging.ingress).cidr_blocks) == 0 && length(one(aws_security_group.staging.ingress).ipv6_cidr_blocks) == 0 && length(one(aws_security_group.staging.ingress).prefix_list_ids) == 1
    error_message = "A origem deve ser apenas a lista gerenciada do CloudFront, nunca CIDR aberto."
  }
  assert {
    condition     = data.aws_ec2_managed_prefix_list.cloudfront[0].name == "com.amazonaws.global.cloudfront.origin-facing"
    error_message = "A lista deve ser a de origem do CloudFront."
  }
  assert {
    condition     = one(aws_security_group.staging.egress).from_port == 443 && one(aws_security_group.staging.egress).to_port == 443
    error_message = "A saída continua somente TCP 443."
  }
}
