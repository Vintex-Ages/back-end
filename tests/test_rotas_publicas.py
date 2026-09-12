"""Contrato de rota pública (absorve a BE-US001-1 / #75).

As rotas de descoberta respondem sem `Authorization`. O feed de produtos possui
testes próprios com banco configurado; este teste mantém a cobertura das rotas
de descoberta ainda não implementadas.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

DISCOVERY_ROUTES = [
    "/api/products/1",
    "/api/stores/1",
    "/api/styles",
]


def test_health_responde_sem_token() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_rota_inexistente_usa_o_envelope_de_erro() -> None:
    resp = client.get("/api/nao-existe")
    assert resp.status_code == 404
    body = resp.json()
    assert set(body["error"]) >= {"code", "message"}
    assert "fields" not in body["error"]


@pytest.mark.parametrize("route", DISCOVERY_ROUTES)
def test_rota_de_descoberta_responde_sem_token(route: str) -> None:
    resp = client.get(route)
    if resp.status_code == 404:
        pytest.skip(f"{route} chega com as issues #85 / #93 / #108 / #79")
    assert resp.status_code == 200
    assert "Authorization" not in resp.request.headers
