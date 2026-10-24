"""Guardrails de provider/backend que o mock AWS não executa (#272)."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "infra/terraform/aws"


def test_shared_provider_uses_ohio_expected_account_and_standard_tags():
    source = (SHARED / "main.tf").read_text()
    provider = re.search(r'provider "aws" \{(.*?)\n\}', source, re.DOTALL)
    assert provider is not None
    body = provider.group(1)
    assert re.search(r'aws_region\s*=\s*"us-east-2"', source)
    assert re.search(r"region\s*=\s*local.aws_region", body)
    assert re.search(r"allowed_account_ids\s*=\s*\[var.expected_account_id\]", body)
    assert re.search(r'Project\s*=\s*"Vintex"', body)
    assert re.search(r"Environment\s*=\s*var.deployment", body)
    assert re.search(r'ManagedBy\s*=\s*"Terraform"', body)
    for forbidden in (
        "access_key",
        "secret_key",
        "token",
        "endpoints",
        "skip_credentials_validation",
        "skip_requesting_account_id",
        "skip_metadata_api_check",
        "s3_use_path_style",
    ):
        assert not re.search(rf"\b{forbidden}\b", body)


def test_state_is_separate_encrypted_and_uses_native_lock():
    source = (SHARED / "versions.tf").read_text()
    assert 'backend "s3" {}' in source


@pytest.mark.parametrize("test_file", sorted((SHARED / "tests").glob("*.tftest.hcl")))
def test_shared_tests_only_plan_with_mock_provider(test_file):
    source = test_file.read_text()
    assert re.search(r'mock_provider "aws"\s*\{', source)
    assert re.search(r"command\s*=\s*plan", source)
    assert not re.search(r"command\s*=\s*apply", source)
