output "media_bucket" {
  value = module.media.bucket_name
}
output "queue_arn" {
  value = module.messaging.processing_queue_arn
}
output "queue_url" {
  value = module.messaging.processing_queue_url
}
output "dead_letter_queue_url" {
  value = module.messaging.dead_letter_queue_url
}
output "log_group_arns" {
  value = [for group in aws_cloudwatch_log_group.runtime : group.arn]
}
output "log_group_names" {
  value = [for group in aws_cloudwatch_log_group.runtime : group.name]
}
