import json

import pytest

from app.services.ai.base import AIProviderError, AIProviderUnavailableError
from app.services.ai.freellmapi import FreeLLMAPIProvider
from app.workers.ai_analysis import (
    InvalidImageAnalysisMessage,
    parse_message,
    process_message,
)


def test_parse_message_accepts_contract_of_issue_168() -> None:
    assert parse_message(
        json.dumps(
            {
                "product_id": 12,
                "image_urls": ["https://cdn.test/photo.jpg"],
            }
        )
    ) == (12, ["https://cdn.test/photo.jpg"])


@pytest.mark.parametrize(
    "body",
    [
        "not-json",
        "[]",
        '{"product_id":0,"image_urls":["https://cdn.test/a.jpg"]}',
        '{"product_id":true,"image_urls":["https://cdn.test/a.jpg"]}',
        '{"product_id":1,"image_urls":[]}',
        '{"product_id":1,"image_urls":[""]}',
    ],
)
def test_parse_message_rejects_invalid_contract(body: str) -> None:
    with pytest.raises(InvalidImageAnalysisMessage):
        parse_message(body)


def test_worker_deletes_message_only_after_success() -> None:
    class _Sqs:
        deleted = []

        def delete_message(self, **kwargs):
            self.deleted.append(kwargs)

    sqs = _Sqs()
    message = {
        "Body": '{"product_id":4,"image_urls":["https://cdn.test/a"]}',
        "ReceiptHandle": "receipt",
    }

    assert process_message(sqs, "queue", message, processor=lambda *_: True) is True
    assert sqs.deleted == [{"QueueUrl": "queue", "ReceiptHandle": "receipt"}]

    assert process_message(sqs, "queue", message, processor=lambda *_: False) is False
    assert len(sqs.deleted) == 1


def test_worker_keeps_invalid_message_for_redrive() -> None:
    class _Sqs:
        deleted = False

        def delete_message(self, **kwargs):
            self.deleted = True

    sqs = _Sqs()
    message = {"Body": "{}", "ReceiptHandle": "receipt"}

    assert process_message(sqs, "queue", message) is False
    assert sqs.deleted is False


def test_freellmapi_requires_runtime_key(monkeypatch) -> None:
    monkeypatch.setattr("app.services.ai.freellmapi.settings.FREELLMAPI_API_KEY", "")

    with pytest.raises(AIProviderUnavailableError):
        FreeLLMAPIProvider()


def test_freellmapi_sends_inline_image_and_parses_suggestions(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.ai.freellmapi.settings.FREELLMAPI_API_KEY", "fake-test-token"
    )
    monkeypatch.setattr(
        "app.services.ai.freellmapi.settings.FREELLMAPI_BASE_URL",
        "http://freellmapi:3001/v1/",
    )
    monkeypatch.setattr("app.services.ai.freellmapi.settings.FREELLMAPI_MODEL", "auto")
    captured = {}

    class _ImageResponse:
        headers = {"content-type": "image/jpeg"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            pass

        def iter_bytes(self, chunk_size):
            yield b"fake-image"

    class _HttpClient:
        def __init__(self, **kwargs):
            captured["download_options"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, method, url):
            captured["image_url"] = url
            return _ImageResponse()

    class _ProviderResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"category":{"value":"Jaqueta","confidence":0.9}}'
                        }
                    }
                ]
            }

    def fake_post(url, **kwargs):
        captured["request_url"] = url
        captured["request"] = kwargs
        return _ProviderResponse()

    monkeypatch.setattr("app.services.ai.freellmapi.httpx.Client", _HttpClient)
    monkeypatch.setattr("app.services.ai.freellmapi.httpx.post", fake_post)

    result = FreeLLMAPIProvider().analyze_image(["https://cdn.test/signed?a=secret"])

    assert result.category.value == "Jaqueta"
    assert captured["request_url"] == "http://freellmapi:3001/v1/chat/completions"
    assert captured["request"]["headers"]["Authorization"] == "Bearer fake-test-token"
    request_content = captured["request"]["json"]["messages"][0]["content"]
    assert (
        request_content[1]["image_url"]["url"]
        == "data:image/jpeg;base64,ZmFrZS1pbWFnZQ=="
    )
    assert "secret" not in json.dumps(captured["request"])


def test_freellmapi_rejects_invalid_json_response(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.ai.freellmapi.settings.FREELLMAPI_API_KEY", "fake-test-token"
    )

    class _ImageResponse:
        headers = {"content-type": "image/jpeg"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            pass

        def iter_bytes(self, chunk_size):
            yield b"image"

    class _HttpClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def stream(self, method, url):
            return _ImageResponse()

    class _ProviderResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "not-json"}}]}

    monkeypatch.setattr("app.services.ai.freellmapi.httpx.Client", _HttpClient)
    monkeypatch.setattr(
        "app.services.ai.freellmapi.httpx.post",
        lambda *args, **kwargs: _ProviderResponse(),
    )

    with pytest.raises(AIProviderError, match="análise inválida"):
        FreeLLMAPIProvider().analyze_image(["https://cdn.test/a.jpg"])
