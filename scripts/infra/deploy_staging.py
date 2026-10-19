"""Manual EC2 staging deploy; run as root on the host, never in CI."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import urlopen

import boto3

REGION = "us-east-2"
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
LLM_DIGEST = "1942b1437628deb70699d7371dab3cb7e65c296c4e1db345218b4de2102149eb"


def run(args: list[str], *, env: dict[str, str] | None = None) -> str:
    """Capture command output: Docker/SDK errors can contain secret values."""
    result = subprocess.run(args, env=env, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed (exit {result.returncode})")
    return result.stdout


def private_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Exclusive creation avoids following a previously planted symlink.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as target:
        target.write(content)


def login_ecr(client: Any, registry: str) -> None:
    token = client.get_authorization_token()["authorizationData"][0][
        "authorizationToken"
    ]
    password = base64.b64decode(token).decode().split(":", 1)[1]
    result = subprocess.run(
        ["docker", "login", "--username", "AWS", "--password-stdin", registry],
        input=password,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("ECR login failed")


def read_parameters(ssm: Any) -> dict[str, str]:
    values: dict[str, str] = {}
    paginator = ssm.get_paginator("get_parameters_by_path")
    for page in paginator.paginate(
        Path="/vintex/staging/", Recursive=False, WithDecryption=True
    ):
        values.update(
            (parameter["Name"].rsplit("/", 1)[1], parameter["Value"])
            for parameter in page["Parameters"]
        )
    return values


def render_secrets(
    values: dict[str, str], directory: Path, config: dict[str, str]
) -> None:
    required = (
        "db_password",
        "jwt_secret",
        "llm_encryption_key",
        "llm_admin_email",
        "llm_admin_password",
    )
    if any(not values.get(key) for key in required):
        raise ValueError("Missing required staging parameters")
    if len(values["jwt_secret"]) < 32 or len(values["db_password"]) < 16:
        raise ValueError("JWT and database secrets are too short")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", values["llm_encryption_key"]):
        raise ValueError("Invalid FreeLLMAPI encryption key")
    database_url = (
        f"postgresql://postgres:{quote(values['db_password'], safe='')}@db:5432/vintex"
    )
    common = {
        "APP_ENV": "production",  # Activate the existing JWT guard in staging too.
        "APP_DEBUG": "false",
        "DATABASE_URL": database_url,
        "JWT_SECRET": values["jwt_secret"],
        "AWS_REGION": REGION,
        "AI_PROVIDER": "unavailable",
        "AI_ANALYSIS_QUEUE_URL": config["queue_url"],
        "MEDIA_BUCKET": config["media_bucket"],
        "PUBLIC_BASE_URL": config["public_base_url"],
        "MEDIA_INTERNAL_BASE_URL": "http://api:8000",
        "CORS_ORIGINS": config["public_base_url"],
    }
    files = {
        "api.env": common,
        "worker.env": {
            **common,
            "AI_WORKER_PROVIDER": "freellmapi",
            "FREELLMAPI_BASE_URL": "http://freellmapi:3001/v1",
            "FREELLMAPI_API_KEY": values.get("llm_api_key", ""),
            "FREELLMAPI_MODEL": "auto",
        },
        "db.env": {
            "POSTGRES_USER": "postgres",
            "POSTGRES_DB": "vintex",
            "POSTGRES_PASSWORD": values["db_password"],
        },
        "llm.env": {
            "NODE_ENV": "production",
            "PORT": "3001",
            "ENCRYPTION_KEY": values["llm_encryption_key"],
            "FREELLMAPI_UPDATE_CHECK": "off",
            "FREEAPI_CONFIG_JSON": json.dumps(
                {
                    "admin": {
                        "email": values["llm_admin_email"],
                        "password": values["llm_admin_password"],
                    }
                }
            ),
        },
    }
    # Compose env_file format: raw keeps dollar signs and quotes literal.
    if any(
        "\n" in value or "\r" in value or "\0" in value
        for fields in files.values()
        for value in fields.values()
    ):
        raise ValueError("Parameter values must be single-line")
    for name, fields in files.items():
        private_write(
            directory / name,
            "".join(f"{key}={value}\n" for key, value in fields.items()),
        )


def validate_config(config: dict[str, str]) -> None:
    account = config["account_id"]
    if not re.fullmatch(r"\d{12}", account):
        raise ValueError("Invalid AWS account ID")
    if not SHA_PATTERN.fullmatch(config["sha"]):
        raise ValueError("Backend release must be a full commit SHA")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", config["media_bucket"]):
        raise ValueError("Invalid media bucket")
    if not re.fullmatch(
        rf"https://sqs\.us-east-2\.amazonaws\.com/{account}/vintex-ai-staging",
        config["queue_url"],
    ):
        raise ValueError("Queue must belong to the staging account in Ohio")
    if not re.fullmatch(r"http://localhost:\d{2,5}", config["public_base_url"]):
        raise ValueError("Use the localhost URL of the SSM forward")


class Deployment:
    def __init__(self, state: Path) -> None:
        self.state = state

    @staticmethod
    def compose(release: dict[str, str], *args: str) -> str:
        environment = dict(os.environ)
        environment.update(
            {
                "RELEASE_SHA": release["sha"],
                "BACKEND_IMAGE": release["backend_image"],
                "FREELLMAPI_IMAGE": release["llm_image"],
                "FRONTEND_DIR": release["frontend_dir"],
                "SECRETS_DIR": release["secrets_dir"],
            }
        )
        # Never load a developer's .env or persistent AWS keys into Compose.
        return run(
            [
                "docker",
                "compose",
                "--env-file",
                "/dev/null",
                "-f",
                str(Path(release["runtime_dir"]) / "compose.yml"),
                *args,
            ],
            env=environment,
        )

    @staticmethod
    def healthy() -> bool:
        for _ in range(10):
            try:
                with urlopen("http://127.0.0.1/health", timeout=3) as response:
                    if response.status == 200:
                        return True
            except (OSError, ValueError):
                pass
            time.sleep(3)
        return False

    def deploy(self, release: dict[str, str]) -> None:
        current = self.state / "current.json"
        previous = json.loads(current.read_text()) if current.exists() else None
        if (
            previous
            and (Path(previous["secrets_dir"]) / "db.env").read_text()
            != (Path(release["secrets_dir"]) / "db.env").read_text()
        ):
            raise ValueError(
                "Database password rotation requires a separate manual procedure"
            )
        if previous:

            def encryption_key(item: dict[str, str]) -> str:
                return next(
                    line
                    for line in (Path(item["secrets_dir"]) / "llm.env")
                    .read_text()
                    .splitlines()
                    if line.startswith("ENCRYPTION_KEY=")
                )

            if encryption_key(previous) != encryption_key(release):
                raise ValueError(
                    "FreeLLMAPI encryption key must stay stable with its SQLite"
                )
        self.compose(release, "config", "--quiet")
        self.compose(release, "pull")
        for image in (release["backend_image"], release["llm_image"]):
            if (
                run(
                    [
                        "docker",
                        "image",
                        "inspect",
                        image,
                        "--format",
                        "{{.Architecture}}",
                    ]
                ).strip()
                != "arm64"
            ):
                raise ValueError("Images must target ARM64")
        changed = False
        try:
            self.compose(release, "up", "-d", "--wait", "--wait-timeout", "120", "db")
            # Run as the allowed API address: `compose run` has a dynamic address.
            # This temporary API is isolated from proxy traffic until migrations finish.
            changed = True
            self.compose(release, "stop", "proxy", "worker", "api")
            self.compose(release, "up", "-d", "--no-deps", "api")
            self.compose(release, "exec", "-T", "api", "alembic", "upgrade", "head")
            self.compose(release, "up", "-d", "--wait", "--wait-timeout", "120")
            if not self.healthy():
                raise RuntimeError("API health check failed")
        except Exception:
            if changed:
                if previous:
                    self.compose(
                        previous, "up", "-d", "--wait", "--wait-timeout", "120"
                    )
                    if not self.healthy():
                        raise RuntimeError(
                            "Deployment and rollback health checks failed"
                        ) from None
                else:
                    self.compose(
                        release, "stop", "proxy", "api", "worker", "freellmapi"
                    )
            raise
        next_state = self.state / f"next-{time.time_ns()}.json"
        private_write(next_state, json.dumps(release))
        previous_path = self.state / "previous.json"
        retained = previous
        if previous and previous["backend_image"] == release["backend_image"]:
            # Updating SSM credentials for the same SHA must preserve the previous image.
            retained = (
                json.loads(previous_path.read_text())
                if previous_path.exists()
                else None
            )
        if retained:
            previous_next = self.state / f"previous-{time.time_ns()}.json"
            private_write(previous_next, json.dumps(retained))
            previous_next.replace(previous_path)
        next_state.replace(current)
        try:
            self.cleanup_images(release, retained)
        except (RuntimeError, ValueError):
            print(
                "[staging] healthy release recorded; image cleanup needs manual retry"
            )

    @staticmethod
    def cleanup_images(
        release: dict[str, str], previous: dict[str, str] | None
    ) -> None:
        repository = release["backend_image"].rsplit(":", 1)[0]
        keep = {release["backend_image"]}
        if previous:
            keep.add(previous["backend_image"])
        images = run(["docker", "image", "ls", repository, "--format", "{{json .}}"])
        for line in images.splitlines():
            image = json.loads(line)
            name = f"{image['Repository']}:{image['Tag']}"
            if (
                image["Repository"] == repository
                and SHA_PATTERN.fullmatch(image["Tag"])
                and name not in keep
            ):
                try:
                    run(["docker", "image", "rm", name])  # No force, prune or volumes.
                except RuntimeError:
                    pass  # Preserve images still referenced by containers.


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--state", type=Path, default=Path("/var/lib/vintex-staging"))
    args = parser.parse_args()
    if os.geteuid() != 0 or os.uname().machine != "aarch64":
        raise ValueError("Deploy requires root on the ARM64 staging host")
    run(["systemctl", "is-active", "--quiet", "vintex-imds-guard.service"])
    run(["/usr/local/sbin/vintex-imds-guard"])
    config = json.loads(args.config.read_text())
    validate_config(config)
    session = boto3.Session(region_name=REGION)
    credentials = session.get_credentials()
    if credentials is None or credentials.method != "iam-role":
        raise ValueError("Use the staging EC2 instance role, not operator credentials")
    if session.client("sts").get_caller_identity()["Account"] != config["account_id"]:
        raise ValueError("AWS account mismatch")
    root = args.state
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    # Lock deploys and protect files containing secrets across every operation.
    import fcntl

    with (root / "deploy.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        directory = root / "releases" / f"{config['sha']}-{time.time_ns()}"
        directory.mkdir(parents=True, mode=0o700)
        render_secrets(read_parameters(session.client("ssm")), directory, config)
        registry = f"{config['account_id']}.dkr.ecr.{REGION}.amazonaws.com"
        login_ecr(session.client("ecr"), registry)
        release = {
            "sha": config["sha"],
            "backend_image": f"{registry}/vintex-backend:{config['sha']}",
            "llm_image": f"{registry}/freellmapi@sha256:{LLM_DIGEST}",
            "runtime_dir": str(Path(config["runtime_dir"]).resolve()),
            "frontend_dir": str(Path(config["frontend_dir"]).resolve()),
            "secrets_dir": str(directory),
        }
        if not (Path(release["frontend_dir"]) / "index.html").is_file():
            raise ValueError("Missing frontend index.html")
        Deployment(root).deploy(release)
    print("[staging] deploy healthy; release recorded")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Do not expose subprocess output, SDK payloads, secrets or configuration.
        print(
            f"[staging] deploy failed ({type(error).__name__}); inspect protected host state"
        )
        raise SystemExit(1) from None
