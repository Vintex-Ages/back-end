"""Comandos Terraform manuais, com backend e plano isolados por ambiente (#180)."""

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2] / "infra/terraform"
REGION = "us-east-2"
LAYOUT = "staging-complete-v1"
ENVIRONMENTS = ("bootstrap", "staging")
ACTIONS = ("init", "plan", "apply", "output", "show", "validate", "test", "deploy")


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
    if environment == "staging" and not 1 <= len(set(emails)) <= 10:
        raise ValueError("Informe de 1 a 10 e-mails reais para o Budget da staging.")
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


def backend_config(environment: str, account: dict, base: Path) -> dict:
    if environment == "bootstrap":
        return {"path": str(base / "state/bootstrap/terraform.tfstate")}
    return {
        "bucket": account["state_bucket"],
        "key": f"vintex/{environment}/terraform.tfstate",
        "region": REGION,
        "encrypt": True,
        "use_lockfile": True,
        "allowed_account_ids": [account["expected_account_id"]],
    }


def check_overrides() -> None:
    if os.environ.get("TF_WORKSPACE", "default") != "default":
        raise ValueError("Use o workspace default; o ambiente seleciona o state.")
    if any(key.startswith("TF_CLI_ARGS") for key in os.environ):
        raise ValueError("Remova TF_CLI_ARGS* antes de usar os comandos protegidos.")


def check_configuration(environment: str, action: str, base: Path) -> None:
    """Backend-free QA never reads account configuration or operational metadata."""
    check_overrides()
    if environment not in (*ENVIRONMENTS, "local"):
        raise ValueError("Use local, bootstrap ou staging.")
    root = (
        base
        / {
            "local": "envs/local",
            "bootstrap": "bootstrap",
            "staging": "aws",
        }[environment]
    )
    runtime = base / ".terraform/qa" / environment
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    env = dict(os.environ, TF_DATA_DIR=str(runtime / "data"), TF_WORKSPACE="default")
    command = ["terraform", f"-chdir={root}"]
    subprocess.run(
        command + ["init", "-backend=false", "-input=false", "-lockfile=readonly"],
        env=env,
        check=True,
    )
    subprocess.run(command + [action], env=env, check=True)


def aws_session(account: dict):
    # Imported only for operational commands. QA has no SDK/credential dependency.
    import boto3

    session = boto3.Session(region_name=REGION)
    if (
        session.client("sts").get_caller_identity()["Account"]
        != account["expected_account_id"]
    ):
        raise ValueError(
            "Conta AWS diferente da configuração. Confira AWS_PROFILE e STS."
        )
    return session


def remote_state(s3, account: dict, key: str):
    from botocore.exceptions import ClientError

    try:
        response = s3.get_object(
            Bucket=account["state_bucket"],
            Key=key,
            ExpectedBucketOwner=account["expected_account_id"],
        )
    except ClientError as error:
        if error.response["Error"]["Code"] in {"NoSuchKey", "404"}:
            return None
        raise
    with response["Body"] as body:
        return json.loads(body.read())


def inspect_aws(account: dict, base: Path, *, allow_missing: bool = False) -> bool:
    """Read-only prerequisite/legacy checks; never adopt resources or modify state."""
    from botocore.exceptions import ClientError

    session = aws_session(account)
    s3 = session.client("s3")
    try:
        location = s3.get_bucket_location(
            Bucket=account["state_bucket"],
            ExpectedBucketOwner=account["expected_account_id"],
        )["LocationConstraint"]
    except ClientError as error:
        if error.response["Error"]["Code"] not in {"NoSuchBucket", "404"}:
            raise
        if allow_missing:
            return False
        raise ValueError(
            "Bucket ainda não existe. Execute make infra-deploy staging "
            "para criá-lo com Terraform."
        ) from None
    if location != REGION:
        raise ValueError(
            "O bucket de state deve pertencer à conta esperada em us-east-2."
        )
    if remote_state(s3, account, "vintex/shared/terraform.tfstate") is not None:
        raise ValueError(
            "State shared legado encontrado. É necessária migração revisada; "
            "não serão combinados states automaticamente."
        )
    state = remote_state(s3, account, "vintex/staging/terraform.tfstate")
    identity = {
        "account": account["expected_account_id"],
        "bucket": account["state_bucket"],
        "layout": LAYOUT,
    }
    claim = base / "state/staging-layout.json"
    # Terraform may not persist outputs on a partial first apply. A durable claim
    # is written only after checking the old state and before the first apply.
    if state is not None and (
        state.get("outputs", {}).get("infrastructure_layout", {}).get("value") != LAYOUT
        and (not claim.exists() or json.loads(claim.read_text()) != identity)
    ):
        raise ValueError(
            "State staging legado encontrado. Interrompido para migração revisada."
        )
    return True


