locals {
  notifications = {
    actual_28   = { type = "ACTUAL", threshold = 28 }
    actual_30   = { type = "ACTUAL", threshold = 30 }
    actual_35   = { type = "ACTUAL", threshold = 35 }
    forecast_30 = { type = "FORECASTED", threshold = 30 }
  }
}

# Sem filtro por tag: acompanha toda a conta dedicada, inclusive custos sem tag.
resource "aws_budgets_budget" "this" {
  account_id   = var.account_id
  name         = "vintex-monthly"
  budget_type  = "COST"
  limit_amount = "35"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = local.notifications
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value.threshold
      threshold_type             = "ABSOLUTE_VALUE"
      notification_type          = notification.value.type
      subscriber_email_addresses = var.email_addresses
    }
  }
}
