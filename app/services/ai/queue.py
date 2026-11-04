"""Publicação de tarefas de análise de imagens na fila SQS."""

from __future__ import annotations

import json

import boto3
from botocore.config import Config

from app.config import settings


class ImageAnalysisQueueError(RuntimeError):
    """A análise não pôde ser publicada na fila configurada."""


def create_sqs_client():
    return boto3.client(
        "sqs",
        region_name=settings.AWS_REGION,
        endpoint_url=settings.SQS_ENDPOINT_URL,
        config=Config(connect_timeout=3, read_timeout=25, retries={"max_attempts": 2}),
    )


def enqueue_image_analysis(product_id: int, image_urls: list[str]) -> None:
    if not settings.AI_ANALYSIS_QUEUE_URL:
        raise ImageAnalysisQueueError("AI_ANALYSIS_QUEUE_URL não configurada.")

    try:
        create_sqs_client().send_message(
            QueueUrl=settings.AI_ANALYSIS_QUEUE_URL,
            MessageBody=json.dumps(
                {"product_id": product_id, "image_urls": image_urls},
                ensure_ascii=False,
            ),
        )
    except Exception as exc:
        raise ImageAnalysisQueueError(
            "Não foi possível publicar a análise na fila SQS."
        ) from exc
