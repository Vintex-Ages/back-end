output "repositories" {
  description = "Nomes, ARNs e URLs para build manual e runtime."
  value = {
    for name, repository in aws_ecr_repository.this : name => {
      name = repository.name
      arn  = repository.arn
      url  = repository.repository_url
    }
  }
}
