"""Seleção de ambiente e planos manuais sem chamar Terraform/AWS."""

import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

from scripts.infra import terraform_env as tf

INSPECT_AWS = tf.inspect_aws


@pytest.fixture
def setup_runner(tmp_path, monkeypatch):
    base = tmp_path / "infra/terraform"
    for name in ("aws", "bootstrap", "modules", "config", "envs/local"):
        (base / name).mkdir(parents=True)
    (base / "aws/main.tf").write_text("# test\n")
    for name in ("staging",):
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
    monkeypatch.setattr(tf, "inspect_aws", lambda *args, **kwargs: True)
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
        assert config == {"path": str(base / "state/bootstrap/terraform.tfstate")}
        assert f"-chdir={base / 'bootstrap'}" in calls[0][0]
    else:
        assert config["key"] == f"vintex/{environment}/terraform.tfstate"
        assert config["region"] == "us-east-2"
        assert config["allowed_account_ids"] == ["123456789012"]
        assert config["encrypt"] and config["use_lockfile"]
        assert f"-chdir={base / 'aws'}" in calls[0][0]
        assert f"-var-file={base / f'config/{environment}.tfvars'}" in calls[1][0]
    assert (runtime.stat().st_mode & 0o777) == 0o700
    marker = (
        (base / "state/bootstrap/identity.json")
        if environment == "bootstrap"
        else runtime / "initialized.json"
    )
    assert marker.stat().st_mode & 0o777 == 0o600
    for name in (
        "backend.tfbackend.json",
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
        ("enable_budget", "nao"),
        ("enable_budget", 1),
        ("public_preview", "sim"),
        ("public_preview", 1),
    ],
)
def test_invalid_account_configuration_is_rejected(setup_runner, field, value):
    base, account, calls = setup_runner
    config = json.loads(account.read_text())
    config[field] = value
    tf.write_private(account, config)
    with pytest.raises(ValueError):
        tf.execute("staging", "init", account, base)
    assert calls == []


def test_public_preview_flag_is_an_accepted_optional_boolean(setup_runner):
    base, account, calls = setup_runner
    config = json.loads(account.read_text())
    config["public_preview"] = True
    tf.write_private(account, config)
    tf.execute("staging", "init", account, base)
    assert len(calls) == 1


def test_staging_works_without_budget_emails_when_budget_is_disabled(setup_runner):
    base, account, calls = setup_runner
    config = json.loads(account.read_text())
    config["enable_budget"] = False
    config["budget_email_addresses"] = []
    tf.write_private(account, config)
    tf.execute("staging", "init", account, base)
    assert len(calls) == 1


def test_budget_emails_are_still_required_when_budget_is_explicitly_enabled(
    setup_runner,
):
    base, account, calls = setup_runner
    config = json.loads(account.read_text())
    config["enable_budget"] = True
    config["budget_email_addresses"] = []
    tf.write_private(account, config)
    with pytest.raises(ValueError, match="e-mails reais"):
        tf.execute("staging", "init", account, base)
    assert calls == []


def test_bootstrap_works_without_budget_email_and_preserves_existing_state(
    setup_runner,
):
    base, account, calls = setup_runner
    config = json.loads(account.read_text())
    config["budget_email_addresses"] = []
    tf.write_private(account, config)
    tf.execute("bootstrap", "init", account, base)
    (base / "state/bootstrap/terraform.tfstate").write_text("existing")
    config["state_bucket"] = "other-state-bucket"
    tf.write_private(account, config)
    with pytest.raises(ValueError, match="já possui state"):
        tf.execute("bootstrap", "init", account, base)
    assert len(calls) == 1


def test_wrong_environment_or_account_cannot_reuse_init_or_plan(setup_runner):
    base, account, _ = setup_runner
    tf.execute("bootstrap", "init", account, base)
    tf.execute("bootstrap", "plan", account, base)
    with pytest.raises(ValueError, match="terraform-init"):
        tf.execute("staging", "apply", account, base)
    tf.execute("staging", "init", account, base)
    config = json.loads(account.read_text())
    config["expected_account_id"] = "999999999999"
    tf.write_private(account, config)
    with pytest.raises(ValueError, match="terraform-init"):
        tf.execute("staging", "apply", account, base)


def test_profile_cannot_select_shared_in_staging_state(setup_runner):
    base, account, calls = setup_runner
    (base / "config/staging.tfvars").write_text('deployment = "shared"\n')
    with pytest.raises(ValueError, match="não corresponde"):
        tf.execute("staging", "init", account, base)
    assert calls == []


