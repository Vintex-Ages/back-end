data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

data "aws_ami" "al2023" {
  owners = ["amazon"]
  filter {
    name   = "image-id"
    values = [nonsensitive(data.aws_ssm_parameter.al2023.value)]
  }
  filter {
    name   = "architecture"
    values = ["arm64"]
  }
}

resource "aws_security_group" "staging" {
  name        = "vintex-staging"
  description = "No ingress; SSM only; HTTPS egress"
  vpc_id      = var.vpc_id
  ingress     = []
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_iam_role" "instance" {
  name = "VintexStagingInstanceRole"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "runtime" {
  name = "vintex-staging-runtime"
  role = aws_iam_role.instance.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "EcrAuthentication"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Sid      = "PullSharedImages"
        Effect   = "Allow"
        Action   = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"]
        Resource = var.ecr_repository_arns
      },
      {
        Sid      = "ListStagingMedia"
        Effect   = "Allow"
        Action   = ["s3:ListBucket", "s3:GetBucketLocation"]
        Resource = "arn:aws:s3:::${var.media_bucket}"
      },
      {
        Sid      = "StagingMediaObjects"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "arn:aws:s3:::${var.media_bucket}/*"
      },
      {
        Sid      = "StagingAnalysisQueue"
        Effect   = "Allow"
        Action   = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility", "sqs:GetQueueAttributes", "sqs:GetQueueUrl"]
        Resource = var.queue_arn
      },
      {
        Sid      = "ReadStagingParameters"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
        Resource = "arn:aws:ssm:us-east-2:${var.account_id}:parameter/vintex/staging/*"
      },
      {
        # AmazonSSMManagedInstanceCore also grants GetParameter(s) on '*'.
        # Explicit deny is necessary to keep production parameters inaccessible.
        Sid         = "DenyParametersOutsideStaging"
        Effect      = "Deny"
        Action      = ["ssm:GetParameter*"]
        NotResource = "arn:aws:ssm:us-east-2:${var.account_id}:parameter/vintex/staging/*"
      },
      {
        Sid      = "StagingLogStreams"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = [for arn in var.log_group_arns : "${trimsuffix(arn, ":*")}:log-stream:*"]
      },
      {
        Sid      = "DescribeStagingStreams"
        Effect   = "Allow"
        Action   = ["logs:DescribeLogStreams"]
        Resource = [for arn in var.log_group_arns : "${trimsuffix(arn, ":*")}:*"]
      }
    ]
  })
}

resource "aws_iam_instance_profile" "staging" {
  name = "vintex-staging"
  role = aws_iam_role.instance.name
}

resource "aws_instance" "staging" {
  ami                         = data.aws_ami.al2023.id
  instance_type               = "t4g.small"
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = [aws_security_group.staging.id]
  associate_public_ip_address = true
  iam_instance_profile        = aws_iam_instance_profile.staging.name
  user_data_replace_on_change = false
  user_data = templatefile("${path.module}/bootstrap.sh.tftpl", {
    imds_guard_b64 = filebase64("${path.module}/../../../aws/staging/imds-guard.sh")
    imds_unit_b64  = filebase64("${path.module}/../../../aws/staging/vintex-imds-guard.service")
  })
  root_block_device {
    volume_type           = "gp3"
    volume_size           = 10
    encrypted             = true
    delete_on_termination = true
  }
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
    http_protocol_ipv6          = "disabled"
    instance_metadata_tags      = "disabled"
  }
  credit_specification {
    cpu_credits = "standard"
  }
  tags = {
    Name        = "vintex-staging"
    Environment = "staging"
    Project     = "Vintex"
  }
  lifecycle {
    ignore_changes = [ami, user_data]
  }
  depends_on = [aws_iam_role_policy.runtime, aws_iam_role_policy_attachment.ssm]
}
