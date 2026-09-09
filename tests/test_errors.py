"""Envelope de erro e handlers de exceção (`app/core/errors.py`)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import (
    AppError,
    Conflict,
    ErrorCode,
    NotFound,
    register_exception_handlers,
)


class _Payload(BaseModel):
    name: str
    age: int


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/app-error")
    def _app_error() -> None:
        raise AppError("algo inválido", code="ALGO_INVALIDO")

    @app.get("/not-found")
    def _not_found() -> None:
        raise NotFound("produto não existe", code=ErrorCode.PRODUCT_NOT_FOUND)

    @app.get("/conflict")
    def _conflict() -> None:
        raise Conflict("e-mail em uso", code=ErrorCode.EMAIL_TAKEN)

    @app.post("/validate")
    def _validate(payload: _Payload) -> dict[str, str]:
        return {"ok": "sim"}

    @app.get("/boom")
    def _boom() -> None:
        raise RuntimeError("erro não previsto")

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app(), raise_server_exceptions=False)


def test_app_error_usa_status_e_code_da_excecao(client: TestClient) -> None:
    resp = client.get("/app-error")
    assert resp.status_code == 400
    assert resp.json() == {
        "error": {"code": "ALGO_INVALIDO", "message": "algo inválido"}
    }


def test_not_found_retorna_404_com_code_de_dominio(client: TestClient) -> None:
    resp = client.get("/not-found")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == ErrorCode.PRODUCT_NOT_FOUND


def test_conflict_retorna_409(client: TestClient) -> None:
    resp = client.get("/conflict")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == ErrorCode.EMAIL_TAKEN


def test_validacao_vira_422_com_fields_por_campo(client: TestClient) -> None:
    resp = client.post("/validate", json={"name": "Ana"})
    assert resp.status_code == 422
    body = resp.json()["error"]
    assert body["code"] == ErrorCode.VALIDATION_ERROR
    assert "age" in body["fields"]


def test_fields_so_aparece_em_validacao(client: TestClient) -> None:
    assert "fields" not in client.get("/app-error").json()["error"]


def test_excecao_nao_tratada_vira_500_generico(client: TestClient) -> None:
    resp = client.get("/boom")
    assert resp.status_code == 500
    body = resp.json()["error"]
    assert body["code"] == ErrorCode.INTERNAL_ERROR
    assert "erro não previsto" not in body["message"]
