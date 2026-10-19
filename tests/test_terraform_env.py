"""Seleção de ambiente e planos manuais sem chamar Terraform/AWS."""

import json
import subprocess
from pathlib import Path

import pytest

from scripts.infra import terraform_env as tf


@pytest.fixture
def setup_runner(tmp_path, monkeypatch):
    base = tmp_path / "infra/terraform"
    for name in ("aws", "bootstrap", "modules", "config"):
        (base / name).mkdir(parents=True)
    (base / "aws/main.tf").write_text("# test\n")
    for name in ("shared", "staging"):
        (base / f"config/{name}.tfvars").write_text(f'deployment = "{name}"\n')
    account = base / "account.tfvars.json"
    tf.write_private(
        account,
        {
            "expected_account_id": "123456789012",
            "state_bucket": "vintex-terraform-state-123456789012",
            "budget_email_addresses": ["infra@example.test"],
        },
    )
    calls = []

    def run(command, *, env, check):
        assert check
        calls.append((command, env))
        for arg in command:
            if arg.startswith("-out="):
                Path(arg.removeprefix("-out=")).write_bytes(b"saved plan")

    monkeypatch.setattr(tf.subprocess, "run", run)
    for key in list(tf.os.environ):
        if key.startswith("TF_CLI_ARGS") or key == "TF_WORKSPACE":
            monkeypatch.delenv(key)
    return base, account, calls


@pytest.mark.parametrize("environment", tf.ENVIRONMENTS)
def test_backend_and_plan_are_selected_by_environment(setup_runner, environment):
    base, account, calls = setup_runner
    tf.execute(environment, "init", account, base)
    tf.execute(environment, "plan", account, base)
    runtime = base / ".terraform" / environment
    config = json.loads((runtime / "backend.tfbackend.json").read_text())
    assert calls[0][1]["TF_DATA_DIR"] == str(runtime / "data")
    assert calls[0][1]["TF_WORKSPACE"] == "default"
    assert "-reconfigure" in calls[0][0]
    assert "-lockfile=readonly" in calls[0][0]
    assert not any("apply" in command for command, _ in calls)
    assert f"-var-file={account}" in calls[1][0]
    if environment == "bootstrap":
        assert config == {"path": str(runtime / "bootstrap.tfstate")}
        assert f"-chdir={base / 'bootstrap'}" in calls[0][0]
    else:
        assert config["key"] == f"vintex/{environment}/terraform.tfstate"
        assert config["region"] == "us-east-2"
        assert config["allowed_account_ids"] == ["123456789012"]
        assert config["encrypt"] and config["use_lockfile"]
        assert f"-chdir={base / 'aws'}" in calls[0][0]
        assert f"-var-file={base / f'config/{environment}.tfvars'}" in calls[1][0]
    assert (runtime.stat().st_mode & 0o777) == 0o700
    for name in (
        "backend.tfbackend.json",
        "initialized.json",
        "deploy.tfplan",
        "plan.json",
    ):
        assert (runtime / name).stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("change", ["account", "source", "module", "profile", "plan"])
def test_apply_refuses_stale_plan(setup_runner, change):
    base, account, calls = setup_runner
    tf.execute("staging", "init", account, base)
    tf.execute("staging", "plan", account, base)
    if change == "account":
        config = json.loads(account.read_text())
        config["budget_email_addresses"] = ["other@example.test"]
        tf.write_private(account, config)
    else:
        target = {
            "source": "aws/main.tf",
            "module": "modules/change.tf",
            "profile": "config/staging.tfvars",
            "plan": ".terraform/staging/deploy.tfplan",
        }[change]
        (base / target).write_text(
            'deployment = "staging"\n\n' if change == "profile" else "changed"
        )
    with pytest.raises(ValueError, match="obsoleto"):
        tf.execute("staging", "apply", account, base)
    assert len(calls) == 2


def test_apply_requires_correct_initialization_and_confirmation(
    setup_runner, monkeypatch
):
    base, account, calls = setup_runner
    with pytest.raises(ValueError, match="terraform-init"):
        tf.execute("staging", "apply", account, base)
    tf.execute("staging", "init", account, base)
    with pytest.raises(ValueError, match="terraform-plan"):
        tf.execute("staging", "apply", account, base)
    tf.execute("staging", "plan", account, base)
    monkeypatch.setattr("builtins.input", lambda _: "shared")
    with pytest.raises(ValueError, match="cancelado"):
        tf.execute("staging", "apply", account, base)
    monkeypatch.setattr("builtins.input", lambda _: "staging")
    tf.execute("staging", "apply", account, base)
    assert calls[-1][0][-3:] == [
        "apply",
        "-input=false",
        str(base / ".terraform/staging/deploy.tfplan"),
    ]
    assert not (base / ".terraform/staging/plan.json").exists()


