"""Smoke tests do MiniStack; integração ativada por `make test-ministack`."""

import os
from uuid import uuid4

import pytest

from scripts.infra.ministack_resources import (
    API,
    CLUSTER,
    DISCOVERY_SERVICE,
    ECS_SERVICE,
    NAMESPACE,
    REPOSITORY,
    TASK_FAMILY,
    clients,
    endpoint_url,
    seed,
    verify,
)


def test_endpoint_rejects_external_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINISTACK_ENDPOINT_URL", "https://ecs.us-east-2.amazonaws.com")
    with pytest.raises(ValueError, match="MiniStack local"):
        endpoint_url()


@pytest.mark.skipif(
    os.environ.get("VINTEX_INFRA_MINISTACK_TEST") != "1",
    reason="requer o Compose vintex-infra; execute make test-ministack",
)
def test_seeded_services_and_container_alias() -> None:
    assert endpoint_url() == "http://ministack:4567"
    verify()
    aws = clients()
    assert (
        aws["ecs"].describe_clusters(clusters=[CLUSTER])["clusters"][0]["clusterName"]
        == CLUSTER
    )
    task = aws["ecs"].describe_task_definition(taskDefinition=TASK_FAMILY)[
        "taskDefinition"
    ]
    assert task["networkMode"] == "awsvpc"
    assert "FARGATE" in task["requiresCompatibilities"]
    service = aws["ecs"].describe_services(cluster=CLUSTER, services=[ECS_SERVICE])[
        "services"
    ][0]
    assert service["desiredCount"] == 0
    assert any(
        item["Name"] == NAMESPACE
        for item in aws["servicediscovery"].list_namespaces()["Namespaces"]
    )
    assert any(
        item["Name"] == DISCOVERY_SERVICE
        for item in aws["servicediscovery"].list_services()["Services"]
    )
    assert any(item["Name"] == API for item in aws["apigatewayv2"].get_apis()["Items"])
    assert (
        aws["ecr"].describe_repositories(repositoryNames=[REPOSITORY])["repositories"][
            0
        ]["repositoryName"]
        == REPOSITORY
    )


@pytest.mark.skipif(
    os.environ.get("VINTEX_INFRA_MINISTACK_TEST") != "1",
    reason="requer o Compose vintex-infra; execute make test-ministack",
)
def test_seed_is_idempotent_and_temporary_resources_are_removed() -> None:
    aws = clients()
    before = {
        "tasks": len(
            aws["ecs"].list_task_definitions(familyPrefix=TASK_FAMILY)[
                "taskDefinitionArns"
            ]
        ),
        "apis": len(aws["apigatewayv2"].get_apis()["Items"]),
    }
    seed()
    after = {
        "tasks": len(
            aws["ecs"].list_task_definitions(familyPrefix=TASK_FAMILY)[
                "taskDefinitionArns"
            ]
        ),
        "apis": len(aws["apigatewayv2"].get_apis()["Items"]),
    }
    assert after == before

    name = f"vintex-infra-test-{uuid4().hex[:12]}"
    repo_created = api_id = None
    try:
        repo_created = aws["ecr"].create_repository(repositoryName=name)["repository"]
        assert (
            aws["ecr"].describe_repositories(repositoryNames=[name])["repositories"][0][
                "repositoryName"
            ]
            == name
        )
        api_id = aws["apigatewayv2"].create_api(Name=name, ProtocolType="HTTP")["ApiId"]
        assert aws["apigatewayv2"].get_api(ApiId=api_id)["Name"] == name
    finally:
        if api_id:
            aws["apigatewayv2"].delete_api(ApiId=api_id)
        if repo_created:
            aws["ecr"].delete_repository(repositoryName=name, force=True)

    assert name not in {
        item["Name"] for item in aws["apigatewayv2"].get_apis()["Items"]
    }
    assert name not in {
        item["repositoryName"]
        for item in aws["ecr"].describe_repositories()["repositories"]
    }
