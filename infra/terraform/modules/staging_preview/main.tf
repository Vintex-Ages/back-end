# IP fixo da instância: o DNS público dela muda a cada stop/start (Scheduler
# 10h-22h), e o CloudFront precisa de um nome de origem estável. A cobrança do
# IPv4 público é por hora, com a instância ligada ou não.
resource "aws_eip" "preview" {
  domain = "vpc"
  tags = {
    Name        = "vintex-staging-preview"
    Environment = "staging"
    Project     = "Vintex"
  }
}

resource "aws_eip_association" "preview" {
  instance_id   = var.instance_id
  allocation_id = aws_eip.preview.id
}

locals {
  # Políticas gerenciadas do CloudFront (IDs fixos, documentados pela AWS).
  caching_disabled_policy        = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
  caching_optimized_policy       = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  all_viewer_except_host_request = "b689b0a8-53d0-40ab-baf2-68738e2966ac"
  ec2_origin_id                  = "staging-ec2"
  offline_origin_id              = "offline-s3"
  offline_page_path              = "/offline/index.html"
}

# Segredo que só o CloudFront desta distribuição conhece: o Nginx recusa
# requisições sem ele, porque a lista gerenciada do CloudFront cobre todas as
# distribuições do mundo. A instância lê o mesmo valor do Parameter Store.
resource "random_password" "origin_verify" {
  length  = 48
  special = false
}

resource "aws_ssm_parameter" "origin_verify" {
  name  = "/vintex/staging/origin_verify"
  type  = "SecureString"
  value = random_password.origin_verify.result
}

# Página "staging fora do horário", servida quando a origem está parada.
resource "aws_s3_bucket" "offline" {
  bucket        = "vintex-offline-staging-${var.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "offline" {
  bucket                  = aws_s3_bucket.offline.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "offline" {
  bucket = aws_s3_bucket.offline.id
  rule { object_ownership = "BucketOwnerEnforced" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "offline" {
  bucket = aws_s3_bucket.offline.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_object" "offline_index" {
  bucket       = aws_s3_bucket.offline.id
  key          = "offline/index.html"
  content      = file("${path.module}/offline.html")
  content_type = "text/html; charset=utf-8"
  etag         = filemd5("${path.module}/offline.html")
}

resource "aws_cloudfront_origin_access_control" "offline" {
  name                              = "vintex-staging-offline"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_function" "guard" {
  name    = "vintex-staging-preview-guard"
  runtime = "cloudfront-js-2.0"
  comment = "Fecha o cadastro publico na staging"
  publish = true
  code    = file("${path.module}/function.js")
}

resource "aws_cloudfront_distribution" "preview" {
  enabled         = true
  is_ipv6_enabled = true
  http_version    = "http2and3"
  price_class     = "PriceClass_100"
  comment         = "Vintex staging (preview aberto)"

  # Origem dinâmica: Nginx da EC2 (SPA e proxy da API). O DNS da EC2 não aceita
  # certificado público, então este trecho é HTTP; o segredo evita que outras
  # distribuições do CloudFront usem a instância.
  origin {
    origin_id           = local.ec2_origin_id
    domain_name         = aws_eip.preview.public_dns
    connection_attempts = 1
    connection_timeout  = 3
    custom_origin_config {
      http_port                = 80
      https_port               = 443
      origin_protocol_policy   = "http-only"
      origin_ssl_protocols     = ["TLSv1.2"]
      origin_read_timeout      = 30
      origin_keepalive_timeout = 5
    }
    custom_header {
      name  = "X-Origin-Verify"
      value = random_password.origin_verify.result
    }
  }

  # Página offline: nunca depende da instância estar de pé.
  origin {
    origin_id                = local.offline_origin_id
    domain_name              = aws_s3_bucket.offline.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.offline.id
  }

  default_cache_behavior {
    target_origin_id         = local.ec2_origin_id
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = local.caching_disabled_policy
    origin_request_policy_id = local.all_viewer_except_host_request
    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.guard.arn
    }
  }

  ordered_cache_behavior {
    path_pattern           = "/offline/*"
    target_origin_id       = local.offline_origin_id
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = local.caching_optimized_policy
  }

  ordered_cache_behavior {
    path_pattern             = "/assets/*"
    target_origin_id         = local.ec2_origin_id
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = local.caching_optimized_policy
    origin_request_policy_id = local.all_viewer_except_host_request
  }

  # Origem parada (fora do horário) ou inalcançável: mostra a página offline.
  dynamic "custom_error_response" {
    for_each = toset([502, 503, 504])
    content {
      error_code            = custom_error_response.value
      response_code         = 503
      response_page_path    = local.offline_page_path
      error_caching_min_ttl = 10
    }
  }

  restrictions {
    geo_restriction { restriction_type = "none" }
  }

  # Sem domínio próprio: certificado padrão *.cloudfront.net.
  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Name        = "vintex-staging-preview"
    Environment = "staging"
    Project     = "Vintex"
  }
}

data "aws_iam_policy_document" "offline" {
  statement {
    sid       = "CloudFrontLeSoAPaginaOffline"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.offline.arn}/offline/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.preview.arn]
    }
  }
  statement {
    sid       = "ExigeTLS"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.offline.arn, "${aws_s3_bucket.offline.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "offline" {
  bucket = aws_s3_bucket.offline.id
  policy = data.aws_iam_policy_document.offline.json
}