def test_failed_apply_invalidates_plan(setup_runner, monkeypatch):
    base, account, _ = setup_runner
    tf.execute("staging", "init", account, base)
    tf.execute("staging", "plan", account, base)
    monkeypatch.setattr("builtins.input", lambda _: "staging")

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr(tf.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        tf.execute("staging", "apply", account, base)
    assert not (base / ".terraform/staging/plan.json").exists()


def test_apply_rechecks_changes_during_confirmation(setup_runner, monkeypatch):
    base, account, calls = setup_runner
    tf.execute("staging", "init", account, base)
    tf.execute("staging", "plan", account, base)

    def confirm(_):
        account.write_text(account.read_text() + "\n")
        return "staging"

    monkeypatch.setattr("builtins.input", confirm)
    with pytest.raises(ValueError, match="durante a confirmação"):
        tf.execute("staging", "apply", account, base)
    assert len(calls) == 2


@pytest.mark.parametrize(
    "variable,value", [("TF_WORKSPACE", "prod"), ("TF_CLI_ARGS", "-destroy")]
)
def test_environment_overrides_are_rejected(setup_runner, monkeypatch, variable, value):
    base, account, calls = setup_runner
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValueError):
        tf.execute("staging", "init", account, base)
    assert calls == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_account_id", "invalid"),
        ("state_bucket", "INVALID"),
        ("budget_email_addresses", []),
        ("budget_email_addresses", ["not-email"]),
        ("budget_email_addresses", [f"a{i}@example.test" for i in range(11)]),
        ("access_key", "not-allowed"),
    ],
)
def test_invalid_account_configuration_is_rejected(setup_runner, field, value):
    base, account, calls = setup_runner
    config = json.loads(account.read_text())
    config[field] = value
    tf.write_private(account, config)
    with pytest.raises(ValueError):
        tf.execute("shared", "init", account, base)
    assert calls == []


def test_bootstrap_works_without_budget_email_and_preserves_existing_state(
    setup_runner,
):
    base, account, calls = setup_runner
    config = json.loads(account.read_text())
    config["budget_email_addresses"] = []
    tf.write_private(account, config)
    tf.execute("bootstrap", "init", account, base)
    (base / ".terraform/bootstrap/bootstrap.tfstate").write_text("existing")
    config["state_bucket"] = "other-state-bucket"
    tf.write_private(account, config)
    with pytest.raises(ValueError, match="já possui state"):
        tf.execute("bootstrap", "init", account, base)
    assert len(calls) == 1


def test_wrong_environment_or_account_cannot_reuse_init_or_plan(setup_runner):
    base, account, _ = setup_runner
    tf.execute("shared", "init", account, base)
    tf.execute("shared", "plan", account, base)
    with pytest.raises(ValueError, match="terraform-init"):
        tf.execute("staging", "apply", account, base)
    config = json.loads(account.read_text())
    config["expected_account_id"] = "999999999999"
    tf.write_private(account, config)
    with pytest.raises(ValueError, match="terraform-init"):
        tf.execute("shared", "apply", account, base)


def test_profile_cannot_select_shared_in_staging_state(setup_runner):
    base, account, calls = setup_runner
    (base / "config/staging.tfvars").write_text('deployment = "shared"\n')
    with pytest.raises(ValueError, match="não corresponde"):
        tf.execute("staging", "init", account, base)
    assert calls == []


def test_unknown_environment_and_local_apply_are_rejected(setup_runner):
    base, account, calls = setup_runner
    for environment in ("local", "prod", "typo"):
        with pytest.raises(ValueError, match="não suportado"):
            tf.execute(environment, "apply", account, base)
    assert calls == []


def test_bootstrap_lifecycle_moves_and_private_configuration_guards():
    root = Path(__file__).resolve().parents[1]
    bootstrap = (tf.BASE / "bootstrap/main.tf").read_text()
    assert "prevent_destroy = true" in bootstrap
    assert 'backend "local" {}' in bootstrap
    moves = (tf.BASE / "aws/moved.tf").read_text()
    for module in ("network", "registry", "budget", "services", "host", "scheduler"):
        assert f"from = module.{module}\n" in moves
        assert f"to   = module.{module}[0]" in moves
    for file in (".gitignore", ".dockerignore"):
        assert "infra/terraform/account.tfvars.json" in (root / file).read_text()
    assert "**/.terraform/" in (root / ".dockerignore").read_text()
