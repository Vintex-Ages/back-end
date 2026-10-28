"""Consertos da auditoria de 28/09 (back-end#220).

Quatro coisas, todas medidas contra o app rodando antes de consertar:

1. `GOOGLE_EMBEDDING_MODEL` nao aceitava lista, e era o primeiro critério da
   `#209`. Cada mensagem da conversa com a Vintex chama `embed()` para
   vetorizar a pergunta, entao um 503 aqui derruba a conversa e a busca por
   similaridade inteiras. A analise de foto ja estava protegida pelo `#210`.
2. `kind=logo` nao existia, entao a logo da loja teria que subir como
   `kind=photo` e morar em `products/photos/`, junto das fotos de peca.
3. `url` de comprovante vinha absoluta, e a rota de leitura recusa o prefixo:
   201 no upload e 404 na leitura. A API entregava endereco que ela nega.
4. `MEDIA_BUCKET` ausente levantava `ValueError` dentro da dependency, e toda
   requisicao virava 500 -- inclusive a leitura publica de foto, que e o
   caminho do feed.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.controllers.media_controller import MediaController
from app.core.errors import ValidationError
from app.core.security import require_auth
from app.main import app
from app.models.user import User
from app.services import media_rules
from app.services.ai import google as mod
from app.services.ai.base import AIProviderError
from app.services.media_storage import MEDIA_PREFIXES, MediaKind, MediaStorage
from app.views.media_routes import get_controller

PNG = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]) + b"0" * 64


# --------------------------------------------------------- 1. fallback do embed
class _Erro(Exception):
    def __init__(self, code: int, mensagem: str) -> None:
        super().__init__(mensagem)
        self.code = code


class _Modelos:
    """Dubla `client.models`, respondendo por modelo."""

    def __init__(self, respostas: dict[str, Any]) -> None:
        self.respostas = respostas
        self.chamados: list[str] = []

    def embed_content(self, *, model: str, **_: Any) -> Any:  # noqa: ANN401
        self.chamados.append(model)
        r = self.respostas[model]
        if isinstance(r, Exception):
            raise r
        return r


class _Vetores:
    def __init__(self, quantos: int) -> None:
        self.embeddings = [
            type("E", (), {"values": [0.0] * 768})() for _ in range(quantos)
        ]


def _provider(monkeypatch, modelos: str, respostas: dict[str, Any]) -> tuple:
    monkeypatch.setattr(settings, "GOOGLE_EMBEDDING_MODEL", modelos)
    monkeypatch.setattr(settings, "GOOGLE_API_KEY", "chave-de-teste")
    p = mod.GoogleAIProvider()
    duble = _Modelos(respostas)
    p._client = type("C", (), {"models": duble})()
    return p, duble


def test_embedding_nao_tem_fallback_de_modelo(monkeypatch) -> None:
    """Um 503 no embedding falha, e nao tenta outro modelo (back-end#227).

    O `#224` tinha implementado o fallback, e foi revertido: `find_similar` nao
    filtra por `embedding_model`, entao o vetor da pergunta vindo de um modelo
    e os do catalogo de outro produziriam distancia entre espacos vetoriais
    diferentes -- ruido com cara de resultado. Um 503 e melhor: falha alto e o
    front mostra "indisponivel".
    """
    p, duble = _provider(
        monkeypatch,
        "gemini-embedding-2",
        {"gemini-embedding-2": _Erro(503, "UNAVAILABLE. high demand")},
    )

    with pytest.raises(AIProviderError, match="Falha ao gerar embedding"):
        p.embed(["camiseta preta"])

    assert duble.chamados == ["gemini-embedding-2"]


def test_embedding_nao_aceita_lista_de_modelos(monkeypatch) -> None:
    """Lista aqui seria armadilha: o `backfill_embeddings.py` le esta variavel
    crua para gravar em `Product.embedding_model` (`String(60)`) e para decidir
    o que reprocessar. Com lista, gravaria a lista inteira."""
    p, duble = _provider(monkeypatch, "a,b", {"a,b": _Vetores(1)})

    p.embed(["camiseta"])

    # O nome vai inteiro para o SDK, sem ser partido: quem configurar lista
    # recebe 404 do provedor, que e melhor que fallback silencioso.
    assert duble.chamados == ["a,b"]


def test_embedding_funciona_com_um_nome_so(monkeypatch) -> None:
    p, duble = _provider(
        monkeypatch, "gemini-embedding-2", {"gemini-embedding-2": _Vetores(2)}
    )

    assert p.embed(["a", "b"]) == [[0.0] * 768, [0.0] * 768]
    assert duble.chamados == ["gemini-embedding-2"]


def test_lista_de_visao_vazia_diz_o_que_esta_errado(monkeypatch) -> None:
    """Antes, lista vazia caia no `raise` do fim com `ultimo = None` e produzia
    "Falha ao analisar as fotos: None", que nao diz nada."""
    monkeypatch.setattr(settings, "GOOGLE_VISION_MODEL", "  ,  ")
    monkeypatch.setattr(settings, "GOOGLE_API_KEY", "chave-de-teste")
    p = mod.GoogleAIProvider()
    p._client = type("C", (), {"models": _Modelos({})})()

    with pytest.raises(AIProviderError, match="vazio"):
        p._gerar_com_fallback([])


# ------------------------------------------------------------- 2. kind de logo
def test_logo_tem_prefixo_proprio() -> None:
    """Sem isto a logo do brecho moraria em `products/photos/`, e limpeza de
    foto de peca apagada levaria logo junto."""
    assert MEDIA_PREFIXES["logo"] == "stores/logos/"
    assert MEDIA_PREFIXES["logo"] != MEDIA_PREFIXES["photo"]


def test_logo_aceita_os_mesmos_formatos_de_foto_e_e_publica() -> None:
    assert media_rules.validar_tipo("logo", "image/png") == "image/png"
    assert "logo" in media_rules.PUBLIC_KINDS


def test_logo_recusa_video() -> None:
    with pytest.raises(ValidationError):
        media_rules.validar_tipo("logo", "video/mp4")


# ----------------------------------------------- 3. url so para tipo publico
# Mesmo padrao do `test_media_upload.py`: S3 em memoria, porque o que interessa
# aqui e a resposta da rota, nao o contrato com o boto3.
class _S3EmMemoria:
    def __init__(self) -> None:
        self.objetos: dict[str, tuple[bytes, str]] = {}

    def put_object(self, Bucket, Key, Body, ContentType) -> None:  # noqa: N803
        self.objetos[Key] = (Body, ContentType)

    def get_object(self, Bucket, Key):  # noqa: N803, ANN201
        if Key not in self.objetos:
            raise KeyError(Key)
        corpo, tipo = self.objetos[Key]
        return {
            "Body": type("B", (), {"read": staticmethod(lambda: corpo)})(),
            "ContentType": tipo,
        }


@pytest.fixture
def midia():  # noqa: ANN201
    controller = MediaController(
        MediaStorage("bucket-de-teste", _S3EmMemoria()), "http://localhost:8000"
    )
    app.dependency_overrides[require_auth] = lambda: User(id=1, email="v@x.test")
    app.dependency_overrides[get_controller] = lambda: controller
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _subir(c: TestClient, kind: MediaKind) -> dict:
    r = c.post(
        "/api/users/me/media",
        data={"kind": kind},
        files={"files": ("a.png", PNG, "image/png")},
    )
    assert r.status_code == 201, r.text
    return r.json()["items"][0]


def test_comprovante_nao_recebe_url(midia: TestClient) -> None:
    item = _subir(midia, "receipt")

    assert item["url"] is None, "a rota de leitura recusa este prefixo: url seria 404"
    assert item["key"].startswith("payments/receipts/")


@pytest.mark.parametrize("kind", ["photo", "logo"])
def test_tipo_publico_recebe_url_que_a_leitura_aceita(
    midia: TestClient, kind: MediaKind
) -> None:
    item = _subir(midia, kind)

    assert item["url"] is not None
    assert midia.get(f"/api/media/{item['key']}").status_code == 200


# ------------------------------------------- 4. MEDIA_BUCKET ausente vira 503
def test_falha_de_configuracao_de_midia_nao_sai_rotulada_como_IA(monkeypatch) -> None:
    """`ServiceUnavailable` tinha `AI_UNAVAILABLE` como default da classe, e a
    rota de midia levantava sem `code=` -- falha de storage respondia com rotulo
    da camada de IA (back-end#227). O front despacha pelo status, entao nao
    mudava comportamento; mudava o diagnostico de quem le o payload."""
    monkeypatch.setattr(settings, "MEDIA_BUCKET", None)
    app.dependency_overrides[require_auth] = lambda: User(id=1, email="v@x.test")
    try:
        with TestClient(app) as c:
            r = c.get("/api/media/products/photos/qualquer")
            assert r.status_code == 503, r.text
            assert r.json()["error"]["code"] == "SERVICE_UNAVAILABLE", r.text
    finally:
        app.dependency_overrides.clear()


def test_a_camada_de_IA_continua_com_o_proprio_codigo(monkeypatch) -> None:
    """Quem e a camada de IA passa `AI_UNAVAILABLE` explicitamente, para o
    `#268` do front continuar distinguindo 'provedor fora' de 'foto ruim'."""
    from app.core.errors import ErrorCode, ServiceUnavailable

    erro = ServiceUnavailable("x", code=ErrorCode.AI_UNAVAILABLE)
    assert erro.code == "AI_UNAVAILABLE"
    assert ServiceUnavailable("y").code == "SERVICE_UNAVAILABLE"


def test_sem_bucket_configurado_responde_503_e_nao_500(monkeypatch) -> None:
    """Falta de configuracao e indisponibilidade declarada. E nao pode derrubar
    a leitura publica de foto, que e o caminho do feed.

    Sem override do `get_controller`: e justamente ele que levantava o
    `ValueError` dentro da dependency.
    """
    monkeypatch.setattr(settings, "MEDIA_BUCKET", None)
    app.dependency_overrides[require_auth] = lambda: User(id=1, email="v@x.test")
    try:
        with TestClient(app) as c:
            r = c.post(
                "/api/users/me/media",
                data={"kind": "photo"},
                files={"files": ("a.png", PNG, "image/png")},
            )
            assert r.status_code == 503, r.text

            leitura = c.get("/api/media/products/photos/qualquer")
            assert leitura.status_code == 503, leitura.text
    finally:
        app.dependency_overrides.clear()
