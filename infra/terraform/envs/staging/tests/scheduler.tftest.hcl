mock_provider "aws" {}
variables {
  account_id   = "123456789012"
  instance_id  = "i-00000000000000001"
  instance_arn = "arn:aws:ec2:us-east-2:123456789012:instance/i-00000000000000001"
}
override_resource {
  target          = aws_scheduler_schedule_group.staging
  override_during = plan
  values          = { arn = "arn:aws:scheduler:us-east-2:123456789012:schedule-group/vintex-staging" }
}
run "horarios_brasilia_e_alvo_exclusivo" {
  command = plan
  module { source = "../../modules/staging_schedule" }
  assert {
    condition     = output.schedules.start.expression == "cron(0 10 ? * MON-FRI *)" && output.schedules.stop.expression == "cron(0 22 ? * MON-FRI *)" && output.schedules.sweep.expression == "cron(0 2 * * ? *)"
    error_message = "Horários devem ser 10h/22h em dias úteis e 02h diariamente."
  }
  assert {
    condition     = alltrue([for schedule in aws_scheduler_schedule.staging : schedule.schedule_expression_timezone == "America/Sao_Paulo" && schedule.flexible_time_window[0].mode == "OFF" && schedule.state == "ENABLED" && jsondecode(schedule.target[0].input).InstanceIds == [var.instance_id] && schedule.target[0].retry_policy[0].maximum_event_age_in_seconds == 300])
    error_message = "Agendamentos devem usar Brasília e apenas a instância staging, sem retries tardios."
  }
  assert {
    condition     = aws_scheduler_schedule.staging["start"].target[0].arn == "arn:aws:scheduler:::aws-sdk:ec2:startInstances" && aws_scheduler_schedule.staging["stop"].target[0].arn == "arn:aws:scheduler:::aws-sdk:ec2:stopInstances"
    error_message = "Alvos universais precisam chamar StartInstances e StopInstances."
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.scheduler.policy).Statement[0].Resource == var.instance_arn && jsondecode(aws_iam_role_policy.scheduler.policy).Statement[0].Condition.StringEquals["ec2:ResourceTag/Environment"] == "staging" && toset(jsondecode(aws_iam_role_policy.scheduler.policy).Statement[0].Action) == toset(["ec2:StartInstances", "ec2:StopInstances"])
    error_message = "Scheduler deve controlar somente o ARN da staging, também condicionado por tag."
  }
  assert {
    condition     = jsondecode(aws_iam_role.scheduler.assume_role_policy).Statement[0].Principal.Service == "scheduler.amazonaws.com" && jsondecode(aws_iam_role.scheduler.assume_role_policy).Statement[0].Condition.StringEquals["aws:SourceAccount"] == var.account_id && jsondecode(aws_iam_role.scheduler.assume_role_policy).Statement[0].Condition.ArnEquals["aws:SourceArn"] == aws_scheduler_schedule_group.staging.arn
    error_message = "Trust deve exigir Scheduler da conta e grupo específicos."
  }
}
