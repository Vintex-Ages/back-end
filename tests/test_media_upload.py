"""Upload e leitura de mídia (VE-04, back-end#73).

S3 dublado por um cliente em memória: o contrato do `MediaStorage` com o boto3
já está coberto em `test_media_storage.py`, e o que interessa aqui é a rota, a
validação e a URL que sai.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.controllers.media_controller import ArquivoRecebido, MediaController
from app.core.errors import NotFound, ValidationError
from app.core.security import require_auth
from app.main import app
from app.models.user import User
from app.services import media_rules
from app.services.media_storage import MediaStorage
from app.views.media_routes import get_controller

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64


class _S3EmMemoria:
    def __init__(self) -> None:
        self.objetos: dict[str, tuple[bytes, str]] = {}

    def put_object(
        self, Bucket: str, Key: str, Body: bytes, ContentType: str
    ) -> None:  # noqa: N803
        self.objetos[Key] = (Body, ContentType)

    def get_object(self, Bucket: str, Key: str):  # noqa: N803, ANN201
        if Key not in self.objetos:
            raise KeyError(Key)
        corpo, content_type = self.objetos[Key]

        class _Body:
            @staticmethod
            def read() -> bytes:
                return corpo

        return {"Body": _Body(), "ContentType": content_type}


@pytest.fixture
def storage() -> MediaStorage:
    return MediaStorage("bucket-de-teste", _S3EmMemoria())


@pytest.fixture
def controller(storage: MediaStorage) -> MediaController:
    return MediaController(storage, "http://localhost:8000")


@pytest.fixture
def client(controller: MediaController):  # noqa: ANN201
    app.dependency_overrides[require_auth] = lambda: User(id=1, email="v@x.test")
    app.dependency_overrides[get_controller] = lambda: controller
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _arquivo(
    nome: str = "frente.jpg", tipo: str = "image/jpeg", conteudo: bytes = JPEG
):  # noqa: ANN202
    return ArquivoRecebido(nome=nome, content_type=tipo, conteudo=conteudo)


# --- controller ---


def test_upload_devolve_url_absoluta_que_o_servidor_alcanca(
    controller: MediaController,
) -> None:
    """A URL precisa ser absoluta: é o servidor que baixa a foto para a IA."""
    resposta = controller.upload("photo", [_arquivo()])

    item = resposta.items[0]
    assert item.url.startswith("http://localhost:8000/api/media/")
    assert item.url.endswith(item.key)
    assert item.content_type == "image/jpeg"
    assert item.size == len(JPEG)


def test_base_com_barra_no_fim_nao_gera_url_com_barra_dupla(
    storage: MediaStorage,
) -> None:
    c = MediaController(storage, "http://localhost:8000/")
    url = c.upload("photo", [_arquivo()]).items[0].url
    assert "//api" not in url


def test_le_de_volta_o_que_subiu_com_o_tipo_gravado(
    controller: MediaController,
) -> None:
    key = controller.upload("photo", [_arquivo()]).items[0].key

    conteudo, content_type = controller.read_publico(key)

    assert conteudo == JPEG
    assert content_type == "image/jpeg"


def test_recusa_tipo_fora_da_lista(controller: MediaController) -> None:
    with pytest.raises(ValidationError, match="não aceito"):
        controller.upload("photo", [_arquivo(nome="a.pdf", tipo="application/pdf")])


def test_aceita_tipo_com_charset_no_header(controller: MediaController) -> None:
    resposta = controller.upload("photo", [_arquivo(tipo="image/jpeg; charset=binary")])
    assert resposta.items[0].content_type == "image/jpeg"


def test_recusa_arquivo_vazio(controller: MediaController) -> None:
    with pytest.raises(ValidationError, match="vazio"):
        controller.upload("photo", [_arquivo(conteudo=b"")])


def test_recusa_arquivo_maior_que_o_limite(controller: MediaController) -> None:
    grande = b"0" * (media_rules.MAX_BYTES_PER_FILE + 1)
    with pytest.raises(ValidationError, match="por arquivo"):
        controller.upload("photo", [_arquivo(conteudo=grande)])


def test_recusa_soma_dos_arquivos_acima_do_limite(controller: MediaController) -> None:
    quase = b"0" * (media_rules.MAX_BYTES_PER_FILE - 1)
    arquivos = [_arquivo(nome=f"{i}.jpg", conteudo=quase) for i in range(4)]
    with pytest.raises(ValidationError, match="somando"):
        controller.upload("photo", arquivos)


def test_recusa_mais_arquivos_que_o_limite(controller: MediaController) -> None:
    arquivos = [
        _arquivo(nome=f"{i}.jpg") for i in range(media_rules.MAX_FILES_PER_REQUEST + 1)
    ]
    with pytest.raises(ValidationError, match="No máximo"):
        controller.upload("photo", arquivos)


def test_recusa_envio_sem_arquivo(controller: MediaController) -> None:
    with pytest.raises(ValidationError, match="ao menos um"):
        controller.upload("photo", [])


def test_nada_sobe_quando_um_dos_arquivos_e_invalido(
    controller: MediaController, storage: MediaStorage
) -> None:
    """Validar tudo antes de subir: metade no bucket seria objeto órfão."""
    with pytest.raises(ValidationError):
        controller.upload(
            "photo", [_arquivo(), _arquivo(nome="b.pdf", tipo="application/pdf")]
        )

    assert storage.client.objetos == {}


def test_comprovante_de_pagamento_nao_e_legivel_pela_rota_publica(
    controller: MediaController,
) -> None:
    """Chave sorteada não é controle de acesso (RN de pagamento, PIX)."""
    key = controller.upload("receipt", [_arquivo()]).items[0].key

    with pytest.raises(NotFound):
        controller.read_publico(key)


def test_chave_com_salto_de_diretorio_e_recusada_pelo_prefixo(
    controller: MediaController, storage: MediaStorage
) -> None:
    """Hoje o S3 já barraria (chave é string opaca); a regra é nossa de propósito."""
    key = controller.upload("receipt", [_arquivo()]).items[0].key

    with pytest.raises(NotFound):
        controller.read_publico(f"products/photos/../../{key}")

    with pytest.raises(NotFound):
        controller.read_publico("/products/photos/qualquer")


def test_chave_inexistente_responde_nao_encontrado(
    controller: MediaController,
) -> None:
    with pytest.raises(NotFound):
        controller.read_publico("products/photos/nao-existe")


# --- rota ---


def test_rota_sobe_e_serve_a_foto(client) -> None:  # noqa: ANN001
    r = client.post(
        "/api/users/me/media",
        files=[("files", ("frente.jpg", JPEG, "image/jpeg"))],
    )
    assert r.status_code == 201, r.text

    corpo = r.json()
    assert corpo["kind"] == "photo"
    url = corpo["items"][0]["url"]

    servida = client.get(url.replace("http://localhost:8000", ""))
    assert servida.status_code == 200
    assert servida.content == JPEG
    assert servida.headers["content-type"] == "image/jpeg"


def test_rota_de_leitura_manda_nosniff(
    client, controller: MediaController
) -> None:  # noqa: ANN001
    """O tipo vem do que o cliente declarou; sem `nosniff` o navegador pode
    farejar os bytes e renderizar como HTML."""
    key = controller.upload("photo", [_arquivo()]).items[0].key

    r = client.get(f"/api/media/{key}")

    assert r.headers["x-content-type-options"] == "nosniff"


def test_rota_recusa_pdf_com_422_e_envelope_de_erro(client) -> None:  # noqa: ANN001
    r = client.post(
        "/api/users/me/media",
        files=[("files", ("doc.pdf", b"%PDF-1.4", "application/pdf"))],
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_rota_de_leitura_nao_exige_login(
    client, controller: MediaController
) -> None:  # noqa: ANN001
    """Foto de peça anunciada é pública, e é assim que a IA a baixa."""
    key = controller.upload("photo", [_arquivo()]).items[0].key
    app.dependency_overrides.pop(require_auth, None)

    r = client.get(f"/api/media/{key}")

    assert r.status_code == 200


def test_upload_exige_login() -> None:
    """Sem `require_auth` sobreposto: a rota responde 401."""
    app.dependency_overrides.clear()
    with TestClient(app) as c:
        r = c.post(
            "/api/users/me/media",
            files=[("files", ("frente.jpg", JPEG, "image/jpeg"))],
        )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "AUTH_REQUIRED"
