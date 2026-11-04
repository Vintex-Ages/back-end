output "schedules" {
  value = { for key, schedule in aws_scheduler_schedule.staging : key => {
    name       = schedule.name
    expression = schedule.schedule_expression
    timezone   = schedule.schedule_expression_timezone
  } }
}
