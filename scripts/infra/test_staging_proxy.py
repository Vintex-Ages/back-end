"""Exercise the actual staging Nginx config with a synthetic HTTP backend."""

import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
IMAGE = "nginx:1.28.0-alpine@sha256:30f1c0d78e0ad60901648be663a710bdadf19e4c10ac6782c235200619158284"
BACKEND = """
from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(404 if self.path == '/api/missing' else 200)
        self.end_headers()
        self.wfile.write(self.path.encode())
    def log_message(self, *args):
        pass
HTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
"""


def docker(*args: str) -> str:
    return subprocess.check_output(
        ["docker", *args], text=True, stderr=subprocess.STDOUT
    ).strip()


def request(url: str) -> tuple[int, bytes]:
    try:
        with urlopen(url, timeout=5) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def main() -> None:
    suffix = uuid4().hex[:12]
    network, api, proxy = (
        f"vintex-proxy-test-{suffix}-{name}" for name in ("net", "api", "proxy")
    )
    with tempfile.TemporaryDirectory(prefix="vintex-static-") as temporary:
        frontend = Path(temporary) / "frontend"
        frontend.mkdir(mode=0o755)
        (frontend / "index.html").write_text("synthetic-staging-SPA")
        try:
            docker("network", "create", network)
            docker(
                "run",
                "-d",
                "--name",
                api,
                "--network",
                network,
                "--network-alias",
                "api",
                "python:3.12-slim",
                "python",
                "-c",
                BACKEND,
            )
            docker(
                "run",
                "-d",
                "--name",
                proxy,
                "--network",
                network,
                "-p",
                "127.0.0.1::80",
                "-v",
                f"{ROOT / 'infra/aws/staging/nginx.conf'}:/etc/nginx/conf.d/default.conf:ro",
                "-v",
                f"{frontend}:/usr/share/nginx/html:ro",
                IMAGE,
            )
            endpoint = "http://" + docker("port", proxy, "80/tcp")
            for attempt in range(20):
                try:
                    if request(endpoint + "/health")[0] == 200:
                        break
                except OSError:
                    pass
                time.sleep(0.5)
            else:
                raise RuntimeError("Nginx did not become healthy")
            assert request(endpoint + "/catalog/items")[1] == b"synthetic-staging-SPA"
            assert request(endpoint + "/api/items")[1] == b"/api/items"
            assert request(endpoint + "/api/missing") == (404, b"/api/missing")
            with urlopen(endpoint + "/index.html") as response:
                assert response.headers["Cache-Control"] == "no-store"
            with ThreadPoolExecutor(max_workers=40) as pool:
                responses = list(
                    pool.map(lambda _: request(endpoint + "/api/items"), range(60))
                )
            assert any(status == 429 for status, _ in responses)
            print(
                "[staging-proxy] SPA, API prefix, API 404, cache and rate limit passed"
            )
        finally:
            for name in (proxy, api):
                subprocess.run(
                    ["docker", "rm", "-f", name], capture_output=True, check=False
                )
            subprocess.run(
                ["docker", "network", "rm", network], capture_output=True, check=False
            )


if __name__ == "__main__":
    main()
