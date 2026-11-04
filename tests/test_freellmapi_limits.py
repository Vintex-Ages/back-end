"""Exercise real HTTPX streaming and serialization without external requests."""

import httpx
import pytest

from app.services.ai.base import AIProviderError
from app.services.ai.freellmapi import FreeLLMAPIProvider

MIB = 1024 * 1024


@pytest.fixture
def gateway(monkeypatch):
    from app.services.ai import freellmapi

    monkeypatch.setattr(freellmapi.settings, "FREELLMAPI_API_KEY", "synthetic-key")
    client_type = httpx.Client
    captured = {"sizes": [], "status": 200}

    def download(request):
        size = int(request.url.path.removeprefix("/"))
        return httpx.Response(
            200, content=b"x" * size, headers={"Content-Type": "image/jpeg"}
        )

    monkeypatch.setattr(
        freellmapi.httpx,
        "Client",
        lambda **kwargs: client_type(transport=httpx.MockTransport(download), **kwargs),
    )

    def post(url, **kwargs):
        request = httpx.Request("POST", url, json=kwargs["json"])
        captured["sizes"].append(len(request.content))
        return httpx.Response(
            captured["status"],
            request=request,
            json={"choices": [{"message": {"content": "{}"}}]},
        )

    monkeypatch.setattr(freellmapi.httpx, "post", post)
    return captured


@pytest.mark.parametrize("sizes", [[8 * MIB], [8 * MIB] * 3])
def test_allowed_images_fit_gateway_json_limit(gateway, sizes):
    FreeLLMAPIProvider().analyze_image([f"https://image.test/{size}" for size in sizes])
    assert len(gateway["sizes"]) == 1
    serialized_bytes = gateway["sizes"][0]
    assert sum(sizes) * 4 // 3 < serialized_bytes < 40 * MIB
    if len(sizes) == 3:
        assert serialized_bytes > 25 * MIB


@pytest.mark.parametrize(
    "sizes,message",
    [
        ([8 * MIB + 1], "8 MiB"),
        ([6 * MIB] * 3 + [6 * MIB + 1], "24 MiB"),
    ],
)
def test_excess_image_bytes_are_rejected_before_post(gateway, sizes, message):
    with pytest.raises(AIProviderError, match=message):
        FreeLLMAPIProvider().analyze_image(
            [f"https://image.test/{size}" for size in sizes]
        )
    assert gateway["sizes"] == []


@pytest.mark.parametrize("status", [401, 413, 429, 503])
def test_gateway_failures_remain_provider_errors(gateway, status):
    gateway["status"] = status
    with pytest.raises(AIProviderError, match="análise inválida"):
        FreeLLMAPIProvider().analyze_image(["https://image.test/64"])
