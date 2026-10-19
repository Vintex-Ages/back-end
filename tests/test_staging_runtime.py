"""Staging deployment behavior without credentials or changes to the host."""

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.infra import deploy_staging as deploy

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "infra/aws/staging"


@pytest.fixture
def config():
    return {
        "account_id": "123456789012",
        "sha": "a" * 40,
        "queue_url": "https://sqs.us-east-2.amazonaws.com/123456789012/vintex-ai-staging",
        "media_bucket": "vintex-media-staging-test",
        "public_base_url": "http://localhost:8080",
    }


@pytest.fixture
def parameters():
    return {
        "db_password": "password$with:'special",
        "jwt_secret": "test$secret'" * 4,
        "llm_encryption_key": "a" * 64,
        "llm_admin_email": "admin@example.test",
        "llm_admin_password": "not-a-real-password",
    }


def test_render_secrets_encodes_database_password_and_limits_exposure(
    tmp_path, config, parameters
):
    deploy.render_secrets(parameters, tmp_path, config)
    assert (
        "password%24with%3A%27special@db:5432/vintex"
        in (tmp_path / "api.env").read_text()
    )
    assert "APP_ENV=production" in (tmp_path / "api.env").read_text()
    assert "APP_DEBUG=false" in (tmp_path / "api.env").read_text()
    assert "FREELLMAPI_API_KEY=\n" in (tmp_path / "worker.env").read_text()
    assert "ENCRYPTION_KEY" not in (tmp_path / "api.env").read_text()
    assert "JWT_SECRET" not in (tmp_path / "llm.env").read_text()
    assert "AWS_ACCESS_KEY_ID" not in (tmp_path / "worker.env").read_text()
    assert (
        "POSTGRES_PASSWORD=password$with:'special" in (tmp_path / "db.env").read_text()
    )
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in tmp_path.iterdir())


@pytest.mark.parametrize(
    "change",
    [
        {"jwt_secret": "short"},
        {"db_password": "short"},
        {"llm_encryption_key": "invalid"},
        {"llm_admin_email": ""},
        {"llm_api_key": "bad\ninjected=value"},
    ],
)
def test_invalid_parameters_do_not_write_files(tmp_path, config, parameters, change):
    with pytest.raises(ValueError):
        deploy.render_secrets({**parameters, **change}, tmp_path, config)
    assert not list(tmp_path.iterdir())


def test_private_write_refuses_symlink(tmp_path):
    protected = tmp_path / "protected"
    protected.write_text("original")
    link = tmp_path / "link"
    link.symlink_to(protected)
    with pytest.raises(FileExistsError):
        deploy.private_write(link, "changed")
    assert protected.read_text() == "original"


def test_parameters_paginate_and_decrypt_only_staging():
    client = Mock()
    client.get_paginator.return_value.paginate.return_value = [
        {"Parameters": [{"Name": "/vintex/staging/jwt_secret", "Value": "fake"}]},
        {"Parameters": [{"Name": "/vintex/staging/llm_api_key", "Value": "fake-key"}]},
    ]
    assert deploy.read_parameters(client) == {
        "jwt_secret": "fake",
        "llm_api_key": "fake-key",
    }
    client.get_paginator.return_value.paginate.assert_called_once_with(
        Path="/vintex/staging/", Recursive=False, WithDecryption=True
    )


@pytest.mark.parametrize(
    "change",
    [
        {"account_id": "bad"},
        {"sha": "latest"},
        {"media_bucket": "invalid/bucket"},
        {"queue_url": "http://localstack:4566/queue"},
        {
            "queue_url": "https://sqs.us-east-2.amazonaws.com/999999999999/vintex-ai-prod"
        },
        {"public_base_url": "https://public.example.test"},
    ],
)
def test_config_rejects_wrong_account_emulators_and_mutable_release(config, change):
    with pytest.raises(ValueError):
        deploy.validate_config({**config, **change})


def test_valid_staging_config(config):
    deploy.validate_config(config)


def release(tmp_path, sha):
    secret_dir = tmp_path / sha
    secret_dir.mkdir()
    (secret_dir / "db.env").write_text("POSTGRES_PASSWORD=fake")
    (secret_dir / "llm.env").write_text("ENCRYPTION_KEY=fake-stable-key")
    return {
        "sha": sha,
        "backend_image": f"registry/vintex-backend:{sha}",
        "llm_image": "registry/freellmapi@sha256:fake",
        "runtime_dir": str(RUNTIME),
        "frontend_dir": str(tmp_path),
        "secrets_dir": str(secret_dir),
    }


