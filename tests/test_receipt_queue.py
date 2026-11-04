"""Fila de comprovantes da administradora (back-end#250).

Os comprovantes entram pela rota de envio de verdade (#249), com o S3 dublado
em memória como em `test_media_upload.py`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event

from app.controllers.order_controller import OrderController
from app.controllers.payment_review_controller import PaymentReviewController
from app.core.clock import utcnow_naive
from app.main import app
from app.models import Order, Product, ProductImage, Seller, Store, User
from app.schemas.order_schema import OrderCreate
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
FILA = "/api/admin/payments"


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


@pytest.fixture(autouse=True)
def storage():
    storage = MediaStorage("bucket-de-teste", _S3EmMemoria())
    app.dependency_overrides[get_media_storage] = lambda: storage
    yield storage
    app.dependency_overrides.pop(get_media_storage, None)


def make_user(db, name: str, email: str, **extra) -> User:
    user = User(name=name, email=email, password_hash="x", **extra)
    db.add(user)
    db.flush()
    return user


def make_store(db, name: str, dona: str, documento: str) -> Store:
    store = Store(
        name=name,
        pix_key=f"{name.lower().replace(' ', '.')}@pix",
        seller=Seller(
            user=make_user(db, dona, f"{documento}@loja.test"),
            document_type="CPF",
            document_value=documento,
        ),
    )
    db.add(store)
    db.flush()
    return store


def make_product(db, store: Store, name: str, price: str = "100.00") -> Product:
    product = Product(
        store=store,
        name=name,
        price=Decimal(price),
        status="ativo",
        images=[ProductImage(image_url=f"https://cdn.test/{name}.jpg", position=0)],
    )
    db.add(product)
    db.flush()
    return product


@pytest.fixture
def cenario(db_session, auth_headers):
    aurora = make_store(db_session, "Brechó Aurora", "Marina Oliveira", "52998224725")
    sul = make_store(db_session, "Garimpo do Sul", "Rafael Menezes", "11144477735")
    ana = make_user(db_session, "Ana Souza", "ana@test.local", phone="51999990000")
    bruno = make_user(db_session, "Bruno Lima", "bruno@test.local")
    admin = make_user(db_session, "Admin", "admin@test.local", is_admin=True)
    pecas = {
        "jaqueta": make_product(db_session, aurora, "Jaqueta", "100.00"),
        "saia": make_product(db_session, sul, "Saia", "50.00"),
        "bolsa": make_product(db_session, aurora, "Bolsa", "80.00"),
    }
    db_session.commit()
    return {
        "ana": ana,
        "bruno": bruno,
        "admin": admin,
        "pecas": pecas,
        "como_admin": auth_headers(admin.id, is_admin=True),
        "como": lambda user: auth_headers(user.id),
    }


def pedir(db, comprador: User, *pecas: Product) -> Order:
    resposta = OrderController(db).create(
        comprador.id,
        OrderCreate(product_ids=[p.id for p in pecas], delivery_address=ENDERECO),
    )
    return db.get(Order, resposta.id)


def enviar(client, cenario, comprador: User, pedido: Order, pdf: bool = False):
    arquivo = (
        ("c.pdf", PDF, "application/pdf") if pdf else ("c.jpg", JPEG, "image/jpeg")
    )
    response = client.post(
        f"/api/users/me/orders/{pedido.id}/receipt",
        headers=cenario["como"](comprador),
        files={"file": arquivo},
    )
    assert response.status_code == 200, response.text


def enviado_ha(db, pedido: Order, tempo: timedelta) -> None:
    db.refresh(pedido)
    pedido.payments[-1].submitted_at = utcnow_naive() - tempo
    db.commit()


def fila(client, cenario, **params):
    return client.get(FILA, headers=cenario["como_admin"], params=params)


@contextmanager
def contar_consultas(db) -> Iterator[list[str]]:
    consultas: list[str] = []

    def registrar(conn, cursor, statement, *args) -> None:
        consultas.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", registrar)
    try:
        yield consultas
    finally:
        event.remove(engine, "before_cursor_execute", registrar)


# --- quem entra e em que ordem ---------------------------------------------------


def test_lista_so_pedidos_com_comprovante_mais_antigo_primeiro(
    client, db_session, cenario
):
    p = cenario["pecas"]
    primeiro = pedir(db_session, cenario["ana"], p["jaqueta"])
    segundo = pedir(db_session, cenario["bruno"], p["saia"])
    pedir(db_session, cenario["ana"], p["bolsa"])  # sem comprovante: fora da fila
    enviar(client, cenario, cenario["ana"], primeiro)
    enviar(client, cenario, cenario["bruno"], segundo)
    # Datas invertidas em relação aos ids: a ordem tem que ser pela data.
    enviado_ha(db_session, primeiro, timedelta(hours=1))
    enviado_ha(db_session, segundo, timedelta(hours=2))

    body = fila(client, cenario).json()

    assert [item["order_id"] for item in body["items"]] == [segundo.id, primeiro.id]
    assert body["total"] == 2


def test_fila_vazia_nao_e_erro(client, cenario):
    body = fila(client, cenario).json()

    assert (body["items"], body["total"]) == ([], 0)


# --- filtro e busca --------------------------------------------------------------


@pytest.fixture
def tres_situacoes(client, db_session, cenario):
    """Um comprovante pendente, um aprovado e um rejeitado."""
    p, admin = cenario["pecas"], cenario["admin"]
    pendente = pedir(db_session, cenario["ana"], p["jaqueta"])
    aprovado = pedir(db_session, cenario["bruno"], p["saia"])
    rejeitado = pedir(db_session, cenario["ana"], p["bolsa"])
    for comprador, pedido in (
        (cenario["ana"], pendente),
        (cenario["bruno"], aprovado),
        (cenario["ana"], rejeitado),
    ):
        enviar(client, cenario, comprador, pedido)
    PaymentReviewController(db_session).approve(aprovado.id, admin)
    PaymentReviewController(db_session).reject(rejeitado.id, admin, "Ilegível.")
    return {"pendente": pendente, "aprovado": aprovado, "rejeitado": rejeitado}


@pytest.mark.parametrize("situacao", ["pendente", "aprovado", "rejeitado"])
def test_filtrar_por_situacao(client, cenario, tres_situacoes, situacao):
    body = fila(client, cenario, status=situacao).json()

    assert [item["order_id"] for item in body["items"]] == [tres_situacoes[situacao].id]
    assert body["items"][0]["payment"]["status"] == situacao


def test_situacao_desconhecida_responde_422(client, cenario):
    assert fila(client, cenario, status="cancelado").status_code == 422


@pytest.mark.parametrize(
    "termo, compradores",
    [
        ("ana", ["Ana Souza", "Ana Souza"]),  # nome do comprador, sem caixa
        ("LIMA", ["Bruno Lima"]),
        ("garimpo", ["Bruno Lima"]),  # nome da loja
        ("aurora", ["Ana Souza", "Ana Souza"]),
        ("ninguém", []),
    ],
)
def test_busca_casa_nome_do_comprador_ou_da_loja(
    client, cenario, tres_situacoes, termo, compradores
):
    body = fila(client, cenario, q=termo).json()

    assert sorted(item["buyer"]["name"] for item in body["items"]) == compradores


# --- o que cada linha traz -------------------------------------------------------


def test_linha_traz_contato_loja_valores_e_o_comprovante(client, db_session, cenario):
    pedido = pedir(db_session, cenario["ana"], cenario["pecas"]["jaqueta"])
    enviar(client, cenario, cenario["ana"], pedido)

    item = fila(client, cenario).json()["items"][0]

    assert item["buyer"] == {
        "name": "Ana Souza",
        "email": "ana@test.local",
        "phone": "51999990000",
    }
    assert item["store"]["name"] == "Brechó Aurora"
    assert item["store"]["seller_name"] == "Marina Oliveira"
    assert item["store"]["pix_key"] == "brechó.aurora@pix"
    assert item["items"] == [
        {
            "product_id": cenario["pecas"]["jaqueta"].id,
            "name": "Jaqueta",
            "price": 100.0,
            "cover_image_url": "https://cdn.test/Jaqueta.jpg",
        }
    ]
    assert item["payment"]["status"] == "pendente"
    assert item["payment"]["validated_by"] is None
    assert item["payment"]["rejection_reason"] is None


def test_valores_saem_como_numero_e_o_liquido_e_o_total_menos_9_por_cento(
    client, db_session, cenario
):
    pedido = pedir(db_session, cenario["ana"], cenario["pecas"]["jaqueta"])
    enviar(client, cenario, cenario["ana"], pedido)

    item = fila(client, cenario).json()["items"][0]

    assert item["total_amount"] == 100.0
    assert item["platform_fee"] == 9.0
    assert item["seller_net_amount"] == 91.0
    for campo in ("total_amount", "platform_fee", "seller_net_amount"):
        assert isinstance(item[campo], float), campo


@pytest.mark.parametrize("pdf, tipo", [(False, "image"), (True, "pdf")])
def test_receipt_type_distingue_imagem_de_pdf(client, db_session, cenario, pdf, tipo):
    pedido = pedir(db_session, cenario["ana"], cenario["pecas"]["jaqueta"])
    enviar(client, cenario, cenario["ana"], pedido, pdf=pdf)

    assert fila(client, cenario).json()["items"][0]["payment"]["receipt_type"] == tipo


def test_receipt_url_e_a_rota_autenticada_e_devolve_o_arquivo(
    client, db_session, cenario
):
    pedido = pedir(db_session, cenario["ana"], cenario["pecas"]["jaqueta"])
    enviar(client, cenario, cenario["ana"], pedido, pdf=True)

    url = fila(client, cenario).json()["items"][0]["payment"]["receipt_url"]

    assert url == f"http://testserver/api/admin/payments/{pedido.id}/receipt"
    assert "/api/media/" not in url
    arquivo = client.get(url, headers=cenario["como_admin"])
    assert arquivo.status_code == 200
    assert arquivo.content == PDF
    assert client.get(url, headers=cenario["como"](cenario["ana"])).status_code == 403


def test_aprovado_mostra_quem_validou_e_quando(client, cenario, tres_situacoes):
    item = fila(client, cenario, status="aprovado").json()["items"][0]

    assert item["payment"]["validated_by"] == {
        "id": cenario["admin"].id,
        "name": "Admin",
    }
    assert item["payment"]["validated_at"]


def test_reenvio_pendente_mostra_o_motivo_da_rejeicao_anterior(
    client, db_session, cenario
):
    """RN-23: a administradora vê o que já foi dito ao comprador."""
    pedido = pedir(db_session, cenario["ana"], cenario["pecas"]["jaqueta"])
    enviar(client, cenario, cenario["ana"], pedido)
    PaymentReviewController(db_session).reject(
        pedido.id, cenario["admin"], "Valor diferente do pedido."
    )
    enviar(client, cenario, cenario["ana"], pedido)

    body = fila(client, cenario).json()

    assert body["total"] == 1, "uma linha por pedido, não por envio"
    pagamento = body["items"][0]["payment"]
    assert pagamento["status"] == "pendente"
    assert pagamento["validated_by"] is None
    assert pagamento["rejection_reason"] == "Valor diferente do pedido."


# --- paginação e consultas -------------------------------------------------------


def test_paginacao(client, db_session, cenario):
    p = cenario["pecas"]
    for comprador, peca in (
        (cenario["ana"], p["jaqueta"]),
        (cenario["bruno"], p["saia"]),
        (cenario["ana"], p["bolsa"]),
    ):
        enviar(client, cenario, comprador, pedir(db_session, comprador, peca))

    body = fila(client, cenario, page=2, page_size=2).json()

    assert (body["page"], body["page_size"], body["total"]) == (2, 2, 3)
    assert len(body["items"]) == 1


def test_fila_nao_faz_uma_consulta_por_pedido(client, db_session, cenario):
    """A sessão é esvaziada antes de contar: com loja, vendedor e comprador já
    carregados nela, um N+1 nos muitos-para-um não faria SQL e passaria."""
    ids = {
        "ana": cenario["ana"].id,
        "bruno": cenario["bruno"].id,
        **{nome: peca.id for nome, peca in cenario["pecas"].items()},
    }

    def comprar(comprador: str, peca: str) -> None:
        # Recarregados pelo id: o `expunge_all` tira da sessão os do cenário.
        quem = db_session.get(User, ids[comprador])
        enviar(
            client,
            cenario,
            quem,
            pedir(db_session, quem, db_session.get(Product, ids[peca])),
        )

    comprar("ana", "jaqueta")
    db_session.expunge_all()
    with contar_consultas(db_session) as com_um:
        fila(client, cenario)

    comprar("bruno", "saia")
    comprar("ana", "bolsa")
    db_session.expunge_all()
    with contar_consultas(db_session) as com_tres:
        fila(client, cenario)

    assert len(com_tres) == len(com_um)


# --- matriz de papel nas duas rotas ----------------------------------------------


@pytest.mark.parametrize("rota", ["fila", "arquivo"])
def test_matriz_de_papel(client, db_session, cenario, rota):
    pedido = pedir(db_session, cenario["ana"], cenario["pecas"]["jaqueta"])
    enviar(client, cenario, cenario["ana"], pedido)
    vendedora = db_session.get(Store, cenario["pecas"]["jaqueta"].store_id).seller.user
    caminho = FILA if rota == "fila" else f"{FILA}/{pedido.id}/receipt"

    assert client.get(caminho).status_code == 401
    for quem in (cenario["ana"], vendedora):
        response = client.get(caminho, headers=cenario["como"](quem))
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "ADMIN_REQUIRED"
    assert client.get(caminho, headers=cenario["como_admin"]).status_code == 200


@pytest.mark.postgres
def test_busca_ignora_acento_no_postgres(pg_client, pg_session, auth_headers):
    loja = make_store(pg_session, "Brechó da Conceição", "Lúcia", "52998224725")
    comprador = make_user(pg_session, "José Antônio", "jose@test.local")
    admin = make_user(pg_session, "Admin", "admin@test.local", is_admin=True)
    peca = make_product(pg_session, loja, "Vestido")
    pg_session.commit()
    pedido = pedir(pg_session, comprador, peca)
    response = pg_client.post(
        f"/api/users/me/orders/{pedido.id}/receipt",
        headers=auth_headers(comprador.id),
        files={"file": ("c.jpg", JPEG, "image/jpeg")},
    )
    assert response.status_code == 200

    for termo in ("conceicao", "JOSE ANTONIO"):
        body = pg_client.get(
            FILA, headers=auth_headers(admin.id, is_admin=True), params={"q": termo}
        ).json()
        assert [item["order_id"] for item in body["items"]] == [pedido.id], termo
