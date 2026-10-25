mock_provider "aws" {}
mock_provider "random" {}

# O ARN e o domínio só existem depois do apply; o plano mockado os fixa.
override_resource {
  target          = aws_cloudfront_distribution.preview
  override_during = plan
  values = {
    id          = "E00000000EXAMPLE"
    arn         = "arn:aws:cloudfront::123456789012:distribution/E00000000EXAMPLE"
    domain_name = "d111111abcdef8.cloudfront.net"
  }
}

override_resource {
  target          = aws_s3_bucket.offline
  override_during = plan
  values = {
    id                          = "vintex-offline-staging-123456789012"
    arn                         = "arn:aws:s3:::vintex-offline-staging-123456789012"
    bucket_regional_domain_name = "vintex-offline-staging-123456789012.s3.us-east-2.amazonaws.com"
  }
}

variables {
  account_id  = "123456789012"
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

run "origem_http_protegida_por_segredo" {
  command = plan
  module { source = "../modules/staging_preview" }
  assert {
    condition     = [for o in aws_cloudfront_distribution.preview.origin : o.origin_id if o.origin_id == "staging-ec2"][0] == "staging-ec2"
    error_message = "Deve existir a origem dinâmica da EC2."
  }
  assert {
    condition = (
      one([for o in aws_cloudfront_distribution.preview.origin : one(o.custom_origin_config).origin_protocol_policy if o.origin_id == "staging-ec2"]) == "http-only" &&
      one([for o in aws_cloudfront_distribution.preview.origin : one(o.custom_origin_config).http_port if o.origin_id == "staging-ec2"]) == 80
    )
    error_message = "O trecho CloudFront -> EC2 é HTTP na porta 80 (o DNS da EC2 não aceita certificado público)."
  }
  assert {
    condition = (
      one([for o in aws_cloudfront_distribution.preview.origin : one(o.custom_header).name if o.origin_id == "staging-ec2"]) == "X-Origin-Verify" &&
      random_password.origin_verify.length == 48 && !random_password.origin_verify.special
    )
    error_message = "A origem deve enviar o segredo X-Origin-Verify gerado com 48 caracteres."
  }
  assert {
    condition     = aws_ssm_parameter.origin_verify.name == "/vintex/staging/origin_verify" && aws_ssm_parameter.origin_verify.type == "SecureString"
    error_message = "O segredo deve ficar num SecureString legível pela instância (/vintex/staging/*)."
  }
}

run "comportamentos_do_cloudfront" {
  command = plan
  module { source = "../modules/staging_preview" }
  assert {
    condition = (
      one(aws_cloudfront_distribution.preview.default_cache_behavior).viewer_protocol_policy == "redirect-to-https" &&
      one(aws_cloudfront_distribution.preview.default_cache_behavior).cache_policy_id == "4135ea2d-6df8-44a3-9df3-4b5a84be39ad" &&
      one(aws_cloudfront_distribution.preview.default_cache_behavior).origin_request_policy_id == "b689b0a8-53d0-40ab-baf2-68738e2966ac" &&
      length(one(aws_cloudfront_distribution.preview.default_cache_behavior).allowed_methods) == 7
    )
    error_message = "A API e a SPA passam sem cache, com HTTPS obrigatório e todos os cabeçalhos exceto Host."
  }
  assert {
    condition     = length(one(aws_cloudfront_distribution.preview.default_cache_behavior).function_association) == 1 && one(one(aws_cloudfront_distribution.preview.default_cache_behavior).function_association).event_type == "viewer-request"
    error_message = "A Function que fecha o cadastro deve rodar no viewer-request."
  }
  assert {
    condition     = toset([for b in aws_cloudfront_distribution.preview.ordered_cache_behavior : b.path_pattern]) == toset(["/offline/*", "/assets/*"])
    error_message = "Só a página offline e os assets estáticos têm comportamento próprio."
  }
  assert {
    condition     = toset([for e in aws_cloudfront_distribution.preview.custom_error_response : e.error_code]) == toset([502, 503, 504]) && alltrue([for e in aws_cloudfront_distribution.preview.custom_error_response : e.response_page_path == "/offline/index.html" && e.response_code == 503 && e.error_caching_min_ttl == 10])
    error_message = "Origem parada deve mostrar a página offline com 503 e cache curto."
  }
  assert {
    condition = (
      aws_cloudfront_distribution.preview.enabled &&
      aws_cloudfront_distribution.preview.price_class == "PriceClass_100" &&
      one(aws_cloudfront_distribution.preview.viewer_certificate).cloudfront_default_certificate &&
      one(one(aws_cloudfront_distribution.preview.restrictions).geo_restriction).restriction_type == "none"
    )
    error_message = "Sem domínio próprio: certificado padrão do CloudFront e classe de preço mais barata."
  }
}

run "pagina_offline_privada_so_para_o_cloudfront" {
  command = plan
  module { source = "../modules/staging_preview" }
  assert {
    condition     = aws_s3_bucket.offline.bucket == "vintex-offline-staging-123456789012" && aws_s3_bucket_public_access_block.offline.block_public_acls && aws_s3_bucket_public_access_block.offline.block_public_policy && aws_s3_bucket_public_access_block.offline.restrict_public_buckets
    error_message = "O bucket da página offline deve ser privado."
  }
  assert {
    condition     = aws_s3_object.offline_index.key == "offline/index.html" && aws_s3_object.offline_index.content_type == "text/html; charset=utf-8" && strcontains(aws_s3_object.offline_index.content, "Staging fora do horário")
    error_message = "A página offline deve ser publicada em offline/index.html."
  }
  assert {
    condition     = aws_cloudfront_origin_access_control.offline.origin_access_control_origin_type == "s3" && aws_cloudfront_origin_access_control.offline.signing_behavior == "always" && aws_cloudfront_origin_access_control.offline.signing_protocol == "sigv4"
    error_message = "O acesso ao S3 deve ser por OAC assinado."
  }
  assert {
    condition = (
      toset([for s in data.aws_iam_policy_document.offline.statement : s.sid]) == toset(["CloudFrontLeSoAPaginaOffline", "ExigeTLS"]) &&
      one([for s in data.aws_iam_policy_document.offline.statement : one(s.principals).identifiers if s.sid == "CloudFrontLeSoAPaginaOffline"]) == toset(["cloudfront.amazonaws.com"]) &&
      one([for s in data.aws_iam_policy_document.offline.statement : s.effect if s.sid == "ExigeTLS"]) == "Deny"
    )
    error_message = "A policy deve liberar só o serviço CloudFront e exigir TLS."
  }
}

run "function_fecha_o_cadastro" {
  command = plan
  module { source = "../modules/staging_preview" }
  assert {
    condition     = aws_cloudfront_function.guard.runtime == "cloudfront-js-2.0" && aws_cloudfront_function.guard.publish
    error_message = "A Function deve ser publicada em cloudfront-js-2.0."
  }
  assert {
    condition     = strcontains(aws_cloudfront_function.guard.code, "/api/auth/register") && strcontains(aws_cloudfront_function.guard.code, "REGISTRATION_CLOSED") && strcontains(aws_cloudfront_function.guard.code, "decodeURIComponent")
    error_message = "A Function deve bloquear POST em /api/auth/register já decodificado."
  }
}

run "saidas_do_preview" {
  command = plan
  module { source = "../modules/staging_preview" }
  assert {
    condition     = output.public_url == "https://d111111abcdef8.cloudfront.net" && output.origin_verify_parameter == "/vintex/staging/origin_verify"
    error_message = "A URL pública é a do CloudFront e o segredo fica no parâmetro combinado."
  }
}