@contextlib.contextmanager
def operation_lock(base: Path):
    directory = base / "state"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    descriptor = os.open(directory / "operation.lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(
                "Já existe uma operação Terraform neste checkout. Aguarde e repita."
            ) from None
        yield


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
    paths.extend(
        path
        for path in (
            base.parents[1] / "scripts/infra/terraform_env.py",
            base.parents[1] / "Makefile",
        )
        if path.is_file()
    )
    return digest(
        b"".join(
            os.path.relpath(path, base).encode() + b"\0" + path.read_bytes()
            for path in sorted(paths)
        )
    )


def execute(environment: str, action: str, account_path: Path, base: Path = BASE):
    if action in {"validate", "test"}:
        check_configuration(environment, action, base)
        return
    if action == "deploy":
        if environment != "staging":
            raise ValueError("Use make infra-deploy staging para provisionar AWS.")
        deploy(account_path, base)
        return
    if environment not in ENVIRONMENTS or action not in ACTIONS:
        raise ValueError(
            "Ambiente ou comando Terraform não suportado. Para AWS use staging "
            "(exemplo: make terraform-plan staging)."
        )
    check_overrides()
    (base / "state").mkdir(parents=True, exist_ok=True, mode=0o700)
    account_path = account_path.resolve()
    account = read_account(account_path, environment)
    profile = base / "config" / f"{environment}.tfvars"
    if environment != "bootstrap" and not re.fullmatch(
        rf'\s*deployment\s*=\s*"{environment}"\s*', profile.read_text()
    ):
        raise ValueError(
            "O arquivo de ambiente não corresponde ao ambiente selecionado."
        )
    runtime = base / ".terraform" / environment
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(runtime, 0o700)
    root = base / ("bootstrap" if environment == "bootstrap" else "aws")
    env = dict(os.environ, TF_DATA_DIR=str(runtime / "data"), TF_WORKSPACE="default")
    command = ["terraform", f"-chdir={root}"]
    backend = backend_config(environment, account, base)
    identity = digest(
        json.dumps(
            [backend, account["expected_account_id"], account["state_bucket"]],
            sort_keys=True,
        ).encode()
    )
    marker = runtime / "initialized.json"
    bootstrap_identity = {
        "account": account["expected_account_id"],
        "bucket": account["state_bucket"],
        "region": REGION,
    }
    if environment == "bootstrap":
        directory = base / "state/bootstrap"
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(directory, 0o700)
        durable_identity = directory / "identity.json"
        if (runtime / "bootstrap.tfstate").exists():
            raise ValueError(
                "State bootstrap no caminho antigo. Preserve-o e faça migração "
                "manual revisada para state/bootstrap antes de continuar."
            )
        if (directory / "terraform.tfstate").exists() and (
            not durable_identity.exists()
            or json.loads(durable_identity.read_text()) != bootstrap_identity
        ):
            raise ValueError(
                "Bootstrap já possui state; não troque a conta/bucket sem migrá-lo."
            )
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
        if environment == "staging":
            inspect_aws(account, base)
        config_file = runtime / "backend.tfbackend.json"
        write_private(config_file, backend)
        # Cache metadata is disposable; the bootstrap ownership record is not.
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
        if environment == "bootstrap":
            write_private(durable_identity, bootstrap_identity)
        return

    if not marker.exists() or json.loads(marker.read_text()) != {"backend": identity}:
        raise ValueError(f"Execute make terraform-init {environment} nesta conta.")
    if environment == "staging" and action in {"plan", "apply"}:
        inspect_aws(account, base)
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
            raise ValueError(f"Execute make terraform-plan {environment} primeiro.")
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
        if environment == "staging":
            write_private(
                base / "state/staging-layout.json",
                {
                    "account": account["expected_account_id"],
                    "bucket": account["state_bucket"],
                    "layout": LAYOUT,
                },
            )
        run(["apply", "-input=false", str(plan)])
        plan.unlink()
    else:
        run([action])


