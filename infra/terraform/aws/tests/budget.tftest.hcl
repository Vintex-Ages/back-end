mock_provider "aws" {}

run "teto_e_alertas_da_conta_vintex" {
  command = plan
  module {
    source = "../modules/project_budget"
  }
  variables {
    account_id      = "123456789012"
    email_addresses = ["ages3@example.test", "ages4@example.test"]
  }

  assert {
    condition = (aws_budgets_budget.this.account_id == "123456789012" && aws_budgets_budget.this.budget_type == "COST" &&
    aws_budgets_budget.this.limit_amount == "35" && aws_budgets_budget.this.limit_unit == "USD" && aws_budgets_budget.this.time_unit == "MONTHLY")
    error_message = "Budget mensal deve acompanhar o teto de US$35 da conta dedicada."
  }
  assert {
    condition = length(aws_budgets_budget.this.notification) == 4 && toset([
      for n in aws_budgets_budget.this.notification : "${n.notification_type}:${n.threshold}"
    ]) == toset(["ACTUAL:28", "ACTUAL:30", "ACTUAL:35", "FORECASTED:30"])
    error_message = "Os quatro alertas devem seguir os valores absolutos da especificação."
  }
  assert {
    condition = alltrue([
      for n in aws_budgets_budget.this.notification : n.threshold_type == "ABSOLUTE_VALUE" &&
      n.comparison_operator == "GREATER_THAN" && n.subscriber_email_addresses == toset(var.email_addresses)
    ])
    error_message = "Alertas devem usar valores em USD e somente os destinatários locais."
  }
  assert {
    condition     = length(aws_budgets_budget.this.cost_filter) == 0 && length(aws_budgets_budget.this.filter_expression) == 0
    error_message = "Conta dedicada: custos sem tags também devem entrar no Budget."
  }
}
