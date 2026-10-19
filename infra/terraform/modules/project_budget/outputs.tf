output "budget" {
  description = "Identificação do único orçamento mensal Vintex."
  value = {
    name = aws_budgets_budget.this.name
    arn  = aws_budgets_budget.this.arn
  }
}