def deploy(account_path: Path, base: Path = BASE) -> None:
    """Human-operated bootstrap and complete staging, stopping at every failure."""
    check_overrides()
    account = read_account(account_path.resolve(), "staging")
    legacy = base / ".terraform/bootstrap/bootstrap.tfstate"
    if legacy.exists():
        raise ValueError("State bootstrap antigo encontrado; faça migração revisada.")
    if not re.fullmatch(
        r'\s*deployment\s*=\s*"staging"\s*',
        (base / "config/staging.tfvars").read_text(),
    ):
        raise ValueError("O arquivo de ambiente não corresponde à staging.")
    print("[infra] Validando bootstrap e staging sem acessar a conta AWS.", flush=True)
    for environment in ENVIRONMENTS:
        check_configuration(environment, "validate", base)
    exists = inspect_aws(account, base, allow_missing=True)
    if exists:
        path = base / "state/bootstrap/terraform.tfstate"
        if not path.exists():
            raise ValueError(
                "Bucket existente sem state local do bootstrap. Restaure o backup "
                "de state/bootstrap; não será feita adoção automática."
            )
        state = json.loads(path.read_text())
        if not any(
            resource.get("type") == "aws_s3_bucket"
            and resource.get("name") == "state"
            and any(
                item.get("attributes", {}).get("id") == account["state_bucket"]
                for item in resource.get("instances", [])
            )
            for resource in state.get("resources", [])
        ):
            raise ValueError("State do bootstrap não administra o bucket configurado.")
    print(
        f"[infra] staging | conta {account['expected_account_id']} | {REGION}",
        flush=True,
    )
    for environment in ENVIRONMENTS:
        print(
            f"[infra] Etapa: {environment}. Revise o plano antes de confirmar.",
            flush=True,
        )
        execute(environment, "init", account_path, base)
        execute(environment, "plan", account_path, base)
        execute(environment, "show", account_path, base)
        execute(environment, "apply", account_path, base)
    execute("staging", "output", account_path, base)
    print(
        "[infra] Infraestrutura aplicada. Aguarde o bootstrap da EC2/SSM e siga "
        "documentation/docs/infraestrutura/aws-staging-runtime.md para publicar o app."
    )


def explain_failure(error: Exception, action: str, environment: str) -> None:
    """SDK payloads may contain private data; print only recognized error codes."""
    prefix = f"[terraform:{environment}:{action}]"
    if type(error).__module__.startswith("botocore") and hasattr(error, "response"):
        code = error.response["Error"]["Code"]
        if code in {"ExpiredToken", "ExpiredTokenException", "InvalidClientTokenId"}:
            detail = "Sessão AWS inválida/expirada. Renove a sessão do perfil e repita."
        elif code in {"AccessDenied", "AccessDeniedException", "403"}:
            detail = (
                "Permissão negada. Confira as concessões da identidade institucional "
                "para STS/S3 e os recursos declarados antes de repetir."
            )
        else:
            detail = (
                "Falha na consulta AWS. Confira sessão, conectividade e permissões."
            )
    elif type(error).__module__.startswith("botocore"):
        detail = "Confira AWS_PROFILE, credenciais válidas e conectividade com a AWS."
    elif isinstance(error, FileNotFoundError):
        detail = (
            "Arquivo ou ferramenta ausente. Confira a instalação do Terraform e "
            "prepare infra/terraform/account.tfvars.json conforme o README."
        )
    elif isinstance(error, subprocess.CalledProcessError):
        detail = f"Terraform retornou código {error.returncode}; confira o erro acima."
    elif isinstance(error, KeyboardInterrupt):
        detail = "Operação interrompida pelo responsável."
    elif isinstance(error, EOFError):
        detail = (
            "Confirmação ausente. Execute o apply manualmente em terminal interativo."
        )
    else:
        detail = str(error)
    print(f"{prefix} {detail}", file=sys.stderr)
    if action == "deploy":
        print(
            "[infra] Etapa interrompida; states existentes foram preservados. "
            "Corrija a causa e execute make infra-deploy staging para revisar "
            "novos planos. Nenhum apply será repetido automaticamente.",
            file=sys.stderr,
        )
    elif action == "apply":
        print(
            f"[terraform] Se houve apply parcial, execute make terraform-plan "
            f"{environment} antes de tentar aplicar novamente.",
            file=sys.stderr,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=ACTIONS)
    parser.add_argument("--env", required=True, choices=(*ENVIRONMENTS, "local"))
    parser.add_argument("--account", type=Path, default=BASE / "account.tfvars.json")
    args = parser.parse_args()
    # Terraform state/plans and downloaded backend metadata stay private.
    os.umask(0o077)
    try:
        if args.action in {"validate", "test"}:
            execute(args.env, args.action, args.account)
        else:
            with operation_lock(BASE):
                execute(args.env, args.action, args.account)
    except (Exception, KeyboardInterrupt) as error:
        explain_failure(error, args.action, args.env)
        if isinstance(error, KeyboardInterrupt):
            return 130
        return (
            error.returncode if isinstance(error, subprocess.CalledProcessError) else 1
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
