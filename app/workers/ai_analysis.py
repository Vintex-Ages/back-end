"""Consumidor SQS para tarefas de análise de imagens."""

from __future__ import annotations

import argparse
import json
import logging
import time
from collections.abc import Callable
from typing import Any

import boto3
from botocore.config import Config

from app.config import settings
from app.services.ai.pipeline import process_image_analysis

logger = logging.getLogger("vintex.ai.worker")
MAX_MESSAGES = 1
LONG_POLL_SECONDS = 20
PROCESSING_VISIBILITY_SECONDS = 180
RETRY_DELAY_SECONDS = 5


class InvalidImageAnalysisMessage(ValueError):
    """Mensagem SQS que não segue o contrato VE-17."""


def parse_message(body: str) -> tuple[int, list[str]]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise InvalidImageAnalysisMessage("Corpo da tarefa não é JSON válido.") from exc

    if not isinstance(payload, dict):
        raise InvalidImageAnalysisMessage("Corpo da tarefa precisa ser um objeto JSON.")

    product_id = payload.get("product_id")
    image_urls = payload.get("image_urls")
    if (
        isinstance(product_id, bool)
        or not isinstance(product_id, int)
        or product_id < 1
    ):
        raise InvalidImageAnalysisMessage("product_id precisa ser um inteiro positivo.")
    if (
        not isinstance(image_urls, list)
        or not image_urls
        or any(not isinstance(url, str) or not url.strip() for url in image_urls)
    ):
        raise InvalidImageAnalysisMessage("image_urls precisa conter URLs não vazias.")
    return product_id, image_urls


def create_sqs_client():
    return boto3.client(
        "sqs",
        region_name=settings.AWS_REGION,
        endpoint_url=settings.SQS_ENDPOINT_URL,
        config=Config(connect_timeout=3, read_timeout=25, retries={"max_attempts": 2}),
    )


def process_message(
    sqs: Any,
    queue_url: str,
    message: dict[str, Any],
    processor: Callable[[int, list[str]], bool] | None = None,
) -> bool:
    """Processa e confirma só os itens concluídos ou terminais."""
    try:
        product_id, image_urls = parse_message(message["Body"])
        completed = (processor or process_image_analysis)(product_id, image_urls)
    except Exception as exc:
        logger.warning(
            "Tarefa SQS não concluída; será tentada novamente (%s)",
            type(exc).__name__,
        )
        return False

    if not completed:
        return False

    sqs.delete_message(
        QueueUrl=queue_url,
        ReceiptHandle=message["ReceiptHandle"],
    )
    return True


def poll_once(sqs: Any | None = None) -> int:
    if not settings.AI_ANALYSIS_QUEUE_URL:
        raise RuntimeError("AI_ANALYSIS_QUEUE_URL não configurada para o worker.")

    client = sqs or create_sqs_client()
    messages = client.receive_message(
        QueueUrl=settings.AI_ANALYSIS_QUEUE_URL,
        MaxNumberOfMessages=MAX_MESSAGES,
        WaitTimeSeconds=LONG_POLL_SECONDS,
        VisibilityTimeout=PROCESSING_VISIBILITY_SECONDS,
    ).get("Messages", [])
    if not messages:
        return 0

    return int(process_message(client, settings.AI_ANALYSIS_QUEUE_URL, messages[0]))


def run_forever() -> None:
    while True:
        try:
            poll_once()
        except Exception:
            logger.exception("Falha no ciclo do worker SQS")
            time.sleep(RETRY_DELAY_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once", action="store_true", help="Executa um long poll e encerra."
    )
    args = parser.parse_args()
    if args.once:
        poll_once()
    else:
        run_forever()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
