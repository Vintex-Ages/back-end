"""Provisionamento e verificação das filas de análise no LocalStack (VE-17)."""

from __future__ import annotations

import argparse
import json

from scripts.infra.localstack_resources import clients

PROCESSING_QUEUE = "vintex-local-image-analysis"
DEAD_LETTER_QUEUE = "vintex-local-image-analysis-dlq"
MAX_RECEIVE_COUNT = 3


def _queue_arn(sqs: object, queue_url: str) -> str:
    attributes = sqs.get_queue_attributes(
        QueueUrl=queue_url,
        AttributeNames=["QueueArn"],
    )["Attributes"]
    return attributes["QueueArn"]


def seed() -> None:
    """Cria a DLQ e a fila de análise com redrive; repetir mantém a configuração."""
    sqs = clients()["sqs"]
    dead_letter_url = sqs.create_queue(QueueName=DEAD_LETTER_QUEUE)["QueueUrl"]
    dead_letter_arn = _queue_arn(sqs, dead_letter_url)
    processing_url = sqs.create_queue(QueueName=PROCESSING_QUEUE)["QueueUrl"]
    sqs.set_queue_attributes(
        QueueUrl=processing_url,
        Attributes={
            "RedrivePolicy": json.dumps(
                {
                    "deadLetterTargetArn": dead_letter_arn,
                    "maxReceiveCount": str(MAX_RECEIVE_COUNT),
                }
            )
        },
    )
    print(
        f"[sqs] {PROCESSING_QUEUE} -> {DEAD_LETTER_QUEUE} "
        f"(maxReceiveCount={MAX_RECEIVE_COUNT})"
    )


def verify() -> None:
    """Confirma a política e o destino na mesma instância LocalStack do Compose."""
    sqs = clients()["sqs"]
    processing_url = sqs.get_queue_url(QueueName=PROCESSING_QUEUE)["QueueUrl"]
    dead_letter_url = sqs.get_queue_url(QueueName=DEAD_LETTER_QUEUE)["QueueUrl"]
    attributes = sqs.get_queue_attributes(
        QueueUrl=processing_url,
        AttributeNames=["RedrivePolicy"],
    )["Attributes"]
    policy = json.loads(attributes["RedrivePolicy"])
    expected_arn = _queue_arn(sqs, dead_letter_url)
    if policy != {
        "deadLetterTargetArn": expected_arn,
        "maxReceiveCount": str(MAX_RECEIVE_COUNT),
    }:
        raise AssertionError(f"política de redrive inesperada: {policy}")
    print(f"[sqs] redrive verificado em {PROCESSING_QUEUE}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seed", "verify"))
    args = parser.parse_args()
    {"seed": seed, "verify": verify}[args.action]()
