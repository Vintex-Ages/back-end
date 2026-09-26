"""Contrato do cliente S3 de mídia sem rede ou credenciais reais."""

from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.services.media_storage import (
    MEDIA_PREFIXES,
    MediaKind,
    MediaStorage,
    create_media_s3_client,
)


def test_client_usa_endpoint_e_path_style_no_localstack() -> None:
    config = Settings(
        _env_file=None,
        AWS_REGION="us-east-2",
        S3_ENDPOINT_URL="http://localstack:4566",
        MEDIA_BUCKET="vintex-local-media",
    )
    with patch("app.services.media_storage.boto3.client") as factory:
        assert create_media_s3_client(config) is factory.return_value

    _, kwargs = factory.call_args
    assert kwargs["region_name"] == "us-east-2"
    assert kwargs["endpoint_url"] == "http://localstack:4566"
    assert kwargs["config"].s3["addressing_style"] == "path"


def test_client_sem_endpoint_usa_resolucao_padrao_da_aws() -> None:
    config = Settings(
        _env_file=None, S3_ENDPOINT_URL=None, MEDIA_BUCKET="vintex-prod-media"
    )
    with patch("app.services.media_storage.boto3.client") as factory:
        create_media_s3_client(config)

    _, kwargs = factory.call_args
    assert kwargs["endpoint_url"] is None
    assert kwargs["config"] is None
    assert "aws_access_key_id" not in kwargs


def test_bucket_deve_ser_configurado() -> None:
    with pytest.raises(ValueError, match="MEDIA_BUCKET"):
        MediaStorage.from_settings(Settings(_env_file=None, MEDIA_BUCKET=None))


@pytest.mark.parametrize("kind", ["photo", "video", "receipt"])
def test_upload_leitura_e_limpeza_usam_prefixo_e_bucket(kind: MediaKind) -> None:
    client = MagicMock()
    client.get_object.return_value = {"Body": MagicMock(read=lambda: b"synthetic")}
    storage = MediaStorage("vintex-local-media", client)

    key = storage.upload(kind, b"synthetic", "application/octet-stream")
    assert key.startswith(MEDIA_PREFIXES[kind])
    assert len(key) > len(MEDIA_PREFIXES[kind])
    client.put_object.assert_called_once_with(
        Bucket="vintex-local-media",
        Key=key,
        Body=b"synthetic",
        ContentType="application/octet-stream",
    )
    assert storage.read(key) == b"synthetic"
    client.get_object.assert_called_once_with(Bucket="vintex-local-media", Key=key)
    storage.delete(key)
    client.delete_object.assert_called_once_with(Bucket="vintex-local-media", Key=key)