def test_unknown_environment_and_local_apply_are_rejected(setup_runner):
    base, account, calls = setup_runner
    for environment in ("local", "prod", "shared", "typo"):
        with pytest.raises(ValueError, match="não suportado"):
            tf.execute(environment, "apply", account, base)
    assert calls == []


def test_bootstrap_lifecycle_and_private_configuration_guards():
    root = Path(__file__).resolve().parents[1]
    bootstrap = (tf.BASE / "bootstrap/main.tf").read_text()
    assert "prevent_destroy = true" in bootstrap
    assert 'backend "local" {}' in bootstrap
    assert not (tf.BASE / "aws/moved.tf").exists()
    assert "infra/terraform/account.tfvars.json" in (root / ".dockerignore").read_text()
    assert "**/.terraform/" in (root / ".dockerignore").read_text()
    assert "infra/terraform/state/" in (root / ".dockerignore").read_text()


@pytest.mark.skipif(
    not (tf.BASE.parents[1] / ".gitignore").exists(),
    reason="a imagem da API exclui metadados Git; CI verifica no checkout",
)
def test_account_configuration_is_ignored_by_git():
    assert "/infra/terraform/state/" in (tf.BASE.parents[1] / ".gitignore").read_text()
    assert (
        "infra/terraform/account.tfvars.json"
        in (tf.BASE.parents[1] / ".gitignore").read_text()
    )


@pytest.mark.parametrize("environment", ["local", "bootstrap", "staging"])
@pytest.mark.parametrize("action", ["validate", "test"])
def test_qa_never_reads_account_or_operational_backend(
    setup_runner, environment, action
):
    base, account, calls = setup_runner
    account.unlink()
    tf.execute(environment, action, account, base)
    assert "-backend=false" in calls[0][0]
    assert "-lockfile=readonly" in calls[0][0]
    assert calls[1][0][-1] == action
    assert calls[0][1]["TF_DATA_DIR"] == str(
        base / ".terraform/qa" / environment / "data"
    )
    assert not (base / "state").exists()
    assert not any("-var-file" in arg for call, _ in calls for arg in call)


def test_bootstrap_survives_cache_cleanup(setup_runner):
    base, account, _ = setup_runner
    tf.execute("bootstrap", "init", account, base)
    state = base / "state/bootstrap/terraform.tfstate"
    state.write_text("preserved state")
    shutil.rmtree(base / ".terraform")
    tf.execute("bootstrap", "init", account, base)
    assert state.read_text() == "preserved state"
    config = json.loads(
        (base / ".terraform/bootstrap/backend.tfbackend.json").read_text()
    )
    assert config["path"] == str(state)


def test_bootstrap_backup_can_be_restored_at_another_checkout_path(setup_runner):
    base, account, _ = setup_runner
    tf.execute("bootstrap", "init", account, base)
    (base / "state/bootstrap/terraform.tfstate").write_text("backup state")
    restored = base.parent / "restored"
    shutil.copytree(base, restored, ignore=shutil.ignore_patterns(".terraform"))
    tf.execute("bootstrap", "init", restored / "account.tfvars.json", restored)
    assert (
        restored / "state/bootstrap/terraform.tfstate"
    ).read_text() == "backup state"
    assert json.loads(
        (restored / ".terraform/bootstrap/backend.tfbackend.json").read_text()
    )["path"] == str(restored / "state/bootstrap/terraform.tfstate")


def test_bootstrap_refuses_state_without_identity_and_legacy_state(setup_runner):
    base, account, _ = setup_runner
    tf.execute("bootstrap", "init", account, base)
    legacy = base / ".terraform/bootstrap/bootstrap.tfstate"
    legacy.write_text("legacy")
    with pytest.raises(ValueError, match="caminho antigo"):
        tf.execute("bootstrap", "init", account, base)
    legacy.unlink()
    (base / "state/bootstrap/terraform.tfstate").write_text("state")
    (base / "state/bootstrap/identity.json").unlink()
    with pytest.raises(ValueError, match="já possui state"):
        tf.execute("bootstrap", "init", account, base)


