# Plano mockado: não cria bucket no LocalStack nem na AWS.
mock_provider "aws" {}

run "bucket_privado_e_prefixos" {
  command = plan

  assert {
    condition     = output.media_bucket_name == "vintex-local-media"
    error_message = "O bucket local deve coincidir com a configuração do Compose."
  }

  assert {
    condition = output.media_prefixes == {
      photo   = "products/photos/"
      video   = "products/videos/"
      receipt = "payments/receipts/"
    }
    error_message = "Os prefixos devem separar fotos, vídeos e comprovantes."
  }

  assert {
    condition     = alltrue(values(output.media_public_access_block))
    error_message = "O bucket de mídia deve bloquear todo acesso público."
  }
}
