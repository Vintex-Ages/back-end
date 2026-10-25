"""Validate the actual rendered AWS Compose; no Docker daemon or AWS required."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(
    shutil.which("docker") is None, reason="Docker Compose CLI required"
)
def test_rendered_compose_isolated_and_pinned(tmp_path):
    for name in ("api", "worker", "db", "llm"):
        (tmp_path / f"{name}.env").write_text("SYNTHETIC_TEST=1\n")
    env = dict(os.environ)
    env.update(
        {
            "RELEASE_SHA": "a" * 40,
            "BACKEND_IMAGE": "123456789012.dkr.ecr.us-east-2.amazonaws.com/vintex-backend:"
            + "a" * 40,
            "FREELLMAPI_IMAGE": "123456789012.dkr.ecr.us-east-2.amazonaws.com/freellmapi@sha256:"
            + "b" * 64,
            "SECRETS_DIR": str(tmp_path),
            "FRONTEND_DIR": str(tmp_path),
        }
    )
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            "/dev/null",
            "-f",
            str(ROOT / "infra/aws/staging/compose.yml"),
            "config",
            "--format",
            "json",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    config = json.loads(result.stdout)
    services = config["services"]
    assert set(services) == {"proxy", "api", "worker", "freellmapi", "db"}
    assert services["api"]["image"] == services["worker"]["image"]
    assert "pg16@sha256:" in services["db"]["image"]
    assert "nginx:1.28.0-alpine@sha256:" in services["proxy"]["image"]
    for name, service in services.items():
        assert service["platform"] == "linux/arm64"
        assert "NET_RAW" in service["cap_drop"]
        assert service["healthcheck"]["test"]
        assert (
            service["logging"]["options"]["awslogs-group"] == f"/vintex/staging/{name}"
        )
        for port in service.get("ports", []):
            assert port["host_ip"] == "127.0.0.1"
    assert services["api"]["networks"].keys() == {"app"}
    assert services["freellmapi"]["networks"].keys() == {"llm"}
    assert services["worker"]["networks"].keys() == {"app", "llm"}
    assert all(
        "gw_priority" not in network
        for network in services["worker"]["networks"].values()
    )
    assert "ports" not in services["db"] and "ports" not in services["api"]
    limits_mib = {"proxy": 64, "api": 384, "worker": 256, "freellmapi": 512, "db": 448}
    for name, limit in limits_mib.items():
        assert int(services[name]["mem_limit"]) == limit * 1024 * 1024
    assert 2048 - sum(limits_mib.values()) == 384  # Nominal host reserve, not measured.
    assert all("build" not in s and not s.get("privileged") for s in services.values())
