"""Opt-in ARM64 gateway probe: synthetic secrets/images, no AWS or model calls."""

from __future__ import annotations

import argparse
import base64
import json
import secrets
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from scripts.infra.deploy_staging import LLM_DIGEST

MIB = 1024 * 1024
IMAGE = f"ghcr.io/tashfeenahmed/freellmapi@sha256:{LLM_DIGEST}"
PING = (
    "node -e \"fetch('http://127.0.0.1:3001/api/ping')"
    '.then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"'
)


def docker(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=False, timeout=180
    )
    if check and result.returncode:
        raise RuntimeError(f"Docker {args[0]} failed (exit {result.returncode})")
    return result.stdout


def request(base: str, path: str, body=None, token: str = "") -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None if body is None else json.dumps(body).encode()
    req = Request(base + path, data=data, headers=headers)
    try:
        response = build_opener(ProxyHandler({})).open(req, timeout=60)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response)


def probe(memory: int) -> dict:
    name = "vintex-llm-probe-" + uuid.uuid4().hex[:10]
    report = {"limit_mib": memory, "passed": False, "native_arm64": False}
    network_created = False
    try:
        # No egress: no catalog, provider key or external inference can be used.
        docker("network", "create", "--internal", name)
        network_created = True
        with tempfile.TemporaryDirectory(prefix="vintex-llm-probe-") as folder:
            env = Path(folder) / "llm.env"
            admin = {"email": "infra@test.local", "password": secrets.token_hex(24)}
            env.write_text(
                "NODE_ENV=production\nPORT=3001\nREQUEST_BODY_LIMIT_MB=40\n"
                "FREELLMAPI_UPDATE_CHECK=off\nENCRYPTION_KEY="
                + secrets.token_hex(32)
                + "\nFREEAPI_CONFIG_JSON="
                + json.dumps({"admin": admin})
                + "\n"
            )
            env.chmod(0o600)
            docker(
                "run",
                "-d",
                "--name",
                name,
                "--platform",
                "linux/arm64",
                "--network",
                name,
                "--memory",
                f"{memory}m",
                "--memory-swap",
                f"{memory}m",
                "--cap-drop",
                "NET_RAW",
                "--security-opt",
                "no-new-privileges:true",
                "--env-file",
                str(env),
                "--health-cmd",
                PING,
                "--health-interval",
                "15s",
                "--health-timeout",
                "5s",
                "--health-start-period",
                "20s",
                "--health-retries",
                "10",
                IMAGE,
            )
            architecture = docker("info", "--format", "{{.Architecture}}").strip()
            report["native_arm64"] = architecture in ("aarch64", "arm64")
            address = json.loads(docker("inspect", name))[0]["NetworkSettings"][
                "Networks"
            ][name]["IPAddress"]
            base = f"http://{address}:3001"
            deadline = time.monotonic() + 150
            while time.monotonic() < deadline:
                state = json.loads(docker("inspect", name))[0]["State"]
                if not state["Running"]:
                    raise RuntimeError("Gateway stopped during startup")
                if state["Health"]["Status"] == "healthy":
                    break
                time.sleep(1)
            else:
                raise RuntimeError("Gateway health check timed out")
            status, login = request(base, "/api/auth/login", admin)
            assert status == 200, "Synthetic admin bootstrap failed"
            status, key = request(base, "/api/settings/api-key", token=login["token"])
            assert status == 200, "Synthetic unified key unavailable"
            # Valid tiny PNG padded to the exact supported raw image ceiling.
            png = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aP1sAAAAASUVORK5CYII="
            )
            image = (
                "data:image/png;base64,"
                + base64.b64encode(png.ljust(8 * MIB, b"\0")).decode()
            )
            body = {
                "model": "auto",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": image}}
                            for _ in range(3)
                        ],
                    }
                ],
            }
            report["payload_bytes"] = len(json.dumps(body).encode())
            for _ in range(3):
                status, _ = request(base, "/v1/chat/completions", body, key["apiKey"])
                # Parser/auth accept the request; routing has no provider.
                # This does not prove image normalization or inference works.
                assert status in (400, 503), f"Unexpected inference status {status}"
            report["inference_status_without_provider"] = status
            status, _ = request(
                base,
                "/v1/chat/completions",
                {"padding": "x" * (40 * MIB)},
                key["apiKey"],
            )
            assert status == 413, "Configured upper body ceiling was not enforced"
            assert request(base, "/api/ping")[0] == 200
            peak = int(
                docker("exec", name, "cat", "/sys/fs/cgroup/memory.peak").strip()
            )
            report["peak_mib"] = round(peak / MIB, 2)
            report["below_80_percent"] = peak < memory * MIB * 0.8
            report["passed"] = report["below_80_percent"]
    except (RuntimeError, AssertionError, OSError, ValueError) as error:
        report["error"] = type(error).__name__
        if isinstance(error, (RuntimeError, AssertionError)):
            report["detail"] = str(error)
    finally:
        inspected = docker("inspect", name, check=False)
        if inspected:
            state = json.loads(inspected)[0]["State"]
            report.update(oom_killed=state["OOMKilled"], exit_code=state["ExitCode"])
            report["healthy"] = state.get("Health", {}).get("Status") == "healthy"
            report["passed"] = bool(
                report["passed"]
                and state["Running"]
                and report["healthy"]
                and not state["OOMKilled"]
            )
        docker("rm", "-f", "-v", name, check=False)
        if network_created:
            docker("network", "rm", name, check=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-mib", nargs="+", type=int, default=[256, 384, 512])
    args = parser.parse_args()
    if any(memory not in (128, 256, 384, 512) for memory in args.memory_mib):
        parser.error("Use a bounded candidate: 128, 256, 384 or 512 MiB")
    docker("pull", "--platform", "linux/arm64", IMAGE)
    results = []
    for memory in args.memory_mib:
        result = probe(memory)
        results.append(result)
        print(json.dumps(result), flush=True)
    raise SystemExit(0 if any(item["passed"] for item in results) else 1)


if __name__ == "__main__":
    main()
