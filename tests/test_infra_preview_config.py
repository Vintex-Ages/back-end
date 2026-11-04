"""Contrato do preview aberto (CloudFront + IP elástico), desligado por padrão."""

import re
from pathlib import Path

TF = Path(__file__).resolve().parents[1] / "infra/terraform"
PREVIEW = TF / "modules/staging_preview"
HOST = TF / "modules/staging_host"
AWS = TF / "aws"


def _read(directory: Path, pattern: str = "*.tf") -> str:
    return "\n".join(path.read_text() for path in sorted(directory.glob(pattern)))


def test_public_preview_is_off_by_default_and_wired_through_one_module():
    variables = (AWS / "variables.tf").read_text()
    block = re.search(r'variable "public_preview" \{(.*?)\n\}', variables, re.S)
    assert block and re.search(r"default\s*=\s*false", block.group(1))
    main = (AWS / "main.tf").read_text()
    assert re.search(r'module "preview" \{[^}]*count\s*=\s*var\.public_preview', main)
    assert "public_http_from_cloudfront = var.public_preview" in main


def test_edge_resources_exist_only_in_the_preview_module():
    forbidden = ("aws_eip", "aws_cloudfront_distribution", "aws_cloudfront_function")
    for path in TF.rglob("*.tf"):
        if ".terraform" in path.parts or path.is_relative_to(PREVIEW):
            continue
        source = path.read_text()
        for resource in forbidden:
            assert not re.search(rf'resource "{resource}"', source), path


def test_origin_only_accepts_cloudfront_never_open_cidr():
    host = (HOST / "main.tf").read_text()
    ingress = re.search(
        r"ingress = var\.public_http_from_cloudfront \? \[(.*?)\] : \[\]", host, re.S
    )
    assert ingress, "o ingress deve continuar uma lista autoritativa, vazia por padrão"
    body = ingress.group(1)
    assert "from_port        = 80" in body and "to_port          = 80" in body
    assert "cidr_blocks      = []" in body and "ipv6_cidr_blocks = []" in body
    assert "com.amazonaws.global.cloudfront.origin-facing" in host
    assert "0.0.0.0/0" not in body


def test_preview_module_has_no_shell_hooks_waf_or_acm():
    source = _read(PREVIEW)
    assert '"local-exec"' not in source and '"remote-exec"' not in source
    # A SCP da conta restringe serviços regionais a us-east-2: o WAF de CloudFront
    # e o certificado ACM exigem us-east-1, então a URL é a padrão do CloudFront.
    for unsupported in ("aws_wafv2", "aws_acm_certificate", "aws_route53"):
        assert unsupported not in source
    assert "cloudfront_default_certificate = true" in source
    assert 'viewer_protocol_policy   = "redirect-to-https"' in source


def test_origin_secret_is_generated_and_stored_as_secure_string():
    source = _read(PREVIEW)
    assert 'resource "random_password" "origin_verify"' in source
    assert 'name  = "/vintex/staging/origin_verify"' in source
    assert 'type  = "SecureString"' in source
    assert 'name  = "X-Origin-Verify"' in source


def test_registration_is_closed_at_the_edge_with_normalized_path():
    code = (PREVIEW / "function.js").read_text()
    assert "/api/auth/register" in code and "REGISTRATION_CLOSED" in code
    assert "decodeURIComponent" in code and "toLowerCase" in code
    assert "request.method === 'POST'" in code
    assert "statusCode: 403" in code


def test_offline_page_is_static_and_self_contained():
    page = (PREVIEW / "offline.html").read_text()
    assert "Staging fora do horário" in page
    assert "10h às 22h" in page
    assert not re.search(r"(src|href)=[\"']https?://", page)
    assert "noindex" in page