@pytest.mark.parametrize("failure", ["migration", "up", "health", None])
def test_deploy_sequence_and_rollback_preserve_schema_and_state(
    tmp_path, monkeypatch, failure
):
    previous = release(tmp_path, "b" * 40)
    target = release(tmp_path, "a" * 40)
    (tmp_path / "current.json").write_text(json.dumps(previous))
    calls = []

    def compose(item, *args):
        calls.append((item["sha"], args))
        if item == target and (
            (failure == "migration" and args[:2] == ("exec", "-T"))
            or (
                failure == "up"
                and args == ("up", "-d", "--wait", "--wait-timeout", "120")
            )
        ):
            raise RuntimeError("synthetic failure")
        return ""

    instance = deploy.Deployment(tmp_path)
    monkeypatch.setattr(instance, "compose", compose)
    health = iter([False, True] if failure == "health" else [True])
    monkeypatch.setattr(instance, "healthy", lambda: next(health))
    monkeypatch.setattr(instance, "cleanup_images", Mock())
    monkeypatch.setattr(deploy, "run", lambda *a, **k: "arm64\n")
    if failure:
        with pytest.raises(RuntimeError):
            instance.deploy(target)
        assert json.loads((tmp_path / "current.json").read_text()) == previous
        assert calls[-1][0] == previous["sha"]
        instance.cleanup_images.assert_not_called()
    else:
        instance.deploy(target)
        assert json.loads((tmp_path / "current.json").read_text()) == target
        assert json.loads((tmp_path / "previous.json").read_text()) == previous
    migrate = next(i for i, (_, args) in enumerate(calls) if "alembic" in args)
    assert calls[migrate - 1][1] == ("up", "-d", "--no-deps", "api")
    assert not any("downgrade" in args or "down" in args for _, args in calls)


def test_first_deploy_failure_stops_application_but_preserves_database(
    tmp_path, monkeypatch
):
    target = release(tmp_path, "a" * 40)
    instance = deploy.Deployment(tmp_path)
    compose = Mock(return_value="")
    monkeypatch.setattr(instance, "compose", compose)
    monkeypatch.setattr(instance, "healthy", lambda: False)
    monkeypatch.setattr(deploy, "run", lambda *a, **k: "arm64")
    with pytest.raises(RuntimeError):
        instance.deploy(target)
    assert compose.call_args.args[1:] == (
        "stop",
        "proxy",
        "api",
        "worker",
        "freellmapi",
    )
    assert not (tmp_path / "current.json").exists()


def test_rotation_fails_before_changing_running_services(tmp_path, monkeypatch):
    previous = release(tmp_path, "b" * 40)
    target = release(tmp_path, "a" * 40)
    (Path(target["secrets_dir"]) / "db.env").write_text("POSTGRES_PASSWORD=changed")
    (tmp_path / "current.json").write_text(json.dumps(previous))
    instance = deploy.Deployment(tmp_path)
    mock = Mock()
    monkeypatch.setattr(instance, "compose", mock)
    with pytest.raises(ValueError):
        instance.deploy(target)
    mock.assert_not_called()


def test_cleanup_only_removes_old_backend_sha_without_force(tmp_path, monkeypatch):
    target = release(tmp_path, "a" * 40)
    previous = release(tmp_path, "b" * 40)
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[:3] == ["docker", "image", "ls"]:
            return "\n".join(
                json.dumps({"Repository": "registry/vintex-backend", "Tag": tag})
                for tag in ("a" * 40, "b" * 40, "c" * 40, "manual")
            )
        return ""

    monkeypatch.setattr(deploy, "run", run)
    deploy.Deployment.cleanup_images(target, previous)
    assert calls[1:] == [
        ["docker", "image", "rm", "registry/vintex-backend:" + "c" * 40]
    ]


def test_command_errors_do_not_leak_output(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess([], 2, "secret", "secret"),
    )
    with pytest.raises(RuntimeError, match="exit 2") as failure:
        deploy.run(["docker", "compose"])
    assert "secret" not in str(failure.value)


def test_guard_bootstrap_is_persistent_and_before_docker():
    guard = (RUNTIME / "imds-guard.sh").read_text()
    assert "169.254.169.254" in guard and "fd00:ec2::254" in guard
    assert "-s 172.30.73.3 -j RETURN" in guard
    assert "-s 172.30.73.4 -j RETURN" in guard
    assert "-A VINTEX_IMDS -j DROP" in guard
    assert (
        "Before=docker.service" in (RUNTIME / "vintex-imds-guard.service").read_text()
    )
    assert (
        "Requires=vintex-imds-guard.service"
        in (RUNTIME / "install-guard.sh").read_text()
    )
    assert "NET_RAW" in (RUNTIME / "compose.yml").read_text()


