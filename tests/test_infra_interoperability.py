"""Fluxo local entre API, Postgres, LocalStack e MiniStack (VE-22)."""

import json
import os
from contextlib import ExitStack
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, text

from scripts.infra.localstack_resources import REGION
from scripts.infra.localstack_resources import clients as local_clients
from scripts.infra.ministack_resources import (
    API,
    CLUSTER,
    DISCOVERY_SERVICE,
    NAMESPACE,
    REPOSITORY,
)
from scripts.infra.ministack_resources import (
    clients as mini_clients,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("VINTEX_INFRA_INTEROP_TEST") != "1",
    reason="requer o Compose vintex-infra; execute make test-interoperability",
)


def _discovery_service_id(sd: object) -> str:
    namespace = next(
        item for item in sd.list_namespaces()["Namespaces"] if item["Name"] == NAMESPACE
    )
    service = next(
        item
        for item in sd.list_services(
            Filters=[{"Name": "NAMESPACE_ID", "Values": [namespace["Id"]]}]
        )["Services"]
        if item["Name"] == DISCOVERY_SERVICE
    )
    return service["Id"]


def _synthetic_worker_once(
    sqs: object,
    s3: object,
    sd: object,
    queue_url: str,
    service_id: str,
    *,
    fail_after_s3: bool = False,
) -> tuple[dict, str]:
    """Consome uma mensagem SQS e publica o resultado em S3 e Cloud Map."""
    messages = sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=2,
    )["Messages"]
    assert len(messages) == 1
    message = messages[0]
    job = json.loads(message["Body"])
    result = {"job_id": job["job_id"], "status": "processed"}
    s3.put_object(
        Bucket=job["bucket"],
        Key=job["key"],
        Body=json.dumps(result).encode(),
        ContentType="application/json",
    )
    if fail_after_s3:
        raise RuntimeError("falha sintética após gravar no S3")
    sd.register_instance(
        ServiceId=service_id,
        InstanceId=job["job_id"],
        Attributes={"S3_BUCKET": job["bucket"], "S3_KEY": job["key"]},
    )
    return result, message["ReceiptHandle"]


def _run_probe(name: str, *, fail_after_s3: bool = False) -> dict:
    local = local_clients()
    mini = mini_clients()
    s3, sqs, sd = local["s3"], local["sqs"], mini["servicediscovery"]
    service_id = _discovery_service_id(sd)
    bucket = queue = name
    key = "result.json"
    job = {"job_id": name, "bucket": bucket, "key": key}

    with ExitStack() as cleanup:
        s3.create_bucket(
            Bucket=bucket,
            CreateBucketConfiguration={"LocationConstraint": REGION},
        )
        cleanup.callback(s3.delete_bucket, Bucket=bucket)
        cleanup.callback(s3.delete_object, Bucket=bucket, Key=key)
        queue_url = sqs.create_queue(QueueName=queue)["QueueUrl"]
        cleanup.callback(sqs.delete_queue, QueueUrl=queue_url)
        sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(job))
        result, receipt_handle = _synthetic_worker_once(
            sqs,
            s3,
            sd,
            queue_url,
            service_id,
            fail_after_s3=fail_after_s3,
        )
        cleanup.callback(sd.deregister_instance, ServiceId=service_id, InstanceId=name)
        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
        stored = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
        assert stored == result
        discovered = sd.discover_instances(
            NamespaceName=NAMESPACE,
            ServiceName=DISCOVERY_SERVICE,
        )["Instances"]
        assert any(
            item["InstanceId"] == name
            and item["Attributes"]["S3_BUCKET"] == bucket
            and item["Attributes"]["S3_KEY"] == key
            for item in discovered
        )
        assert not sqs.receive_message(QueueUrl=queue_url).get("Messages")
        return result


def _assert_probe_removed(name: str) -> None:
    local = local_clients()
    mini = mini_clients()
    assert name not in {item["Name"] for item in local["s3"].list_buckets()["Buckets"]}
    assert not local["sqs"].list_queues(QueueNamePrefix=name).get("QueueUrls")
    assert name not in {
        item["InstanceId"]
        for item in mini["servicediscovery"].discover_instances(
            NamespaceName=NAMESPACE,
            ServiceName=DISCOVERY_SERVICE,
        )["Instances"]
    }


def test_api_uses_migrated_postgres_and_both_emulators() -> None:
    assert os.environ["LOCALSTACK_ENDPOINT_URL"] == "http://localstack:4566"
    assert os.environ["MINISTACK_ENDPOINT_URL"] == "http://ministack:4567"
    assert httpx.get("http://api:8000/health", timeout=5).json() == {"status": "ok"}

    engine = create_engine(os.environ["DATABASE_URL"])
    try:
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT to_regclass('products')::text"))
                == "products"
            )
    finally:
        engine.dispose()
    feed = httpx.get("http://api:8000/api/products", timeout=5)
    assert feed.status_code == 200
    assert feed.json()["items"] == []

    local = local_clients()
    mini = mini_clients()
    assert local["sts"].get_caller_identity()["Account"]
    assert mini["ecs"].describe_clusters(clusters=[CLUSTER])["clusters"]
    assert any(item["Name"] == API for item in mini["apigatewayv2"].get_apis()["Items"])
    assert mini["ecr"].describe_repositories(repositoryNames=[REPOSITORY])[
        "repositories"
    ]


def test_synthetic_worker_crosses_emulators_and_cleans_up() -> None:
    name = f"vintex-infra-interop-{uuid4().hex[:12]}"
    assert _run_probe(name) == {"job_id": name, "status": "processed"}
    _assert_probe_removed(name)


def test_partial_failure_does_not_leak_resources() -> None:
    name = f"vintex-infra-interop-{uuid4().hex[:12]}"
    with pytest.raises(RuntimeError, match="falha sintética"):
        _run_probe(name, fail_after_s3=True)
    _assert_probe_removed(name)
