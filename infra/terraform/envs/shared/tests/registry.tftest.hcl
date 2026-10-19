mock_provider "aws" {}

run "imagens_imutaveis_e_scan" {
  command = plan
  module {
    source = "../../modules/container_registry"
  }

  assert {
    condition     = toset(keys(aws_ecr_repository.this)) == toset(["vintex-backend", "freellmapi"])
    error_message = "API e worker compartilham uma imagem; só dois repositórios ECR."
  }
  assert {
    condition = alltrue([
      for repo in aws_ecr_repository.this : repo.image_tag_mutability == "IMMUTABLE" &&
      repo.image_scanning_configuration[0].scan_on_push && !repo.force_delete &&
      repo.encryption_configuration[0].encryption_type == "AES256"
    ])
    error_message = "Repositórios devem ter tags imutáveis, scan no push, criptografia e proteção contra remoção forçada."
  }
  assert {
    condition = alltrue([
      for name, lifecycle in aws_ecr_lifecycle_policy.this :
      lifecycle.repository == name && jsondecode(lifecycle.policy).rules[0].selection.countNumber == 10 &&
      jsondecode(lifecycle.policy).rules[0].selection.countType == "imageCountMoreThan" &&
      jsondecode(lifecycle.policy).rules[0].selection.tagStatus == "any" &&
      jsondecode(lifecycle.policy).rules[0].action.type == "expire"
    ])
    error_message = "Cada repositório deve reter as dez imagens mais recentes."
  }
}