def test_llm_encryption_key_rotation_is_refused(tmp_path, monkeypatch):
    previous = release(tmp_path, "b" * 40)
    target = release(tmp_path, "a" * 40)
    (Path(target["secrets_dir"]) / "llm.env").write_text("ENCRYPTION_KEY=changed")
    (tmp_path / "current.json").write_text(json.dumps(previous))
    instance = deploy.Deployment(tmp_path)
    compose = Mock()
    monkeypatch.setattr(instance, "compose", compose)
    with pytest.raises(ValueError):
        instance.deploy(target)
    compose.assert_not_called()


def test_ecr_password_is_only_sent_on_stdin(monkeypatch):
    import base64

    client = Mock()
    client.get_authorization_token.return_value = {
        "authorizationData": [
            {"authorizationToken": base64.b64encode(b"AWS:fake-password").decode()}
        ]
    }
    command = Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))
    monkeypatch.setattr(subprocess, "run", command)
    deploy.login_ecr(client, "registry.example.test")
    assert "fake-password" not in str(command.call_args.args)
    assert command.call_args.kwargs["input"] == "fake-password"


def test_wrong_image_architecture_does_not_stop_running_application(
    tmp_path, monkeypatch
):
    instance = deploy.Deployment(tmp_path)
    target = release(tmp_path, "a" * 40)
    compose = Mock(return_value="")
    monkeypatch.setattr(instance, "compose", compose)
    monkeypatch.setattr(deploy, "run", lambda *a, **k: "amd64")
    with pytest.raises(ValueError):
        instance.deploy(target)
    assert [call.args[1:] for call in compose.call_args_list] == [
        ("config", "--quiet"),
        ("pull",),
    ]


@pytest.mark.parametrize(
    "method,account",
    [
        ("iam-role", "123456789012"),
        ("env", "123456789012"),
        ("iam-role", "999999999999"),
    ],
)
def test_host_bootstrap_checks_identity_and_uses_instance_role(
    tmp_path, monkeypatch, config, parameters, method, account
):
    from types import SimpleNamespace

    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("synthetic frontend")
    config.update({"runtime_dir": str(RUNTIME), "frontend_dir": str(frontend)})
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    monkeypatch.setattr(
        "sys.argv",
        ["deploy", "--config", str(config_path), "--state", str(tmp_path / "state")],
    )
    monkeypatch.setattr(deploy.os, "geteuid", lambda: 0)
    monkeypatch.setattr(deploy.os, "uname", lambda: SimpleNamespace(machine="aarch64"))
    runner = Mock(return_value="")
    monkeypatch.setattr(deploy, "run", runner)
    session = Mock()
    session.get_credentials.return_value = SimpleNamespace(method=method)
    session.client.return_value.get_caller_identity.return_value = {"Account": account}
    monkeypatch.setattr(deploy.boto3, "Session", lambda **k: session)
    read = Mock(return_value=parameters)
    monkeypatch.setattr(deploy, "read_parameters", read)
    login = Mock()
    monkeypatch.setattr(deploy, "login_ecr", login)
    perform = Mock()
    monkeypatch.setattr(deploy.Deployment, "deploy", perform)
    if method != "iam-role" or account != config["account_id"]:
        with pytest.raises(ValueError):
            deploy.main()
        read.assert_not_called()
        perform.assert_not_called()
    else:
        deploy.main()
        login.assert_called_once()
        perform.assert_called_once()
        output = perform.call_args.args[0]
        assert output["backend_image"].endswith(config["sha"])
        assert output["llm_image"].endswith(deploy.LLM_DIGEST)
        assert (
            "FREELLMAPI_API_KEY=\n"
            in (Path(output["secrets_dir"]) / "worker.env").read_text()
        )
    assert runner.call_args_list[0].args[0] == [
        "systemctl",
        "is-active",
        "--quiet",
        "vintex-imds-guard.service",
    ]
    assert runner.call_args_list[1].args[0] == ["/usr/local/sbin/vintex-imds-guard"]


def test_refreshing_secrets_for_same_sha_retains_previous_distinct_image(
    tmp_path, monkeypatch
):
    older = release(tmp_path, "b" * 40)
    current = release(tmp_path, "a" * 40)
    target = {**current, "frontend_dir": "updated-static-artifact"}
    (tmp_path / "current.json").write_text(json.dumps(current))
    (tmp_path / "previous.json").write_text(json.dumps(older))
    instance = deploy.Deployment(tmp_path)
    monkeypatch.setattr(instance, "compose", Mock(return_value=""))
    monkeypatch.setattr(instance, "healthy", lambda: True)
    cleanup = Mock()
    monkeypatch.setattr(instance, "cleanup_images", cleanup)
    monkeypatch.setattr(deploy, "run", lambda *a, **k: "arm64")
    instance.deploy(target)
    assert json.loads((tmp_path / "previous.json").read_text()) == older
    cleanup.assert_called_once_with(target, older)
