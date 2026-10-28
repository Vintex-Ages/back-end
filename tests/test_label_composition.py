"""Etiqueta e composição da peça (BE-US015-1, back-end#257)."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

import pytest

from app.controllers import assistant_controller
from app.controllers.media_controller import ArquivoRecebido, MediaController
from app.core.errors import ValidationError
from app.models.address import Address
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.seller import Seller
from app.models.store import Store
from app.models.user import User
from app.services import media_rules
from app.services.ai.analysis_prompt import ANALYZE_IMAGE_PROMPT
from app.services.ai.base import AIProvider, ImageAnalysisResult, SuggestedField
from app.services.media_storage import MediaStorage
from app.services.product_embedding import texto_da_peca

ETIQUETA = "http://localhost:8000/api/media/products/labels/abc123"
FOTO = "http://localhost:8000/api/media/products/photos/def456"
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64


class _ProviderDaEtiqueta(AIProvider):
    """Lê a composição quando a etiqueta está entre as fotos, e só então."""

    def __init__(self) -> None:
        self.received_urls: list[str] | None = None

    def analyze_image(self, image_urls: Sequence[str]) -> ImageAnalysisResult:
        self.received_urls = list(image_urls)
        if ETIQUETA not in image_urls:
            return ImageAnalysisResult(
                category=SuggestedField(value="Roupas", confidence=0.9)
            )
        return ImageAnalysisResult(
            category=SuggestedField(value="Roupas", confidence=0.9),
            brand=SuggestedField(value="Zara", confidence=0.8),
            composition=SuggestedField(value="100% algodão", confidence=0.85),
        )

    async def stream_interpret_search(self, query, history=()):  # noqa: ANN001, ANN201
        raise NotImplementedError
        yield  # pragma: no cover

    def embed(self, texts):  # noqa: ANN001, ANN201
        raise NotImplementedError


def _vendedora(db_session, nome: str = "Brecho Etiqueta") -> tuple[User, Store]:
    user = User(
        name=nome,
        email=f"{nome.lower().replace(' ', '.')}@test.local",
        password_hash="x",
    )
    store = Store(
        name=nome,
        seller=Seller(user=user, document_type="CPF", document_value="12345678901"),
        address=Address(
            street="Rua X", number="1", city="Porto Alegre", state="RS", zip_code="9"
        ),
    )
    db_session.add(store)
    db_session.commit()
    db_session.refresh(user)
    return user, store


def _sessao(client) -> dict[str, str]:
    resposta = client.post(
        "/api/auth/register",
        json={
            "name": "Vendedora",
            "email": "etiqueta@example.com",
            "password": "Senha123",
        },
    )
    return {"Authorization": f"Bearer {resposta.json()['access_token']}"}


# --- a foto da etiqueta na mídia ---


class _S3EmMemoria:
    def __init__(self) -> None:
        self.objetos: dict[str, tuple[bytes, str]] = {}

    def put_object(self, Bucket, Key, Body, ContentType):  # noqa: ANN001, N803
        self.objetos[Key] = (Body, ContentType)

    def get_object(self, Bucket, Key):  # noqa: ANN001, ANN201, N803
        corpo, content_type = self.objetos[Key]

        class _Body:
            @staticmethod
            def read() -> bytes:
                return corpo

        return {"Body": _Body(), "ContentType": content_type}


def test_etiqueta_sobe_com_prefixo_proprio_e_a_ia_consegue_baixar() -> None:
    """Prefixo próprio separa a etiqueta da galeria; a URL pública é por onde
    o servidor baixa a foto para a análise."""
    controller = MediaController(
        MediaStorage("bucket", _S3EmMemoria()), "http://localhost:8000"
    )

    item = controller.upload(
        "label", [ArquivoRecebido("etiqueta.jpg", "image/jpeg", JPEG)]
    ).items[0]

    assert item.key.startswith("products/labels/")
    assert item.url == f"http://localhost:8000/api/media/{item.key}"
    assert controller.read_publico(item.key) == (JPEG, "image/jpeg")
    assert media_rules.e_foto_de_etiqueta(item.url)


def test_etiqueta_recusa_o_que_nao_e_foto() -> None:
    controller = MediaController(
        MediaStorage("bucket", _S3EmMemoria()), "http://localhost:8000"
    )

    with pytest.raises(ValidationError, match="Tipo de arquivo não aceito"):
        controller.upload(
            "label", [ArquivoRecebido("etiqueta.pdf", "application/pdf", JPEG)]
        )


@pytest.mark.parametrize(
    ("url", "esperado"),
    [
        (ETIQUETA, True),
        ("https://api.vintex.test/api/media/products%2Flabels%2Fabc", True),
        (FOTO, False),
        ("https://cdn.test/products/labels/foto.jpg", False),
        ("", False),
    ],
)
def test_reconhece_url_de_etiqueta_pelo_caminho(url: str, esperado: bool) -> None:
    assert media_rules.e_foto_de_etiqueta(url) is esperado


# --- a análise da foto ---


def test_prompt_so_pede_composicao_de_etiqueta_legivel() -> None:
    """Composição tem o mesmo cuidado da marca: nunca é chutada (RN-58)."""
    assert "- composition:" in ANALYZE_IMAGE_PROMPT
    assert "APENAS se a etiqueta" in ANALYZE_IMAGE_PROMPT
    assert "Nunca estime a composição" in ANALYZE_IMAGE_PROMPT


def test_etiqueta_legivel_devolve_a_composicao(client, monkeypatch) -> None:
    fake = _ProviderDaEtiqueta()
    monkeypatch.setattr(assistant_controller, "get_ai_provider", lambda: fake)

    resposta = client.post(
        "/api/ai/listing-suggestions",
        json={"image_urls": [FOTO], "label_image_url": ETIQUETA},
        headers=_sessao(client),
    )

    assert resposta.status_code == 200
    assert resposta.json()["composition"] == {
        "value": "100% algodão",
        "confidence": 0.85,
    }
    # Uma análise só, com a etiqueta depois das fotos da peça.
    assert fake.received_urls == [FOTO, ETIQUETA]


def test_sem_etiqueta_legivel_a_composicao_vem_vazia(client, monkeypatch) -> None:
    fake = _ProviderDaEtiqueta()
    monkeypatch.setattr(assistant_controller, "get_ai_provider", lambda: fake)

    resposta = client.post(
        "/api/ai/listing-suggestions",
        json={"image_urls": [FOTO]},
        headers=_sessao(client),
    )

    assert resposta.status_code == 200
    assert resposta.json()["composition"] is None
    assert fake.received_urls == [FOTO]


def test_so_a_etiqueta_tambem_e_analisada(client, monkeypatch) -> None:
    fake = _ProviderDaEtiqueta()
    monkeypatch.setattr(assistant_controller, "get_ai_provider", lambda: fake)

    resposta = client.post(
        "/api/ai/listing-suggestions",
        json={"image_urls": [], "label_image_url": ETIQUETA},
        headers=_sessao(client),
    )

    assert resposta.status_code == 200
    assert resposta.json()["composition"]["value"] == "100% algodão"
    assert fake.received_urls == [ETIQUETA]


# --- a composição na peça ---


def test_composicao_vem_no_rascunho_no_detalhe_e_na_edicao(
    client, db_session, auth_headers
) -> None:
    user, _ = _vendedora(db_session)
    headers = auth_headers(user.id)

    criada = client.post(
        "/api/users/me/products",
        json={"name": "Camisa", "price": "59.90", "composition": "100% algodão"},
        headers=headers,
    )
    assert criada.status_code == 201
    assert criada.json()["composition"] == "100% algodão"
    product_id = criada.json()["id"]

    detalhe = client.get(f"/api/users/me/products/{product_id}", headers=headers)
    assert detalhe.json()["composition"] == "100% algodão"

    editada = client.patch(
        f"/api/users/me/products/{product_id}",
        json={"composition": "95% algodão, 5% elastano"},
        headers=headers,
    )
    assert editada.status_code == 200
    assert editada.json()["composition"] == "95% algodão, 5% elastano"


def test_composicao_e_opcional(client, db_session, auth_headers) -> None:
    user, _ = _vendedora(db_session)

    criada = client.post(
        "/api/users/me/products",
        json={"name": "Camisa", "price": "59.90"},
        headers=auth_headers(user.id),
    )

    assert criada.status_code == 201
    assert criada.json()["composition"] is None


def test_composicao_aparece_no_detalhe_publico(client, db_session) -> None:
    _, store = _vendedora(db_session)
    product = Product(
        store=store,
        name="Camisa",
        price=Decimal("59.90"),
        status="ativo",
        composition="100% linho",
        images=[ProductImage(image_url=FOTO, position=0)],
    )
    db_session.add(product)
    db_session.commit()

    resposta = client.get(f"/api/products/{product.id}")

    assert resposta.status_code == 200
    assert resposta.json()["composition"] == "100% linho"


def test_composicao_acima_do_limite_da_coluna_e_recusada(
    client, db_session, auth_headers
) -> None:
    user, _ = _vendedora(db_session)

    resposta = client.post(
        "/api/users/me/products",
        json={"name": "Camisa", "price": "59.90", "composition": "x" * 201},
        headers=auth_headers(user.id),
    )

    assert resposta.status_code == 422


# --- a etiqueta fica fora da galeria ---


def test_etiqueta_nao_entra_na_galeria_ao_criar(
    client, db_session, auth_headers
) -> None:
    user, _ = _vendedora(db_session)

    resposta = client.post(
        "/api/users/me/products",
        json={"name": "Camisa", "price": "59.90", "images": [FOTO, ETIQUETA]},
        headers=auth_headers(user.id),
    )

    assert resposta.status_code == 422
    assert "images" in resposta.json()["error"]["fields"]
    assert db_session.query(Product).count() == 0


def test_etiqueta_nao_entra_na_galeria_ao_editar(
    client, db_session, auth_headers
) -> None:
    user, _ = _vendedora(db_session)
    headers = auth_headers(user.id)
    criada = client.post(
        "/api/users/me/products",
        json={"name": "Camisa", "price": "59.90"},
        headers=headers,
    )

    resposta = client.patch(
        f"/api/users/me/products/{criada.json()['id']}",
        json={"images": [ETIQUETA]},
        headers=headers,
    )

    assert resposta.status_code == 422
    assert "images" in resposta.json()["error"]["fields"]


def test_so_com_a_etiqueta_a_peca_nao_publica(client, db_session, auth_headers) -> None:
    """RN-47: a etiqueta não conta como foto da peça. Como ela não entra em
    `images`, a peça que só tem etiqueta continua sem foto para publicar."""
    user, _ = _vendedora(db_session)
    headers = auth_headers(user.id)
    criada = client.post(
        "/api/users/me/products",
        json={"name": "Camisa", "price": "59.90", "composition": "100% algodão"},
        headers=headers,
    )
    product_id = criada.json()["id"]
    recusada = client.patch(
        f"/api/users/me/products/{product_id}",
        json={"images": [ETIQUETA]},
        headers=headers,
    )
    assert recusada.status_code == 422

    publicada = client.post(
        f"/api/users/me/products/{product_id}/publish", headers=headers
    )

    assert publicada.status_code == 422
    assert "images" in publicada.json()["error"]["fields"]


# --- a composição no vetor ---


def test_composicao_entra_no_texto_do_vetor(db_session) -> None:
    _, store = _vendedora(db_session)
    product = Product(
        store=store, name="Camisa", price=Decimal("59.90"), composition="100% linho"
    )

    assert "100% linho" in texto_da_peca(product)


def test_sem_composicao_o_texto_do_vetor_nao_muda(db_session) -> None:
    """Peça sem composição gera o mesmo texto de antes: os vetores já gravados
    continuam descrevendo a peça."""
    _, store = _vendedora(db_session)
    product = Product(store=store, name="Camisa", price=Decimal("59.90"))

    assert texto_da_peca(product) == "Camisa Porto Alegre R$ 59.90"
