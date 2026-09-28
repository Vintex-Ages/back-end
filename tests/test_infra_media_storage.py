"""Roundtrip de mídia no LocalStack; ativado por `make test-media-storage`."""

import os

import pytest
from botocore.exceptions import ClientError

from app.services.media_storage import MEDIA_PREFIXES, MediaKind, MediaStorage
from scripts.infra.media_storage_resources import BUCKET, PUBLIC_ACCESS_BLOCK, verify

pytestmark = pytest.mark.skipif(
    os.environ.get("VINTEX_INFRA_MEDIA_TEST") != "1",
    reason="requer o Compose vintex-infra; execute make test-media-storage",
)


@pytest.mark.parametrize("kind", ["photo", "video", "receipt"])
def test_upload_leitura_e_limpeza_no_bucket_privado(kind: MediaKind) -> None:
    storage = MediaStorage.from_settings()
    assert storage.bucket == BUCKET
    key = storage.upload(kind, b"synthetic-media", "application/octet-stream")
    try:
        assert key.startswith(MEDIA_PREFIXES[kind])
        assert storage.read(key) == b"synthetic-media"
        block = storage.client.get_public_access_block(Bucket=BUCKET)[
            "PublicAccessBlockConfiguration"
        ]
        assert all(
            block[name] == expected for name, expected in PUBLIC_ACCESS_BLOCK.items()
        )
    finally:
        storage.delete(key)

    with pytest.raises(ClientError) as missing:
        storage.client.head_object(Bucket=BUCKET, Key=key)
    assert missing.value.response["ResponseMetadata"]["HTTPStatusCode"] == 404
    verify()
