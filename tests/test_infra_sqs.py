"""Contrato e redrive de SQS executados contra o LocalStack do Compose (VE-17)."""

import json
import os
from uuid import uuid4

import pytest

from scripts.infra.localstack_resources import clients
from scripts.infra.sqs_resources import (
    DEAD_LETTER_QUEUE,
    MAX_RECEIVE_COUNT,
    PROCESSING_QUEUE,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("VINTEX_INFRA_SQS_TEST") != "1",
    reason="requer o Compose vintex-infra; execute make test-sqs",
)


def test_fila_seeded_tem_redrive_e_processa_contrato() -> None:
    sqs = clients()["sqs"]
    processing_url = sqs.get_queue_url(QueueName=PROCESSING_QUEUE)["QueueUrl"]
    dead_letter_url = sqs.get_queue_url(QueueName=DEAD_LETTER_QUEUE)["QueueUrl"]
    dead_letter_arn = sqs.get_queue_attributes(
        QueueUrl=dead_letter_url,
        AttributeNames=["QueueArn"],
    )["Attributes"]["QueueArn"]
    policy = json.loads(
        sqs.get_queue_attributes(
            QueueUrl=processing_url,
            AttributeNames=["RedrivePolicy"],
        )["Attributes"]["RedrivePolicy"]
    )
    assert policy == {
        "deadLetterTargetArn": dead_letter_arn,
        "maxReceiveCount": str(MAX_RECEIVE_COUNT),
    }

    message = {
        "product_id": 123,
        "image_urls": ["https://images.example.test/product-123.jpg"],
    }
    test_queue_url = sqs.create_queue(
        QueueName=f"vintex-infra-contract-{uuid4().hex[:12]}"
    )["QueueUrl"]
    try:
        sent = sqs.send_message(
            QueueUrl=test_queue_url, MessageBody=json.dumps(message)
        )
        received = sqs.receive_message(
            QueueUrl=test_queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=2,
        )["Messages"]
        assert len(received) == 1
        assert received[0]["Body"] == json.dumps(message)
        sqs.delete_message(
            QueueUrl=test_queue_url,
            ReceiptHandle=received[0]["ReceiptHandle"],
        )
    finally:
        sqs.delete_queue(QueueUrl=test_queue_url)
    assert sent["MessageId"]


def test_mensagem_com_falhas_repetidas_chega_a_dlq() -> None:
    sqs = clients()["sqs"]
    suffix = uuid4().hex[:12]
    dlq_name = f"vintex-infra-test-dlq-{suffix}"
    queue_name = f"vintex-infra-test-retry-{suffix}"
    dlq_url = queue_url = None
    body = json.dumps({"product_id": 456, "image_urls": ["https://example.test/a.jpg"]})

    try:
        dlq_url = sqs.create_queue(QueueName=dlq_name)["QueueUrl"]
        dlq_arn = sqs.get_queue_attributes(
            QueueUrl=dlq_url,
            AttributeNames=["QueueArn"],
        )["Attributes"]["QueueArn"]
        queue_url = sqs.create_queue(
            QueueName=queue_name,
            Attributes={
                "VisibilityTimeout": "0",
                "RedrivePolicy": json.dumps(
                    {
                        "deadLetterTargetArn": dlq_arn,
                        "maxReceiveCount": str(MAX_RECEIVE_COUNT),
                    }
                ),
            },
        )["QueueUrl"]
        sqs.send_message(QueueUrl=queue_url, MessageBody=body)

        receives = 0
        moved_to_dlq = []
        for _ in range(MAX_RECEIVE_COUNT + 4):
            messages = sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=1,
                AttributeNames=["ApproximateReceiveCount"],
            ).get("Messages", [])
            if messages:
                receives += 1
            moved_to_dlq = sqs.receive_message(
                QueueUrl=dlq_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=1,
            ).get("Messages", [])
            if moved_to_dlq:
                break

        assert receives == MAX_RECEIVE_COUNT
        assert len(moved_to_dlq) == 1
        assert moved_to_dlq[0]["Body"] == body
        sqs.delete_message(
            QueueUrl=dlq_url,
            ReceiptHandle=moved_to_dlq[0]["ReceiptHandle"],
        )
    finally:
        if queue_url:
            sqs.delete_queue(QueueUrl=queue_url)
        if dlq_url:
            sqs.delete_queue(QueueUrl=dlq_url)
