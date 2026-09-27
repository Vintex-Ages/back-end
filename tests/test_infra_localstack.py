"""Smoke tests reais do LocalStack; ativados por `make test-localstack`."""

import json
import os
from uuid import uuid4

import pytest

from scripts.infra.localstack_resources import (
    BUCKET,
    IAM_USER,
    QUEUE,
    REGION,
    SECRET,
    SECRET_VALUE,
    clients,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("VINTEX_INFRA_LOCALSTACK_TEST") != "1",
    reason="requer o Compose vintex-infra; execute make test-localstack",
)


def test_seeded_services_are_available() -> None:
    aws = clients()
    assert BUCKET in {bucket["Name"] for bucket in aws["s3"].list_buckets()["Buckets"]}
    assert aws["sqs"].get_queue_url(QueueName=QUEUE)["QueueUrl"]
    value = aws["secretsmanager"].get_secret_value(SecretId=SECRET)["SecretString"]
    assert json.loads(value) == json.loads(SECRET_VALUE)
    assert aws["iam"].get_user(UserName=IAM_USER)["User"]["UserName"] == IAM_USER
    assert aws["sts"].get_caller_identity()["Account"]


def test_synthetic_resources_roundtrip_and_cleanup() -> None:
    aws = clients()
    suffix = uuid4().hex[:12]
    bucket = f"vintex-infra-test-{suffix}"
    queue = f"vintex-infra-test-{suffix}"
    secret = f"vintex/infra/test-{suffix}"
    user = f"vintex-infra-test-{suffix}"
    queue_url = None
    created_bucket = created_secret = created_user = False

    try:
        aws["s3"].create_bucket(
            Bucket=bucket,
            CreateBucketConfiguration={"LocationConstraint": REGION},
        )
        created_bucket = True
        aws["s3"].put_object(Bucket=bucket, Key="probe.txt", Body=b"synthetic")
        assert (
            aws["s3"].get_object(Bucket=bucket, Key="probe.txt")["Body"].read()
            == b"synthetic"
        )

        queue_url = aws["sqs"].create_queue(QueueName=queue)["QueueUrl"]
        aws["sqs"].send_message(QueueUrl=queue_url, MessageBody="synthetic")
        messages = aws["sqs"].receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=2,
        )["Messages"]
        assert messages[0]["Body"] == "synthetic"
        aws["sqs"].delete_message(
            QueueUrl=queue_url,
            ReceiptHandle=messages[0]["ReceiptHandle"],
        )

        aws["secretsmanager"].create_secret(Name=secret, SecretString="synthetic")
        created_secret = True
        assert (
            aws["secretsmanager"].get_secret_value(SecretId=secret)["SecretString"]
            == "synthetic"
        )

        aws["iam"].create_user(UserName=user)
        created_user = True
        assert aws["iam"].get_user(UserName=user)["User"]["UserName"] == user
    finally:
        if created_user:
            aws["iam"].delete_user(UserName=user)
        if created_secret:
            aws["secretsmanager"].delete_secret(
                SecretId=secret,
                ForceDeleteWithoutRecovery=True,
            )
        if queue_url:
            aws["sqs"].delete_queue(QueueUrl=queue_url)
        if created_bucket:
            aws["s3"].delete_object(Bucket=bucket, Key="probe.txt")
            aws["s3"].delete_bucket(Bucket=bucket)

    assert bucket not in {item["Name"] for item in aws["s3"].list_buckets()["Buckets"]}
    assert user not in {item["UserName"] for item in aws["iam"].list_users()["Users"]}
