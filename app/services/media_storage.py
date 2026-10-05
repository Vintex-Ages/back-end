"""Cliente S3 para mídia; regras de upload do produto pertencem à VE-04."""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

import boto3
from botocore.client import BaseClient
from botocore.config import Config

from app.config import Settings, settings

# `logo` existe para a imagem da loja nao morar em `products/photos/`
# (back-end#220). O `front-end#212` sobe a logo por esta rota e manda a URL em
# `POST /api/users/me/store`; sem um prefixo proprio, logo de brecho e foto de
# peca ficariam misturadas no bucket para sempre, e qualquer limpeza de fotos
# de peca apagada levaria logo junto.
MediaKind = Literal["photo", "video", "receipt", "logo"]
MEDIA_PREFIXES: dict[MediaKind, str] = {
    "photo": "products/photos/",
    "video": "products/videos/",
    "receipt": "payments/receipts/",
    "logo": "stores/logos/",
}


def create_media_s3_client(config: Settings = settings) -> BaseClient:
    """Usa credenciais padrão do boto3 e endpoint local quando configurado."""
    return boto3.client(
        "s3",
        region_name=config.AWS_REGION,
        endpoint_url=config.S3_ENDPOINT_URL,
        config=(
            Config(s3={"addressing_style": "path"}) if config.S3_ENDPOINT_URL else None
        ),
    )


class MediaStorage:
    """Operações mínimas de objeto, sem regras de formato/tamanho ou URLs."""

    def __init__(self, bucket: str, client: BaseClient) -> None:
        self.bucket = bucket
        self.client = client

    @classmethod
    def from_settings(cls, config: Settings = settings) -> "MediaStorage":
        if not config.MEDIA_BUCKET:
            raise ValueError("MEDIA_BUCKET deve ser configurado para usar o storage")
        return cls(config.MEDIA_BUCKET, create_media_s3_client(config))

    def upload(self, kind: MediaKind, body: bytes, content_type: str) -> str:
        key = f"{MEDIA_PREFIXES[kind]}{uuid4().hex}"
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=body, ContentType=content_type
        )
        return key

    def read(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def read_with_type(self, key: str) -> tuple[bytes, str]:
        """Bytes e `Content-Type` gravado no upload.

        A chave e um uuid sem extensao, entao quem serve o arquivo depois nao
        tem como adivinhar o tipo pelo nome: ele vem do objeto.
        """
        objeto = self.client.get_object(Bucket=self.bucket, Key=key)
        content_type = objeto.get("ContentType") or "application/octet-stream"
        return objeto["Body"].read(), content_type

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)
