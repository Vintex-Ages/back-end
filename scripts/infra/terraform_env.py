"""Comandos Terraform manuais, com backend e plano isolados por ambiente (#180)."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2] / "infra/terraform"
ENVIRONMENTS = ("bootstrap", "shared", "staging")
ACTIONS = ("init", "plan", "apply", "output", "show", "validate", "test")


def read_account(path: Path, environment: str) -> dict:
    config = json.loads(path.read_text())
    if not isinstance(config, dict) or set(config) != {
        "expected_account_id",
        "state_bucket",
        "budget_email_addresses",
    }:
        raise ValueError("Use somente os três campos de account.tfvars.json.example.")
    if not re.fullmatch(r"[0-9]{12}", str(config["expected_account_id"])):
        raise ValueError("expected_account_id deve ter 12 dígitos.")
    if not isinstance(config["state_bucket"], str) or not re.fullmatch(
        r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", config["state_bucket"]
    ):
        raise ValueError("state_bucket deve ser um nome de bucket S3.")
    emails = config["budget_email_addresses"]
    if not isinstance(emails, list) or any(
        not isinstance(email, str)
        or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
        for email in emails
    ):
        raise ValueError(
            "budget_email_addresses deve ser uma lista de e-mails válidos."
        )
    if environment == "shared" and not 1 <= len(set(emails)) <= 10:
        raise ValueError("Informe de 1 a 10 e-mails reais para o Budget de shared.")
    return config


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_private(path: Path, value: dict) -> None:
    # Open with private permissions even when a previous file already exists.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        os.chmod(path, 0o600)
        json.dump(value, handle, indent=2)
        handle.write("\n")


def backend_config(environment: str, account: dict, runtime: Path) -> dict:
    if environment == "bootstrap":
        return {"path": str(runtime / "bootstrap.tfstate")}
    return {
        "bucket": account["state_bucket"],
        "key": f"vintex/{environment}/terraform.tfstate",
        "region": "us-east-2",
        "encrypt": True,
        "use_lockfile": True,
        "allowed_account_ids": [account["expected_account_id"]],
    }


def source_digest(base: Path) -> str:
    # Include modules and EC2 bootstrap dependencies, but never state or caches.
    paths = [
        path
        for directory in (base, base.parent / "aws/staging")
        for path in directory.rglob("*")
        if path.is_file()
        and ".terraform" not in path.parts
        and (
            path.suffix in {".tf", ".tftpl", ".sh", ".service"}
            or path.name == ".terraform.lock.hcl"
        )
    ]
    return digest(
        b"".join(
            str(path.relative_to(base.parent)).encode() + b"\0" + path.read_bytes()
            for path in sorted(paths)
        )
    )


def execute(environment: str, action: str, account_path: Path, base: Path = BASE):
    if environment not in ENVIRONMENTS or action not in ACTIONS:
        raise ValueError("Ambiente ou comando Terraform não suportado.")
    if os.environ.get("TF_WORKSPACE", "default") != "default":
        raise ValueError("Use o workspace default; ENV seleciona states independentes.")
    # TF_CLI_ARGS could silently inject -var/-backend-config/-target/-destroy.
    if any(key.startswith("TF_CLI_ARGS") for key in os.environ):
        raise ValueError("Remova TF_CLI_ARGS* antes de usar os comandos protegidos.")
    account_path = account_path.resolve()
    account = read_account(account_path, environment)
    profile = base / "config" / f"{environment}.tfvars"
    if environment != "bootstrap" and not re.fullmatch(
        rf'\s*deployment\s*=\s*"{environment}"\s*', profile.read_text()
    ):
        raise ValueError("O arquivo de ambiente não corresponde ao ENV selecionado.")
    runtime = base / ".terraform" / environment
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(runtime, 0o700)
    root = base / ("bootstrap" if environment == "bootstrap" else "aws")
    env = dict(os.environ, TF_DATA_DIR=str(runtime / "data"), TF_WORKSPACE="default")
    command = ["terraform", f"-chdir={root}"]
    backend = backend_config(environment, account, runtime)
    identity = digest(
        json.dumps(
            [backend, account["expected_account_id"], account["state_bucket"]],
            sort_keys=True,
        ).encode()
    )
    marker = runtime / "initialized.json"
    plan = runtime / "deploy.tfplan"
    manifest = runtime / "plan.json"
    variables = [f"-var-file={account_path}"]
    if environment != "bootstrap":
        variables.append(f"-var-file={profile}")

    def run(arguments):
        subprocess.run(command + arguments, env=env, check=True)

    def signature():
        return {
            "backend": identity,
            "account": digest(account_path.read_bytes()),
            "sources": source_digest(base),
            "profile": digest(profile.read_bytes()) if profile.exists() else None,
        }

    if action == "init":
        if (
            environment == "bootstrap"
            and (runtime / "bootstrap.tfstate").exists()
            and (
                not marker.exists()
                or json.loads(marker.read_text()) != {"backend": identity}
            )
        ):
            raise ValueError(
                "Bootstrap já possui state; não troque a conta/bucket sem migrá-lo."
            )
        config_file = runtime / "backend.tfbackend.json"
        write_private(config_file, backend)
        # A failed re-init must not leave a usable marker for the previous backend.
        if environment != "bootstrap":
            marker.unlink(missing_ok=True)
        manifest.unlink(missing_ok=True)
        run(
            [
                "init",
                "-input=false",
                "-lockfile=readonly",
                "-reconfigure",
                f"-backend-config={config_file}",
            ]
        )
        write_private(marker, {"backend": identity})
        return

    if not marker.exists() or json.loads(marker.read_text()) != {"backend": identity}:
        raise ValueError(f"Execute make terraform-init ENV={environment} nesta conta.")
    if action == "plan":
        manifest.unlink(missing_ok=True)
        before = signature()
        run(["plan", "-input=false", *variables, f"-out={plan}"])
        os.chmod(plan, 0o600)
        if before != signature():
            raise ValueError("Configuração mudou durante o plan; gere um novo plano.")
        write_private(manifest, {**before, "plan": digest(plan.read_bytes())})
    elif action in {"apply", "show"}:
        if not manifest.exists() or not plan.exists():
            raise ValueError(f"Execute make terraform-plan ENV={environment} primeiro.")
        expected = {**signature(), "plan": digest(plan.read_bytes())}
        if json.loads(manifest.read_text()) != expected:
            raise ValueError(
                "Plano obsoleto ou de outra configuração; gere um novo plano."
            )
        if action == "show":
            run(["show", str(plan)])
            return
        confirmation = input(f"Digite {environment} para aplicar o plano revisado: ")
        if confirmation != environment:
            raise ValueError("Apply cancelado.")
        if expected != {**signature(), "plan": digest(plan.read_bytes())}:
            raise ValueError(
                "Configuração mudou durante a confirmação; gere novo plano."
            )
        # Invalidate before apply: a partial failure must also require a new plan.
        manifest.unlink()
        run(["apply", "-input=false", str(plan)])
        plan.unlink()
    else:
        run([action])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=ACTIONS)
    parser.add_argument("--env", required=True, choices=ENVIRONMENTS)
    parser.add_argument("--account", type=Path, default=BASE / "account.tfvars.json")
    args = parser.parse_args()
    # Terraform state/plans and downloaded backend metadata stay private.
    os.umask(0o077)
    try:
        execute(args.env, args.action, args.account)
    except (ValueError, OSError, EOFError) as error:
        print(f"[terraform] {error}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        return error.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
