"""Consumo do worker contra o LocalStack do Compose (VE-18)."""

import json
import os
from uuid import uuid4

import pytest

from app.workers import ai_analysis
from scripts.infra.localstack_resources import clients

pytestmark = pytest.mark.skipif(
    os.environ.get("VINTEX_INFRA_AI_WORKER_TEST") != "1",
    reason="requer o Compose vintex-infra; execute make test-ai-worker",
)


def test_worker_consumes_sqs_contract_and_deletes_only_after_success(monkeypatch):
    sqs = clients()["sqs"]
    queue_name = f"vintex-infra-worker-{uuid4().hex[:12]}"
    queue_url = sqs.create_queue(
        QueueName=queue_name,
        Attributes={"VisibilityTimeout": "0"},
    )["QueueUrl"]
    monkeypatch.setattr(ai_analysis.settings, "AI_ANALYSIS_QUEUE_URL", queue_url)
    monkeypatch.setattr(ai_analysis, "create_sqs_client", lambda: sqs)

    try:
        sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(
                {"product_id": 123, "image_urls": ["https://cdn.test/123.jpg"]}
            ),
        )
        monkeypatch.setattr(
            ai_analysis,
            "process_image_analysis",
            lambda product_id, image_urls: product_id == 123
            and image_urls == ["https://cdn.test/123.jpg"],
        )

        assert ai_analysis.poll_once() == 1
        assert not sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=1).get(
            "Messages"
        )

        sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(
                {"product_id": 124, "image_urls": ["https://cdn.test/124.jpg"]}
            ),
        )
        monkeypatch.setattr(ai_analysis, "process_image_analysis", lambda *_: False)

        assert ai_analysis.poll_once() == 0
        attrs = sqs.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=["ApproximateNumberOfMessagesNotVisible"],
        )["Attributes"]
        assert attrs["ApproximateNumberOfMessagesNotVisible"] == "1"
    finally:
        sqs.delete_queue(QueueUrl=queue_url)