@pytest.fixture
def remote_setup(setup_runner, monkeypatch):
    base, account_path, _ = setup_runner
    account = json.loads(account_path.read_text())
    objects = {}

    class S3:
        location = tf.REGION
        missing = False

        def get_bucket_location(self, **kwargs):
            assert kwargs["ExpectedBucketOwner"] == account["expected_account_id"]
            if self.missing:
                raise ClientError({"Error": {"Code": "NoSuchBucket"}}, "Location")
            return {"LocationConstraint": self.location}

        def get_object(self, **kwargs):
            assert kwargs["ExpectedBucketOwner"] == account["expected_account_id"]
            if kwargs["Key"] not in objects:
                raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
            return {"Body": io.BytesIO(json.dumps(objects[kwargs["Key"]]).encode())}

    class Session:
        def client(self, service):
            assert service == "s3"
            return s3

    s3 = S3()
    monkeypatch.setattr(tf, "aws_session", lambda _: Session())
    return base, account, objects, s3


def test_remote_checks_refuse_legacy_states_wrong_region_and_missing_bucket(
    remote_setup,
):
    base, account, objects, s3 = remote_setup
    assert INSPECT_AWS(account, base)
    objects["vintex/shared/terraform.tfstate"] = {}
    with pytest.raises(ValueError, match="shared legado"):
        INSPECT_AWS(account, base)
    objects.clear()
    objects["vintex/staging/terraform.tfstate"] = {"outputs": {}}
    with pytest.raises(ValueError, match="staging legado"):
        INSPECT_AWS(account, base)
    objects.clear()
    s3.location = "us-east-1"
    with pytest.raises(ValueError, match="us-east-2"):
        INSPECT_AWS(account, base)
    s3.missing = True
    assert not INSPECT_AWS(account, base, allow_missing=True)
    with pytest.raises(ValueError, match="infra-deploy staging"):
        INSPECT_AWS(account, base)


def test_current_remote_state_and_partial_apply_claim_are_accepted(remote_setup):
    base, account, objects, _ = remote_setup
    objects["vintex/staging/terraform.tfstate"] = {
        "outputs": {"infrastructure_layout": {"value": tf.LAYOUT}}
    }
    assert INSPECT_AWS(account, base)
    objects["vintex/staging/terraform.tfstate"] = {"outputs": {}}
    (base / "state").mkdir()
    tf.write_private(
        base / "state/staging-layout.json",
        {
            "account": account["expected_account_id"],
            "bucket": account["state_bucket"],
            "layout": tf.LAYOUT,
        },
    )
    assert INSPECT_AWS(account, base)
    account["expected_account_id"] = "999999999999"
    with pytest.raises(ValueError, match="staging legado"):
        INSPECT_AWS(account, base)


@pytest.mark.parametrize("failed_stage", ["bootstrap", "staging", None])
def test_deploy_orders_stages_stops_on_failure_and_can_be_restarted(
    setup_runner, monkeypatch, failed_stage
):
    base, account, _ = setup_runner
    monkeypatch.setattr(tf, "inspect_aws", lambda *args, **kwargs: False)
    calls = []

    def execute(environment, action, *args):
        calls.append((environment, action))
        if environment == failed_stage and action == "apply":
            raise subprocess.CalledProcessError(31, ["terraform", "apply"])

    monkeypatch.setattr(tf, "execute", execute)
    if failed_stage:
        with pytest.raises(subprocess.CalledProcessError):
            tf.deploy(account, base)
        assert calls[-1] == (failed_stage, "apply")
        assert ("staging", "init") not in calls if failed_stage == "bootstrap" else True
        calls.clear()
        failed_stage = None
    tf.deploy(account, base)
    assert calls == [
        (environment, action)
        for environment in ("bootstrap", "staging")
        for action in ("init", "plan", "show", "apply")
    ] + [("staging", "output")]


def test_deploy_never_adopts_an_existing_bucket(setup_runner):
    base, account, calls = setup_runner
    with pytest.raises(ValueError, match="sem state local"):
        tf.deploy(account, base)
    assert len(calls) == 4  # backend-free init/validate of both roots only
    assert not any("plan" in command or "apply" in command for command, _ in calls)


