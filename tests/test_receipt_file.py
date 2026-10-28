"""PDF no comprovante e o arquivo servido só à administradora (back-end#244).

S3 dublado em memória, como em `test_media_upload.py`: o contrato com o boto3
está em `test_media_storage.py`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import inspect

from app.controllers.order_controller import OrderController
from app.main import app
from app.models import (
    Order,
    OrderStatusHistory,
    Payment,
    Product,
    ProductImage,
    Seller,
    Store,
    User,
)
from app.schemas.order_schema import OrderCreate
from app.services import media_rules
from app.services.media_storage import MediaStorage
from app.views.media_routes import get_media_storage

PDF = b"%PDF-1.7\n" + b"0" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
ENDERECO = {
    "zip_code": "90020000",
    "street": "Rua dos Andradas",
    "number": "100",
    "city": "Porto Alegre",
    "state": "RS",
}


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
def storage():
    storage = MediaStorage("bucket-de-teste", _S3EmMemoria())
    app.dependency_overrides[get_media_storage] = lambda: storage
    yield storage
    app.dependency_overrides.pop(get_media_storage, None)


def make_user(db, email: str, *, is_admin: bool = False) -> User:
    user = User(
        name=email.split("@")[0],
        email=email,
        password_hash="not-a-real-password",
        is_admin=is_admin,
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def cenario(db_session, auth_headers, storage):
    """Pedido de uma compradora, ainda sem comprovante."""
    aurora = Store(
        name="Aurora",
        pix_key="aurora@pix",
        seller=Seller(
            user=make_user(db_session, "aurora@loja.test"),
            document_type="CPF",
            document_value="52998224725",
        ),
    )
    db_session.add(aurora)
    db_session.flush()
    peca = Product(
        store=aurora,
        name="Jaqueta",
        price=Decimal("100.00"),
        status="ativo",
        images=[ProductImage(image_url="https://cdn.test/j.jpg", position=0)],
    )
    db_session.add(peca)
    compradora = make_user(db_session, "compradora@test.local")
    admin = make_user(db_session, "admin@test.local", is_admin=True)
    db_session.commit()
    resposta = OrderController(db_session).create(
        compradora.id, OrderCreate(product_ids=[peca.id], delivery_address=ENDERECO)
    )
    return {
        "pedido": db_session.get(Order, resposta.id),
        "storage": storage,
        "como_admin": auth_headers(admin.id, is_admin=True),
        "como_compradora": auth_headers(compradora.id),
    }


def enviar(
    db,
    cenario,
    conteudo: bytes = PDF,
    tipo: str | None = "application/pdf",
    nome: str | None = "comprovante-itau.pdf",
) -> Payment:
    """O que a rota de envio (#249) grava: arquivo no storage e o pagamento."""
    pedido = cenario["pedido"]
    key = cenario["storage"].upload("receipt", conteudo, tipo or "image/jpeg")
    pedido.status = "em_analise"
    db.add(OrderStatusHistory(order_id=pedido.id, status="em_analise"))
    payment = Payment(
        order_id=pedido.id,
        receipt_key=key,
        receipt_name=nome,
        receipt_content_type=tipo,
    )
    db.add(payment)
    db.commit()
    return payment


def arquivo_do_comprovante(client, cenario, headers_key: str = "como_admin"):
    return client.get(
        f"/api/admin/payments/{cenario['pedido'].id}/receipt",
        headers=cenario[headers_key],
    )


# --- PDF no upload ---------------------------------------------------------------


def test_pdf_como_comprovante_responde_201_e_devolve_o_tipo(client, cenario):
    response = client.post(
        "/api/users/me/media",
        headers=cenario["como_compradora"],
        data={"kind": "receipt"},
        files={"files": ("comprovante.pdf", PDF, "application/pdf")},
    )

    assert response.status_code == 201
    item = response.json()["items"][0]
    assert item["content_type"] == "application/pdf"
    assert item["key"].startswith("payments/receipts/")
    assert item["url"] is None, "comprovante não tem endereço público"


def test_pdf_como_foto_de_peca_continua_recusado(client, cenario):
    response = client.post(
        "/api/users/me/media",
        headers=cenario["como_compradora"],
        data={"kind": "photo"},
        files={"files": ("peca.pdf", PDF, "application/pdf")},
    )

    assert response.status_code == 422


def test_comprovante_acima_de_8_mib_e_recusado_dizendo_o_limite(client, cenario):
    grande = b"0" * (media_rules.MAX_BYTES_PER_FILE + 1)

    response = client.post(
        "/api/users/me/media",
        headers=cenario["como_compradora"],
        data={"kind": "receipt"},
        files={"files": ("grande.pdf", grande, "application/pdf")},
    )

    assert response.status_code == 422
    assert "8MiB" in response.json()["error"]["message"]


# --- arquivo servido só à administradora ----------------------------------------


def test_administradora_recebe_o_arquivo_com_o_tipo_original(
    client, db_session, cenario
):
    enviar(db_session, cenario)

    response = arquivo_do_comprovante(client, cenario)

    assert response.status_code == 200
    assert response.content == PDF
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_comprador_dono_do_pedido_recebe_403(client, db_session, cenario):
    enviar(db_session, cenario)

    response = arquivo_do_comprovante(client, cenario, "como_compradora")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_REQUIRED"


def test_sem_sessao_recebe_401(client, db_session, cenario):
    enviar(db_session, cenario)

    response = client.get(f"/api/admin/payments/{cenario['pedido'].id}/receipt")

    assert response.status_code == 401


def test_pedido_sem_comprovante_responde_404(client, cenario):
    response = arquivo_do_comprovante(client, cenario)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RECEIPT_NOT_FOUND"


def test_pedido_inexistente_responde_404(client, cenario):
    response = client.get(
        "/api/admin/payments/999999/receipt", headers=cenario["como_admin"]
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ORDER_NOT_FOUND"


def test_serve_o_comprovante_mais_recente(client, db_session, cenario):
    primeiro = enviar(db_session, cenario, conteudo=JPEG, tipo="image/jpeg")
    primeiro.status = "rejeitado"
    primeiro.rejection_reason = "Ilegível."
    primeiro.validated_by_id = primeiro.order.buyer_id
    primeiro.validated_at = primeiro.submitted_at
    db_session.commit()
    enviar(db_session, cenario)

    response = arquivo_do_comprovante(client, cenario)

    assert response.content == PDF


def test_o_tipo_gravado_no_envio_vale_sobre_o_do_objeto(client, db_session, cenario):
    """A coluna é a fonte: o objeto pode ter sido gravado com tipo genérico."""
    payment = enviar(db_session, cenario)
    cenario["storage"].client.objetos[payment.receipt_key] = (
        PDF,
        "application/octet-stream",
    )

    response = arquivo_do_comprovante(client, cenario)

    assert response.headers["content-type"] == "application/pdf"


def test_linha_sem_tipo_gravado_usa_o_tipo_do_objeto(client, db_session, cenario):
    """Comprovante gravado antes da coluna: o tipo vem do objeto no storage."""
    enviar(db_session, cenario, conteudo=JPEG, tipo=None, nome=None)

    response = arquivo_do_comprovante(client, cenario)

    assert response.headers["content-type"] == "image/jpeg"


# --- o que o comprador vê --------------------------------------------------------


def test_detalhe_do_pedido_traz_o_nome_do_arquivo_e_nunca_a_url(
    client, db_session, cenario
):
    enviar(db_session, cenario)

    payment = client.get(
        f"/api/users/me/orders/{cenario['pedido'].id}",
        headers=cenario["como_compradora"],
    ).json()["payment"]

    assert payment["receipt_name"] == "comprovante-itau.pdf"
    assert "payments/receipts/" not in str(payment)
    assert "receipt_url" not in payment


# --- migration -------------------------------------------------------------------


@pytest.mark.postgres
def test_migration_cria_as_colunas_do_comprovante(pg_engine):
    with pg_engine.connect() as conn:
        colunas = {c["name"]: c for c in inspect(conn).get_columns("payments")}

    assert colunas["receipt_name"]["nullable"] is True
    assert colunas["receipt_content_type"]["nullable"] is True
