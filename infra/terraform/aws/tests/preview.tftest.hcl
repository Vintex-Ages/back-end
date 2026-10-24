mock_provider "aws" {}

variables {
  instance_id = "i-00000000000000001"
}

run "ip_elastico_associado_a_instancia" {
  command = plan
  module { source = "../modules/staging_preview" }
  assert {
    condition     = aws_eip.preview.domain == "vpc" && aws_eip_association.preview.instance_id == "i-00000000000000001"
    error_message = "O IP elástico deve ser de VPC e associado à instância da staging."
  }
  assert {
    condition     = aws_eip.preview.tags.Environment == "staging" && aws_eip.preview.tags.Project == "Vintex"
    error_message = "O IP deve carregar as tags do projeto."
  }
}
