"""API HTTP, S3/SQS reais no LocalStack e worker em processo separado.

Só a resposta HTTP do provedor externo é sintética. Banco, publicação,
download da foto, análise, persistência e confirmação usam o código real.
"""

import base64
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete

from app.core.security import create_access_token
from app.database import SessionLocal, engine
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.seller import Seller
from app.models.store import Store
from app.models.user import User
from scripts.infra.localstack_resources import clients

pytestmark = pytest.mark.skipif(
    os.environ.get("VINTEX_INFRA_AI_WORKER_TEST") != "1",
    reason="requer o Compose vintex-infra; execute make test-ai-worker",
)


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.parametrize(
    "outcome", ["success", "provider_error", "provider_413", "missing_key"]
)
def test_api_queue_worker_persistence_and_redrive(outcome):
    assert engine.dialect.name == "postgresql"
    resources = clients()
    sqs = resources["sqs"]
    suffix = uuid4().hex[:12]
    queue_url = dlq_url = None
    api = None
    provider_calls = []
    media_key = None
    user_id = seller_id = store_id = None

    class ProviderHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            provider_calls.append(
                (self.path, self.headers.get("Authorization"), request)
            )
            self.send_response(
                200
                if outcome == "success"
                else 413 if outcome == "provider_413" else 503
            )
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps(
                                        {
                                            "category": {
                                                "value": "Jaqueta",
                                                "confidence": 0.9,
                                            }
                                        }
                                    )
                                }
                            }
                        ]
                    }
                ).encode()
            )

    provider = ThreadingHTTPServer(("127.0.0.1", 0), ProviderHandler)
    provider_thread = threading.Thread(target=provider.serve_forever, daemon=True)
    provider_thread.start()
    api_port = _free_port()
    internal_base = f"http://127.0.0.1:{api_port}"
    public_base = "http://browser.test:8080"
    try:
        dlq_url = sqs.create_queue(QueueName=f"vintex-worker-e2e-dlq-{suffix}")[
            "QueueUrl"
        ]
        dlq_arn = sqs.get_queue_attributes(
            QueueUrl=dlq_url, AttributeNames=["QueueArn"]
        )["Attributes"]["QueueArn"]
        queue_url = sqs.create_queue(
            QueueName=f"vintex-worker-e2e-{suffix}",
            Attributes={
                "VisibilityTimeout": "0",
                "RedrivePolicy": json.dumps(
                    {"deadLetterTargetArn": dlq_arn, "maxReceiveCount": "3"}
                ),
            },
        )["QueueUrl"]
        with SessionLocal() as db:
            user = User(
                name="Infra sintética",
                email=f"worker-{suffix}@test.local",
                password_hash="synthetic",
            )
            db.add(user)
            db.flush()
            seller = Seller(user_id=user.id, document_type="CPF", document_value=suffix)
            db.add(seller)
            db.flush()
            store = Store(seller_id=seller.id, name=f"Infra {suffix}")
            db.add(store)
            db.commit()
            user_id, seller_id, store_id = user.id, seller.id, store.id

        env = {
            **os.environ,
            "AI_ANALYSIS_QUEUE_URL": queue_url,
            "AI_WORKER_PROVIDER": "freellmapi",
            "FREELLMAPI_API_KEY": "" if outcome == "missing_key" else "synthetic-token",
            "FREELLMAPI_BASE_URL": f"http://127.0.0.1:{provider.server_port}/v1",
            "PUBLIC_BASE_URL": public_base,
            "MEDIA_INTERNAL_BASE_URL": internal_base,
        }
        api = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(api_port),
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with httpx.Client(
            base_url=internal_base, timeout=10, trust_env=False
        ) as client:
            for _ in range(100):
                try:
                    if client.get("/health").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                assert api.poll() is None, "API terminou antes do health check"
                time.sleep(0.1)
            else:
                pytest.fail("API não ficou saudável")

            headers = {"Authorization": f"Bearer {create_access_token(user_id, False)}"}
            photo = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jhZkAAAAASUVORK5CYII="
            )
            upload = client.post(
                "/api/users/me/media",
                headers=headers,
                files={"files": ("photo.png", photo, "image/png")},
            )
            assert upload.status_code == 201, upload.text
            item = upload.json()["items"][0]
            media_key = item["key"]
            assert item["url"].startswith(public_base + "/api/media/")
            created = client.post(
                "/api/users/me/products",
                headers=headers,
                json={
                    "name": "Jaqueta sintética",
                    "price": 99.90,
                    "images": [item["url"]],
                },
            )
            assert created.status_code == 201, created.text
            product_id = created.json()["id"]
            status_url = f"/api/users/me/products/{product_id}/ai-status"
            assert client.get(status_url, headers=headers).json()["status"] == "pending"

            def run_worker():
                # Acelera só os tempos de redelivery da fila privada deste teste.
                subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        "from app.workers import ai_analysis as w; w.PROCESSING_VISIBILITY_SECONDS=0; w.LONG_POLL_SECONDS=1; w.poll_once()",
                    ],
                    env=env,
                    check=True,
                    timeout=30,
                    capture_output=True,
                )

            run_worker()
            status = client.get(status_url, headers=headers).json()
            with SessionLocal() as db:
                product = db.get(Product, product_id)
                assert product is not None and product.status == "rascunho"
                assert product.ai_status == status["status"]
            if outcome == "success":
                assert status["status"] == "done"
                assert status["suggestions"]["category"]["value"] == "Jaqueta"
                # Entrega duplicada não repete a chamada ao provedor.
                sqs.send_message(
                    QueueUrl=queue_url,
                    MessageBody=json.dumps(
                        {"product_id": product_id, "image_urls": [item["url"]]}
                    ),
                )
                run_worker()
                assert len(provider_calls) == 1
                path, authorization, request = provider_calls[0]
                assert path == "/v1/chat/completions"
                assert authorization == "Bearer synthetic-token"
                assert (
                    request["messages"][0]["content"][1]["image_url"]["url"]
                    == "data:image/png;base64," + base64.b64encode(photo).decode()
                )
                assert not sqs.receive_message(
                    QueueUrl=queue_url, WaitTimeSeconds=1
                ).get("Messages")
                assert not sqs.receive_message(QueueUrl=dlq_url, WaitTimeSeconds=1).get(
                    "Messages"
                )
            else:
                assert status["status"] == "failed" and status["error"]
                for _ in range(3):
                    run_worker()
                dead = sqs.receive_message(QueueUrl=dlq_url, WaitTimeSeconds=2).get(
                    "Messages", []
                )
                assert len(dead) == 1
                assert json.loads(dead[0]["Body"])["product_id"] == product_id
                assert len(provider_calls) == (0 if outcome == "missing_key" else 3)
                assert client.get("/health").status_code == 200
                manual = client.post(
                    "/api/users/me/products",
                    headers=headers,
                    json={"name": "Manual sem IA", "price": 20},
                )
                assert manual.status_code == 201
    finally:
        if api is not None:
            api.terminate()
            api.wait(timeout=10)
        provider.shutdown()
        provider.server_close()
        provider_thread.join(timeout=5)
        if queue_url:
            sqs.delete_queue(QueueUrl=queue_url)
        if dlq_url:
            sqs.delete_queue(QueueUrl=dlq_url)
        if media_key:
            resources["s3"].delete_object(Bucket="vintex-local-media", Key=media_key)
        if store_id is not None:
            with SessionLocal() as db:
                ids = db.query(Product.id).filter(Product.store_id == store_id)
                db.execute(delete(ProductImage).where(ProductImage.product_id.in_(ids)))
                db.execute(delete(Product).where(Product.store_id == store_id))
                db.execute(delete(Store).where(Store.id == store_id))
                db.execute(delete(Seller).where(Seller.id == seller_id))
                db.execute(delete(User).where(User.id == user_id))
                db.commit()
