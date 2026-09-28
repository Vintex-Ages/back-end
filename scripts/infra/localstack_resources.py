"""Recursos sintéticos usados pelos smoke tests do LocalStack (VE-20)."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import dotenv_values

BUCKET = "vintex-infra-smoke"
QUEUE = "vintex-infra-smoke"
SECRET = "vintex/infra/synthetic"
IAM_USER = "vintex-infra-smoke"
SECRET_VALUE = json.dumps({"synthetic": True})
REGION = "us-east-2"
ROOT = Path(__file__).resolve().parents[2]


def endpoint_url() -> str:
    """Resolve apenas endpoints locais; uma falha nunca pode atingir a AWS."""
    env_file = dotenv_values(ROOT / "infra/vintex-infra/.env")
    port = (
        os.environ.get("LOCALSTACK_HOST_PORT")
        or env_file.get("LOCALSTACK_HOST_PORT")
        or "4566"
    )
    endpoint = os.environ.get("LOCALSTACK_ENDPOINT_URL") or f"http://127.0.0.1:{port}"
    parsed = urlparse(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "localstack",
    }:
        raise ValueError("LOCALSTACK_ENDPOINT_URL deve apontar para o LocalStack local")
    if not parsed.port or parsed.path not in ("", "/"):
        raise ValueError("LOCALSTACK_ENDPOINT_URL precisa ter porta e nenhuma rota")
    return endpoint


def clients() -> dict[str, object]:
    """Cria clientes AWS sempre apontados explicitamente ao emulador local."""
    endpoint = endpoint_url()
    config = Config(
        connect_timeout=3,
        read_timeout=5,
        retries={"max_attempts": 2},
        s3={"addressing_style": "path"},
    )
    return {
        service: boto3.client(
            service,
            endpoint_url=endpoint,
            region_name=REGION,
            aws_access_key_id="test",
            aws_secret_access_key="test",
            config=config,
        )
        for service in ("s3", "sqs", "secretsmanager", "iam", "sts")
    }


def _missing(error: ClientError, *codes: str) -> bool:
    return error.response["Error"]["Code"] in codes


def seed() -> None:
    """Prepara uma base estável e pode rodar novamente sem duplicar recursos."""
    aws = clients()
    try:
        aws["s3"].head_bucket(Bucket=BUCKET)
    except ClientError as error:
        if not _missing(error, "404", "NoSuchBucket", "NotFound"):
            raise
        aws["s3"].create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": REGION},
        )

    aws["sqs"].create_queue(QueueName=QUEUE)

    try:
        aws["secretsmanager"].describe_secret(SecretId=SECRET)
    except ClientError as error:
        if not _missing(error, "ResourceNotFoundException"):
            raise
        aws["secretsmanager"].create_secret(Name=SECRET, SecretString=SECRET_VALUE)

    try:
        aws["iam"].get_user(UserName=IAM_USER)
    except ClientError as error:
        if not _missing(error, "NoSuchEntity"):
            raise
        aws["iam"].create_user(UserName=IAM_USER)

    aws["sts"].get_caller_identity()
    print("[localstack] S3, SQS, Secrets Manager, IAM e STS prontos")


def verify() -> None:
    """Confirma os recursos também de dentro de um container da rede Compose."""
    aws = clients()
    aws["s3"].head_bucket(Bucket=BUCKET)
    aws["sqs"].get_queue_url(QueueName=QUEUE)
    secret = aws["secretsmanager"].get_secret_value(SecretId=SECRET)
    if secret["SecretString"] != SECRET_VALUE:
        raise AssertionError("segredo sintético inesperado")
    aws["iam"].get_user(UserName=IAM_USER)
    aws["sts"].get_caller_identity()
    print(f"[localstack] recursos acessíveis por {endpoint_url()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seed", "verify"))
    args = parser.parse_args()
    {"seed": seed, "verify": verify}[args.action]()
