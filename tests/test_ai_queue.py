import json

import pytest

from app.services.ai.queue import ImageAnalysisQueueError, enqueue_image_analysis


def test_enqueue_publishes_documented_message(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.ai.queue.settings.AI_ANALYSIS_QUEUE_URL", "https://sqs.test/queue"
    )

    class _Sqs:
        def send_message(self, **kwargs):
            self.kwargs = kwargs

    sqs = _Sqs()
    monkeypatch.setattr("app.services.ai.queue.create_sqs_client", lambda: sqs)

    enqueue_image_analysis(42, ["https://cdn.test/42.jpg"])

    assert sqs.kwargs["QueueUrl"] == "https://sqs.test/queue"
    assert json.loads(sqs.kwargs["MessageBody"]) == {
        "product_id": 42,
        "image_urls": ["https://cdn.test/42.jpg"],
    }


def test_enqueue_requires_configured_queue(monkeypatch) -> None:
    monkeypatch.setattr("app.services.ai.queue.settings.AI_ANALYSIS_QUEUE_URL", "")

    with pytest.raises(ImageAnalysisQueueError, match="não configurada"):
        enqueue_image_analysis(42, ["https://cdn.test/42.jpg"])


def test_enqueue_hides_transport_details(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.ai.queue.settings.AI_ANALYSIS_QUEUE_URL", "https://sqs.test/queue"
    )

    class _Sqs:
        def send_message(self, **kwargs):
            raise RuntimeError("secret transport detail")

    monkeypatch.setattr("app.services.ai.queue.create_sqs_client", lambda: _Sqs())

    with pytest.raises(ImageAnalysisQueueError) as error:
        enqueue_image_analysis(42, ["https://cdn.test/42.jpg"])

    assert "secret transport detail" not in str(error.value)
