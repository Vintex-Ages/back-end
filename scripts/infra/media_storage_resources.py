"""Provisiona o bucket de mídia somente no LocalStack (VE-16)."""

from __future__ import annotations

import argparse
import os

from botocore.exceptions import ClientError

from scripts.infra.localstack_resources import REGION, clients, endpoint_url

BUCKET = os.environ.get("MEDIA_BUCKET", "vintex-local-media")
PUBLIC_ACCESS_BLOCK = {
    "BlockPublicAcls": True,
    "BlockPublicPolicy": True,
    "IgnorePublicAcls": True,
    "RestrictPublicBuckets": True,
}


def seed() -> None:
    """Cria o bucket local de forma idempotente e aplica as proteções do módulo."""
    s3 = clients()["s3"]
    try:
        s3.head_bucket(Bucket=BUCKET)
    except ClientError as error:
        if error.response["Error"]["Code"] not in {"404", "NoSuchBucket", "NotFound"}:
            raise
        s3.create_bucket(
            Bucket=BUCKET,
            CreateBucketConfiguration={"LocationConstraint": REGION},
        )

    s3.put_public_access_block(
        Bucket=BUCKET, PublicAccessBlockConfiguration=PUBLIC_ACCESS_BLOCK
    )
    s3.put_bucket_encryption(
        Bucket=BUCKET,
        ServerSideEncryptionConfiguration={
            "Rules": [
                {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
            ]
        },
    )
    print(f"[media-storage] bucket {BUCKET} pronto em {endpoint_url()}")


def verify() -> None:
    """Confirma que o bucket segue o contrato privado do Terraform."""
    s3 = clients()["s3"]
    s3.head_bucket(Bucket=BUCKET)
    actual = s3.get_public_access_block(Bucket=BUCKET)["PublicAccessBlockConfiguration"]
    if any(actual.get(key) != value for key, value in PUBLIC_ACCESS_BLOCK.items()):
        raise AssertionError("bloqueio de acesso público do bucket de mídia divergiu")
    encryption = s3.get_bucket_encryption(Bucket=BUCKET)
    algorithm = encryption["ServerSideEncryptionConfiguration"]["Rules"][0][
        "ApplyServerSideEncryptionByDefault"
    ]["SSEAlgorithm"]
    if algorithm != "AES256":
        raise AssertionError("criptografia do bucket de mídia divergiu")
    print(f"[media-storage] bucket {BUCKET} verificado em {endpoint_url()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seed", "verify"))
    args = parser.parse_args()
    {"seed": seed, "verify": verify}[args.action]()
