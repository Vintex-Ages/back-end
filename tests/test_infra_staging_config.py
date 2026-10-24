"""Guardrails AWS staging não exercidos pelo provider mockado (#274)."""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "infra/terraform/aws"
MODULES = ROOT / "infra/terraform/modules"


def test_staging_provider_and_state_are_real_isolated_and_locked():
    source = (STAGING / "main.tf").read_text()
    provider = re.search(r'provider "aws" \{(.*?)\n\}', source, re.DOTALL)
    assert provider is not None
    assert re.search(r'aws_region\s*=\s*"us-east-2"', source)
    assert re.search(r"region\s*=\s*local.aws_region", provider.group(1))
    assert re.search(r"allowed_account_ids\s*=\s*\[var.expected_account_id\]", source)
    for name, value in (
        ("Project", "Vintex"),
        ("ManagedBy", "Terraform"),
    ):
        assert re.search(rf'{name}\s*=\s*"{value}"', source)
    for forbidden in (
        "access_key",
        "secret_key",
        "token",
        "endpoints",
        "skip_credentials_validation",
        "skip_requesting_account_id",
    ):
        assert not re.search(rf"\b{forbidden}\b", provider.group(1))
    backend = (STAGING / "versions.tf").read_text()
    assert 'backend "s3" {}' in backend
    assert re.search(r"Environment\s*=\s*var.deployment", source)
    assert 'required_version = ">= 1.16"' in backend


def test_host_and_parameter_updates_preserve_manual_values_and_instance():
    services = (MODULES / "staging_services/main.tf").read_text()
    host = (MODULES / "staging_host/main.tf").read_text()
    assert re.search(r"ignore_changes\s*=\s*\[value\]", services)
    assert re.search(r"ignore_changes\s*=\s*\[ami, user_data\]", host)
    assert "REPLACE_MANUALLY_BEFORE_DEPLOY" in services
    for directory in (
        STAGING,
        *(
            MODULES / name
            for name in ("staging_host", "staging_services", "staging_schedule")
        ),
    ):
        source = "\n".join(path.read_text() for path in directory.glob("*.tf"))
        for forbidden in (
            "aws_eip",
            "aws_db_instance",
            "aws_cloudfront_distribution",
            "aws_dlm_lifecycle_policy",
            "aws_key_pair",
            "aws_iam_access_key",
        ):
            assert not re.search(rf'resource "{forbidden}"', source)
        assert '"local-exec"' not in source
        assert '"remote-exec"' not in source


def test_bootstrap_shell_and_guard_order(tmp_path):
    source = (MODULES / "staging_host/bootstrap.sh.tftpl").read_text()
    rendered = source.replace("${imds_guard_b64}", "ZmFrZQ==").replace(
        "${imds_unit_b64}", "ZmFrZQ=="
    )
    script = tmp_path / "bootstrap.sh"
    script.write_text(rendered)
    subprocess.run(["bash", "-n", str(script)], check=True)
    assert source.index(
        "systemctl enable --now vintex-imds-guard.service"
    ) < source.index("systemctl enable --now docker")
    assert "Requires=vintex-imds-guard.service" in source
    assert "docker-compose-linux-aarch64" in source
    assert "sha256sum --check --status" in source
    assert "python3.12 -m venv" in source
    assert "docker compose up" not in source
    assert "ssm get-parameter" not in source
    assert "AWS_ACCESS_KEY_ID" not in source


@pytest.mark.parametrize("test_file", sorted((STAGING / "tests").glob("*.tftest.hcl")))
def test_staging_plans_are_mocked_without_apply(test_file):
    source = test_file.read_text()
    assert 'mock_provider "aws"' in source
    assert re.search(r"command\s*=\s*plan", source)
    assert not re.search(r"command\s*=\s*apply", source)
