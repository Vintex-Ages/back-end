"""Recursos sintéticos de controle usados pelos smoke tests do MiniStack."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import dotenv_values

from scripts.infra.localstack_resources import REGION

ROOT = Path(__file__).resolve().parents[2]
CLUSTER = "vintex-infra-smoke"
TASK_FAMILY = "vintex-infra-smoke"
ECS_SERVICE = "vintex-infra-smoke"
NAMESPACE = "vintex-infra-smoke"
DISCOVERY_SERVICE = "vintex-infra-smoke"
API = "vintex-infra-smoke"
REPOSITORY = "vintex-infra-smoke"
VPC_TAG = "vintex-infra-smoke"
VPC_CIDR = "10.222.0.0/16"
SUBNET_CIDR = "10.222.1.0/24"


def endpoint_url() -> str:
    """Aceita apenas a porta HTTP local ou o alias da rede Compose."""
    env_file = dotenv_values(ROOT / "infra/vintex-infra/.env")
    port = (
        os.environ.get("MINISTACK_HOST_PORT")
        or env_file.get("MINISTACK_HOST_PORT")
        or "4567"
    )
    endpoint = os.environ.get("MINISTACK_ENDPOINT_URL") or f"http://127.0.0.1:{port}"
    parsed = urlparse(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "ministack",
    }:
        raise ValueError("MINISTACK_ENDPOINT_URL deve apontar para o MiniStack local")
    if not parsed.port or parsed.path not in ("", "/"):
        raise ValueError("MINISTACK_ENDPOINT_URL precisa ter porta e nenhuma rota")
    return endpoint


def clients() -> dict[str, object]:
    """Cria clientes AWS com credenciais fictícias e endpoint explícito."""
    endpoint = endpoint_url()
    config = Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 2})
    return {
        service: boto3.client(
            service,
            endpoint_url=endpoint,
            region_name=REGION,
            aws_access_key_id="test",
            aws_secret_access_key="test",
            config=config,
        )
        for service in ("ec2", "ecs", "servicediscovery", "apigatewayv2", "ecr")
    }


def _named(items: list[dict], name: str, key: str = "Name") -> dict | None:
    return next((item for item in items if item.get(key) == name), None)


def _network(ec2: object, create: bool = True) -> tuple[str, str, str]:
    """Consulta ou prepara metadados sintéticos para o serviço Fargate local."""
    vpc = next(
        (
            item
            for item in ec2.describe_vpcs()["Vpcs"]
            if {"Key": "Name", "Value": VPC_TAG} in item.get("Tags", [])
        ),
        None,
    )
    if vpc is None:
        if not create:
            raise AssertionError("VPC sintética ausente")
        vpc = ec2.create_vpc(CidrBlock=VPC_CIDR)["Vpc"]
        ec2.create_tags(
            Resources=[vpc["VpcId"]], Tags=[{"Key": "Name", "Value": VPC_TAG}]
        )
    vpc_id = vpc["VpcId"]

    subnet = next(
        (
            item
            for item in ec2.describe_subnets()["Subnets"]
            if item["VpcId"] == vpc_id and item["CidrBlock"] == SUBNET_CIDR
        ),
        None,
    )
    if subnet is None:
        if not create:
            raise AssertionError("subnet sintética ausente")
        subnet = ec2.create_subnet(VpcId=vpc_id, CidrBlock=SUBNET_CIDR)["Subnet"]

    group = next(
        (
            item
            for item in ec2.describe_security_groups()["SecurityGroups"]
            if item["VpcId"] == vpc_id and item["GroupName"] == VPC_TAG
        ),
        None,
    )
    if group is None:
        if not create:
            raise AssertionError("grupo de segurança sintético ausente")
        group_id = ec2.create_security_group(
            GroupName=VPC_TAG,
            Description="Rede sintetica para smoke test MiniStack",
            VpcId=vpc_id,
        )["GroupId"]
    else:
        group_id = group["GroupId"]
    return vpc_id, subnet["SubnetId"], group_id


def _namespace(sd: object, create: bool = True) -> dict:
    namespace = _named(sd.list_namespaces()["Namespaces"], NAMESPACE)
    if namespace is None:
        if not create:
            raise AssertionError("namespace Cloud Map ausente")
        operation_id = sd.create_http_namespace(Name=NAMESPACE)["OperationId"]
        namespace_id = sd.get_operation(OperationId=operation_id)["Operation"][
            "Targets"
        ]["NAMESPACE"]
        namespace = sd.get_namespace(Id=namespace_id)["Namespace"]
    return namespace


def _task_definition(ecs: object) -> str:
    definitions = [
        arn
        for arn in ecs.list_task_definitions(familyPrefix=TASK_FAMILY)[
            "taskDefinitionArns"
        ]
        if arn.split("/")[-1].split(":")[0] == TASK_FAMILY
    ]
    if definitions:
        return definitions[-1]
    return ecs.register_task_definition(
        family=TASK_FAMILY,
        networkMode="awsvpc",
        requiresCompatibilities=["FARGATE"],
        cpu="256",
        memory="512",
        containerDefinitions=[
            {
                "name": "probe",
                "image": "public.ecr.aws/docker/library/busybox:1.36",
                "essential": True,
            }
        ],
    )["taskDefinition"]["taskDefinitionArn"]


def seed() -> None:
    """Cria recursos de controle idempotentes, sem iniciar tarefas reais."""
    aws = clients()
    _, subnet_id, group_id = _network(aws["ec2"])

    ecs = aws["ecs"]
    clusters = ecs.describe_clusters(clusters=[CLUSTER])["clusters"]
    if not clusters or clusters[0]["status"] != "ACTIVE":
        ecs.create_cluster(clusterName=CLUSTER)
    task_arn = _task_definition(ecs)
    services = ecs.describe_services(cluster=CLUSTER, services=[ECS_SERVICE])[
        "services"
    ]
    if not services or services[0]["status"] != "ACTIVE":
        ecs.create_service(
            cluster=CLUSTER,
            serviceName=ECS_SERVICE,
            taskDefinition=task_arn,
            desiredCount=0,
            launchType="FARGATE",
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": [subnet_id],
                    "securityGroups": [group_id],
                    "assignPublicIp": "DISABLED",
                }
            },
        )

    sd = aws["servicediscovery"]
    namespace = _namespace(sd)
    services = sd.list_services(
        Filters=[{"Name": "NAMESPACE_ID", "Values": [namespace["Id"]]}]
    )["Services"]
    if _named(services, DISCOVERY_SERVICE) is None:
        sd.create_service(Name=DISCOVERY_SERVICE, NamespaceId=namespace["Id"])

    api = aws["apigatewayv2"]
    if _named(api.get_apis()["Items"], API) is None:
        api.create_api(Name=API, ProtocolType="HTTP")

    ecr = aws["ecr"]
    try:
        ecr.describe_repositories(repositoryNames=[REPOSITORY])
    except ClientError as error:
        if error.response["Error"]["Code"] != "RepositoryNotFoundException":
            raise
        ecr.create_repository(repositoryName=REPOSITORY)
    print("[ministack] ECS/Fargate, Cloud Map, API HTTP e ECR prontos")


def verify() -> None:
    """Confirma o provisionamento via chamadas AWS a partir da rede Compose."""
    aws = clients()
    _, subnet_id, group_id = _network(aws["ec2"], create=False)
    ecs = aws["ecs"]
    assert (
        ecs.describe_clusters(clusters=[CLUSTER])["clusters"][0]["status"] == "ACTIVE"
    )
    task = ecs.describe_task_definition(taskDefinition=TASK_FAMILY)["taskDefinition"]
    assert "FARGATE" in task["requiresCompatibilities"]
    service = ecs.describe_services(cluster=CLUSTER, services=[ECS_SERVICE])[
        "services"
    ][0]
    assert service["launchType"] == "FARGATE" and service["desiredCount"] == 0

    sd = aws["servicediscovery"]
    namespace = _namespace(sd, create=False)
    services = sd.list_services(
        Filters=[{"Name": "NAMESPACE_ID", "Values": [namespace["Id"]]}]
    )["Services"]
    assert _named(services, DISCOVERY_SERVICE) is not None

    api = aws["apigatewayv2"]
    assert _named(api.get_apis()["Items"], API) is not None
    assert (
        subnet_id in service["networkConfiguration"]["awsvpcConfiguration"]["subnets"]
    )
    assert (
        group_id
        in service["networkConfiguration"]["awsvpcConfiguration"]["securityGroups"]
    )
    aws["ecr"].describe_repositories(repositoryNames=[REPOSITORY])
    print(f"[ministack] recursos acessíveis por {endpoint_url()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seed", "verify"))
    args = parser.parse_args()
    {"seed": seed, "verify": verify}[args.action]()