def test_first_deploy_and_second_run_use_the_real_orchestration_with_fakes(
    setup_runner, remote_setup, monkeypatch
):
    base, account_path, calls = setup_runner
    _, account, objects, s3 = remote_setup
    s3.missing = True
    monkeypatch.setattr(tf, "inspect_aws", INSPECT_AWS)
    monkeypatch.setattr(
        "builtins.input",
        lambda prompt: ("bootstrap" if "bootstrap" in prompt else "staging"),
    )
    original = tf.subprocess.run

    def run(command, *, env, check):
        original(command, env=env, check=check)
        if "apply" in command:
            if f"-chdir={base / 'bootstrap'}" in command:
                s3.missing = False
                tf.write_private(
                    base / "state/bootstrap/terraform.tfstate",
                    {
                        "resources": [
                            {
                                "type": "aws_s3_bucket",
                                "name": "state",
                                "instances": [
                                    {"attributes": {"id": account["state_bucket"]}}
                                ],
                            }
                        ]
                    },
                )
            else:
                objects["vintex/staging/terraform.tfstate"] = {
                    "outputs": {"infrastructure_layout": {"value": tf.LAYOUT}}
                }

    monkeypatch.setattr(tf.subprocess, "run", run)
    tf.deploy(account_path, base)
    assert sum("apply" in command for command, _ in calls) == 2
    assert (base / "state/staging-layout.json").exists()
    assert not (base / ".terraform/staging/plan.json").exists()
    state = (base / "state/bootstrap/terraform.tfstate").read_bytes()
    calls.clear()
    shutil.rmtree(base / ".terraform")
    tf.deploy(account_path, base)
    assert sum("apply" in command for command, _ in calls) == 2
    assert (base / "state/bootstrap/terraform.tfstate").read_bytes() == state


def test_staging_partial_apply_writes_durable_claim_and_requires_new_plan(
    setup_runner, monkeypatch
):
    base, account, _ = setup_runner
    tf.execute("staging", "init", account, base)
    tf.execute("staging", "plan", account, base)
    monkeypatch.setattr("builtins.input", lambda _: "staging")

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(42, args[0])

    monkeypatch.setattr(tf.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        tf.execute("staging", "apply", account, base)
    assert (
        json.loads((base / "state/staging-layout.json").read_text())["layout"]
        == tf.LAYOUT
    )
    with pytest.raises(ValueError, match="terraform-plan staging"):
        tf.execute("staging", "apply", account, base)


def test_aws_identity_is_checked_before_accessing_any_bucket(setup_runner, monkeypatch):
    import boto3

    _, path, _ = setup_runner
    account = json.loads(path.read_text())

    class Session:
        def client(self, service):
            assert service == "sts"
            return self

        def get_caller_identity(self):
            return {"Account": "999999999999"}

    monkeypatch.setattr(boto3, "Session", lambda **kwargs: Session())
    with pytest.raises(ValueError, match="Conta AWS diferente"):
        tf.aws_session(account)


def test_operation_lock_refuses_concurrent_run_and_releases_after_failure(tmp_path):
    with pytest.raises(RuntimeError):
        with tf.operation_lock(tmp_path):
            with pytest.raises(ValueError, match="Já existe"):
                with tf.operation_lock(tmp_path):
                    pytest.fail("must not acquire the same lock")
            raise RuntimeError("simulated failure")
    with tf.operation_lock(tmp_path):
        assert (tmp_path / "state/operation.lock").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "code,fragment",
    [
        ("ExpiredToken", "Renove a sessão"),
        ("AccessDenied", "Permissão negada"),
        ("OtherError", "Falha na consulta AWS"),
    ],
)
def test_failure_messages_do_not_print_sdk_payload(code, fragment, capsys):
    error = ClientError(
        {"Error": {"Code": code, "Message": "secret payload"}}, "GetObject"
    )
    tf.explain_failure(error, "deploy", "staging")
    output = capsys.readouterr().err
    assert fragment in output
    assert "make infra-deploy staging" in output
    assert "secret payload" not in output


def test_region_is_consistent_in_all_providers_and_backend():
    import re

    bootstrap = (tf.BASE / "bootstrap/main.tf").read_text()
    aws = (tf.BASE / "aws/main.tf").read_text()
    assert re.search(rf'region\s*=\s*"{tf.REGION}"', bootstrap)
    assert re.search(
        rf'output "aws_region"\s*\{{\s*value\s*=\s*"{tf.REGION}"', bootstrap
    )
    assert re.search(rf'aws_region\s*=\s*"{tf.REGION}"', aws)
    assert (
        tf.backend_config(
            "staging",
            {"state_bucket": "test-state", "expected_account_id": "123456789012"},
            tf.BASE,
        )["region"]
        == tf.REGION
    )
