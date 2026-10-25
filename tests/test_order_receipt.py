"""O comprador anexa o comprovante ao pedido (back-end#249).

S3 dublado em memória, como em `test_media_upload.py`.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from app.controllers.media_controller import ArquivoRecebido
from app.controllers.order_controller import OrderController
from app.controllers.payment_review_controller import PaymentReviewController
from app.core.clock import utcnow_naive
from app.core.errors import AppError
from app.main import app
from app.models import Order, Payment, Product, ProductImage, Seller, Store, User
from app.repositories.order_repository import OrderRepository
from app.schemas.order_schema import OrderCreate
from app.services import media_rules
from app.services.media_storage import MediaStorage
from app.views.media_routes import get_media_storage

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
PDF = b"%PDF-1.7\n" + b"0" * 64
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
        corpo, content_type = self.objetos[Key]

        class _Body:
            @staticmethod
            def read() -> bytes:
                return corpo

        return {"Body": _Body(), "ContentType": content_type}

    def delete_object(self, Bucket: str, Key: str) -> None:  # noqa: N803
        self.objetos.pop(Key, None)


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
    outra = make_user(db_session, "outra@test.local")
    admin = make_user(db_session, "admin@test.local", is_admin=True)
    db_session.commit()
    resposta = OrderController(db_session).create(
        compradora.id, OrderCreate(product_ids=[peca.id], delivery_address=ENDERECO)
    )
    return {
        "pedido": db_session.get(Order, resposta.id),
        "peca": peca,
        "compradora": compradora,
        "admin": admin,
        "storage": storage,
        "como_compradora": auth_headers(compradora.id),
        "como_outra": auth_headers(outra.id),
    }


def enviar(
    client, cenario, nome="comprovante.jpg", conteudo=JPEG, tipo="image/jpeg", **kw
):
    order_id = kw.get("order_id", cenario["pedido"].id)
    return client.post(
        f"/api/users/me/orders/{order_id}/receipt",
        headers=kw.get("headers", cenario["como_compradora"]),
        files={"file": (nome, conteudo, tipo)},
    )


def pagamentos(db, cenario) -> list[Payment]:
    db.expire_all()
    return db.get(Order, cenario["pedido"].id).payments


def nada_mudou(db, cenario) -> None:
    pedido = db.get(Order, cenario["pedido"].id)
    db.refresh(pedido)
    assert pedido.status == "aguardando_comprovante"
    assert pagamentos(db, cenario) == []
    assert cenario["storage"].client.objetos == {}, "nenhum arquivo subiu"


# --- envio -----------------------------------------------------------------------


def test_enviar_imagem_poe_o_pedido_em_analise_e_grava_a_data(
    client, db_session, cenario
):
    response = enviar(client, cenario)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == cenario["pedido"].id
    assert body["status"] == "em_analise"
    assert body["payment"]["status"] == "pendente"
    assert body["payment"]["receipt_name"] == "comprovante.jpg"
    assert body["payment"]["submitted_at"]
    assert "rejection_reason" not in body["payment"]
    # Parcial, como no contrato: só a etapa que o envio criou.
    assert [h["status"] for h in body["history"]] == ["em_analise"]
    assert body["history"][0]["at"]

    [pagamento] = pagamentos(db_session, cenario)
    assert pagamento.receipt_content_type == "image/jpeg"
    assert cenario["storage"].client.objetos[pagamento.receipt_key][0] == JPEG


def test_enviar_pdf_funciona_igual(client, db_session, cenario):
    response = enviar(client, cenario, "comprovante.pdf", PDF, "application/pdf")

    assert response.status_code == 200
    assert response.json()["status"] == "em_analise"
    [pagamento] = pagamentos(db_session, cenario)
    assert pagamento.receipt_content_type == "application/pdf"


def test_o_detalhe_mostra_o_comprovante_enviado(client, cenario):
    enviar(client, cenario)

    detalhe = client.get(
        f"/api/users/me/orders/{cenario['pedido'].id}",
        headers=cenario["como_compradora"],
    ).json()

    assert detalhe["status"] == "em_analise"
    assert detalhe["payment"]["receipt_name"] == "comprovante.jpg"
    assert [h["status"] for h in detalhe["history"]] == [
        "aguardando_comprovante",
        "em_analise",
    ]


# --- recusas ---------------------------------------------------------------------


def test_acima_de_8_mib_responde_413_e_o_pedido_nao_muda(client, db_session, cenario):
    grande = b"0" * (media_rules.MAX_BYTES_PER_FILE + 1)

    response = enviar(client, cenario, "grande.pdf", grande, "application/pdf")

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "RECEIPT_TOO_LARGE"
    assert "8MiB" in response.json()["error"]["message"]
    nada_mudou(db_session, cenario)


def test_exatamente_8_mib_e_aceito(client, cenario):
    no_limite = b"0" * media_rules.MAX_BYTES_PER_FILE

    assert (
        enviar(client, cenario, "x.pdf", no_limite, "application/pdf").status_code
        == 200
    )


@pytest.mark.parametrize("tipo", ["image/gif", "text/html", "application/zip"])
def test_tipo_nao_aceito_responde_415(client, db_session, cenario, tipo):
    response = enviar(client, cenario, "x", b"conteudo", tipo)

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "RECEIPT_INVALID_TYPE"
    nada_mudou(db_session, cenario)


def test_arquivo_vazio_responde_422(client, db_session, cenario):
    response = enviar(client, cenario, conteudo=b"")

    assert response.status_code == 422
    nada_mudou(db_session, cenario)


def test_pedido_em_analise_responde_409_sem_empilhar(client, db_session, cenario):
    assert enviar(client, cenario).status_code == 200

    response = enviar(client, cenario, "outro.jpg")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ORDER_NOT_AWAITING_RECEIPT"
    assert len(pagamentos(db_session, cenario)) == 1
    assert len(cenario["storage"].client.objetos) == 1


def test_pedido_de_outra_pessoa_responde_404(client, db_session, cenario):
    response = enviar(client, cenario, headers=cenario["como_outra"])

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ORDER_NOT_FOUND"
    nada_mudou(db_session, cenario)


def test_pedido_inexistente_responde_404(client, cenario):
    assert enviar(client, cenario, order_id=999_999).status_code == 404


def test_sem_token_responde_401(client, cenario):
    response = client.post(
        f"/api/users/me/orders/{cenario['pedido'].id}/receipt",
        files={"file": ("c.jpg", JPEG, "image/jpeg")},
    )

    assert response.status_code == 401


# --- reenvio ---------------------------------------------------------------------


def test_reenvio_depois_da_rejeicao_guarda_os_dois_registros(
    client, db_session, cenario
):
    enviar(client, cenario, "primeiro.jpg")
    PaymentReviewController(db_session).reject(
        cenario["pedido"].id, cenario["admin"], "Ilegível."
    )

    response = enviar(client, cenario, "segundo.pdf", PDF, "application/pdf")

    assert response.status_code == 200
    assert response.json()["payment"]["receipt_name"] == "segundo.pdf"
    registros = pagamentos(db_session, cenario)
    assert [(p.status, p.receipt_name) for p in registros] == [
        ("rejeitado", "primeiro.jpg"),
        ("pendente", "segundo.pdf"),
    ]
    assert len(cenario["storage"].client.objetos) == 2, "o primeiro arquivo fica"


# --- prazo e consistência --------------------------------------------------------


def test_pedido_vencido_responde_409_e_e_expirado(client, db_session, cenario):
    """Sem rotina periódica, o envio é o gatilho da expiração (back-end#280)."""
    pedido = cenario["pedido"]
    pedido.expires_at = utcnow_naive() - timedelta(minutes=1)
    db_session.commit()

    response = enviar(client, cenario)

    assert response.status_code == 409
    db_session.expire_all()
    assert db_session.get(Order, pedido.id).status == "expirado"
    assert db_session.get(Product, cenario["peca"].id).status == "ativo"
    assert cenario["storage"].client.objetos == {}


def test_falha_depois_do_upload_apaga_o_arquivo(db_session, cenario, monkeypatch):
    """Envio concorrente: o outro passou na frente entre a leitura e a troca."""
    monkeypatch.setattr(OrderRepository, "transition", lambda *a, **kw: False)

    with pytest.raises(AppError) as erro:
        OrderController(db_session).submit_receipt(
            cenario["compradora"].id,
            cenario["pedido"].id,
            ArquivoRecebido("c.jpg", "image/jpeg", JPEG),
            cenario["storage"],
        )

    assert erro.value.status_code == 409
    assert cenario["storage"].client.objetos == {}, "sem objeto órfão no bucket"


def test_nome_com_caminho_do_navegador_vira_so_o_arquivo(client, db_session, cenario):
    enviar(
        client, cenario, nome="C:\\fakepath\\comprovante-nubank.png", tipo="image/png"
    )

    [pagamento] = pagamentos(db_session, cenario)
    assert pagamento.receipt_name == "comprovante-nubank.png"
