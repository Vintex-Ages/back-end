"""Make CLI contract; dry runs and fake commands never contact Docker or AWS."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    shutil.which("make") is None,
    reason="Make CLI is checked on the CI checkout; the API image needs no Make",
)


def make(*args, dry_run=True):
    return subprocess.run(
        ["make", "--no-print-directory", *(["-n"] if dry_run else []), *args],
        cwd=ROOT,
        env={
            **os.environ,
            "ENV": "production",
            "TF_ENV": "staging",
            "MAKEFLAGS": "",
            "MFLAGS": "",
        },
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "action", ["validate", "test", "plan", "apply", "output", "init", "show"]
)
def test_positional_staging_is_selected(action):
    result = make(f"terraform-{action}", "staging")
    assert result.returncode == 0, result.stderr
    assert f"{action} --env staging" in result.stdout
    assert "--env local" not in result.stdout


@pytest.mark.parametrize(
    "target", ["test-unit", "lint", "infra-qa", "infra-local-test", "infra-complete"]
)
def test_generic_environment_never_breaks_local_commands(target):
    result = make(target)
    assert result.returncode == 0, result.stderr
    assert "--env staging" not in result.stdout
    assert "terraform_env.py init" not in result.stdout
    if target in {"infra-qa", "infra-local-test"}:
        assert "--env local" in result.stdout


@pytest.mark.parametrize(
    "args",
    [
        ["terraform-validate", "stagng"],
        ["terraform-validate", "local", "staging"],
        ["terraform-validate", "terraform-apply", "staging"],
        ["terraform-validate", "infra-qa", "staging"],
        ["staging"],
        ["infra-complete", "staging"],
    ],
)
def test_invalid_combinations_fail_before_any_command(args):
    result = make(*args, dry_run=False)
    assert result.returncode != 0
    assert "make " in result.stderr
    assert "Initializing" not in result.stdout


def test_aws_action_requires_explicit_environment():
    result = make("terraform-plan", dry_run=False)
    assert result.returncode != 0
    assert "make terraform-plan staging" in result.stderr


def test_deploy_selects_only_staging():
    result = make("infra-deploy", "staging")
    assert result.returncode == 0, result.stderr
    assert "deploy --env staging" in result.stdout
    result = make("infra-deploy", dry_run=False)
    assert result.returncode != 0
    assert "make infra-deploy staging" in result.stderr


def test_failed_command_stays_failed(tmp_path):
    script = tmp_path / "failed-command.sh"
    script.write_text("#!/bin/sh\nexit 37\n")
    result = make("terraform-plan", "staging", f"AWS_TF=sh {script}", dry_run=False)
    assert result.returncode != 0
    assert "37" in result.stderr
