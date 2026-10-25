locals {
  schedules = {
    start = { expression = "cron(0 10 ? * MON-FRI *)", operation = "startInstances" }
    stop  = { expression = "cron(0 22 ? * MON-FRI *)", operation = "stopInstances" }
    sweep = { expression = "cron(0 2 * * ? *)", operation = "stopInstances" }
  }
}

resource "aws_scheduler_schedule_group" "staging" {
  name = "vintex-staging"
}

resource "aws_iam_role" "scheduler" {
  name = "VintexStagingSchedulerRole"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "scheduler.amazonaws.com" }
      Condition = {
        StringEquals = { "aws:SourceAccount" = var.account_id }
        ArnEquals    = { "aws:SourceArn" = aws_scheduler_schedule_group.staging.arn }
      }
    }]
  })
}

resource "aws_iam_role_policy" "scheduler" {
  name = "vintex-staging-start-stop"
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = ["ec2:StartInstances", "ec2:StopInstances"]
      Resource  = var.instance_arn
      Condition = { StringEquals = { "ec2:ResourceTag/Environment" = "staging", "ec2:ResourceTag/Project" = "Vintex" } }
    }]
  })
}

resource "aws_scheduler_schedule" "staging" {
  for_each                     = local.schedules
  name                         = "vintex-staging-${each.key}"
  group_name                   = aws_scheduler_schedule_group.staging.name
  schedule_expression          = each.value.expression
  schedule_expression_timezone = "America/Sao_Paulo"
  state                        = "ENABLED"
  flexible_time_window { mode = "OFF" }
  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ec2:${each.value.operation}"
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ InstanceIds = [var.instance_id] })
    # A late start must not undo the next shutdown; no retries hours later.
    retry_policy {
      maximum_event_age_in_seconds = 300
      maximum_retry_attempts       = 2
    }
  }
  depends_on = [aws_iam_role_policy.scheduler]
}
