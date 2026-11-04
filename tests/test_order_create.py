"""Criação do pedido e reserva das peças (back-end#247)."""

import threading
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.controllers.order_controller import OrderController
from app.core.errors import Conflict
from app.models import (
    Order,
    OrderItem,
    OrderStatusHistory,
    Product,
    ProductImage,
    Seller,
    Store,
    User,
)
from app.schemas.order_schema import OrderCreate

ORDERS_URL = "/api/users/me/orders"

ENDERECO = {
    "zip_code": "90020000",
    "street": "Rua dos Andradas",
    "number": "100",
    "complement": "ap 2",
    "neighborhood": "Centro",
    "city": "Porto Alegre",
    "state": "RS",
}


def make_user(db: Session, email: str) -> User:
    user = User(name=email, email=email, password_hash="not-a-real-password")
    db.add(user)
    db.flush()
    return user


def make_store(
    db: Session, name: str, document: str, pix_key: str | None = "pix@loja.test"
) -> Store:
    store = Store(
        name=name,
        pix_key=pix_key,
        seller=Seller(
            user=make_user(db, f"{document}@loja.test"),
            document_type="CPF",
            document_value=document,
        ),
    )
    db.add(store)
    db.flush()
    return store


def make_product(
    db: Session, store: Store, name: str, price: str, status: str = "ativo"
) -> Product:
    product = Product(
        store=store,
        name=name,
        price=Decimal(price),
        status=status,
        images=[ProductImage(image_url=f"https://cdn.test/{name}.jpg", position=0)],
    )
    db.add(product)
    db.flush()
    return product


def pedir(client, auth_headers, buyer: User, *products: Product):
    return client.post(
        ORDERS_URL,
        json={
            "product_ids": [product.id for product in products],
            "delivery_address": ENDERECO,
        },
        headers=auth_headers(buyer.id),
    )


def total_de_pedidos(db: Session) -> int:
    return db.scalar(select(func.count(Order.id)))


@pytest.fixture
def cenario(db_session):
    """Uma compradora, a loja Aurora (duas peças) e a Brisa (uma peça)."""
    buyer = make_user(db_session, "compradora@test.local")
    aurora = make_store(db_session, "Aurora", "11111111111", pix_key="aurora@pix")
    brisa = make_store(db_session, "Brisa", "22222222222")
    jaqueta = make_product(db_session, aurora, "Jaqueta", "100.00")
    saia = make_product(db_session, aurora, "Saia", "50.50")
    bolsa = make_product(db_session, brisa, "Bolsa", "80.00")
    db_session.commit()
    return {
        "buyer": buyer,
        "aurora": aurora,
        "jaqueta": jaqueta,
        "saia": saia,
        "bolsa": bolsa,
    }


def test_duas_pecas_da_mesma_loja_criam_o_pedido_com_os_tres_valores(
    client, cenario, auth_headers
):
    response = pedir(
        client, auth_headers, cenario["buyer"], cenario["jaqueta"], cenario["saia"]
    )

    assert response.status_code == 201
    body = response.json()
    assert body["product_amount"] == 150.50
    # 9% de 150,50 = 13,545, arredondado para cima no meio centavo.
    assert body["platform_fee"] == 13.55
    # O comprador paga o preço cheio: a comissão sai do lado do vendedor.
    assert body["total_amount"] == body["product_amount"]
    assert [item["product_id"] for item in body["items"]] == [
        cenario["jaqueta"].id,
        cenario["saia"].id,
    ]


def test_valores_saem_como_numero_e_nao_string(client, cenario, auth_headers):
    """Decimal do Pydantic serializa como string sem `@field_serializer`, e
    isso já custou dois PRs ao projeto (#212)."""
    body = pedir(client, auth_headers, cenario["buyer"], cenario["jaqueta"]).json()

    for campo in ("product_amount", "platform_fee", "total_amount"):
        assert isinstance(body[campo], float), f"{campo} veio {body[campo]!r}"
    assert isinstance(body["items"][0]["price"], float)


def test_resposta_traz_a_chave_pix_e_o_pedido_aguardando_comprovante(
    client, cenario, auth_headers
):
    body = pedir(client, auth_headers, cenario["buyer"], cenario["jaqueta"]).json()

    assert body["store"] == {
        "id": cenario["aurora"].id,
        "name": "Aurora",
        "pix_key": "aurora@pix",
    }
    assert body["status"] == "aguardando_comprovante"
    assert [entry["status"] for entry in body["history"]] == ["aguardando_comprovante"]
    assert body["payment"] is None
    assert body["delivery_address"] == ENDERECO
    assert body["items"][0]["cover_image_url"] == "https://cdn.test/Jaqueta.jpg"


def test_expira_tres_dias_depois_da_criacao(client, cenario, auth_headers):
    body = pedir(client, auth_headers, cenario["buyer"], cenario["jaqueta"]).json()

    criado = datetime.fromisoformat(body["created_at"])
    expira = datetime.fromisoformat(body["expires_at"])
    assert abs(expira - criado - timedelta(days=3)) < timedelta(minutes=1)


def test_pecas_do_pedido_ficam_reservadas(client, db_session, cenario, auth_headers):
    pedir(client, auth_headers, cenario["buyer"], cenario["jaqueta"], cenario["saia"])

    for nome in ("jaqueta", "saia"):
        db_session.refresh(cenario[nome])
        assert cenario[nome].status == "reservado"


def test_pecas_de_lojas_diferentes_respondem_409(
    client, db_session, cenario, auth_headers
):
    response = pedir(
        client, auth_headers, cenario["buyer"], cenario["jaqueta"], cenario["bolsa"]
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MIXED_STORES"
    assert total_de_pedidos(db_session) == 0


@pytest.mark.parametrize("status", ["vendido", "reservado", "despublicado"])
def test_peca_que_nao_esta_ativo_responde_409_sem_criar_pedido(
    client, db_session, cenario, auth_headers, status
):
    cenario["saia"].status = status
    db_session.commit()

    response = pedir(
        client, auth_headers, cenario["buyer"], cenario["jaqueta"], cenario["saia"]
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PIECE_UNAVAILABLE"
    assert total_de_pedidos(db_session) == 0
    # A peça que estava à venda continua à venda.
    db_session.refresh(cenario["jaqueta"])
    assert cenario["jaqueta"].status == "ativo"


def test_peca_inexistente_responde_409(client, db_session, cenario, auth_headers):
    response = client.post(
        ORDERS_URL,
        json={"product_ids": [999999], "delivery_address": ENDERECO},
        headers=auth_headers(cenario["buyer"].id),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PIECE_UNAVAILABLE"


def test_mesma_peca_nao_entra_em_dois_pedidos(
    client, db_session, auth_headers, cenario
):
    outra = make_user(db_session, "outra@test.local")
    db_session.commit()

    primeiro = pedir(client, auth_headers, cenario["buyer"], cenario["jaqueta"])
    segundo = pedir(client, auth_headers, outra, cenario["jaqueta"])

    assert primeiro.status_code == 201
    assert segundo.status_code == 409
    assert segundo.json()["error"]["code"] == "PIECE_UNAVAILABLE"
    assert total_de_pedidos(db_session) == 1


def test_loja_sem_chave_pix_responde_409(client, db_session, cenario, auth_headers):
    sem_pix = make_store(db_session, "Sem Pix", "33333333333", pix_key=None)
    vestido = make_product(db_session, sem_pix, "Vestido", "40.00")
    db_session.commit()

    response = pedir(client, auth_headers, cenario["buyer"], vestido)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STORE_WITHOUT_PIX"
    db_session.refresh(vestido)
    assert vestido.status == "ativo"


def test_sem_token_responde_401(client, cenario):
    response = client.post(
        ORDERS_URL,
        json={"product_ids": [cenario["jaqueta"].id], "delivery_address": ENDERECO},
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "product_ids",
    [[], [1, 1]],
    ids=["lista vazia", "peca repetida"],
)
def test_lista_de_pecas_invalida_responde_422(
    client, cenario, auth_headers, product_ids
):
    response = client.post(
        ORDERS_URL,
        json={"product_ids": product_ids, "delivery_address": ENDERECO},
        headers=auth_headers(cenario["buyer"].id),
    )

    assert response.status_code == 422


@pytest.mark.postgres
def test_duas_pessoas_na_mesma_peca_ao_mesmo_tempo_so_uma_consegue(
    pg_engine: Engine,
):
    """As duas leem a peça como `ativo` e chegam juntas ao UPDATE. O Postgres
    segura a segunda até a primeira terminar, e aí ela já não encontra `ativo`.

    Não usa `pg_session`: aquela fixture põe tudo numa transação só, e a disputa
    precisa de duas conexões de verdade, cada uma com o seu commit.
    """
    with Session(pg_engine) as db:
        loja = make_store(db, "Disputa", "44444444444")
        peca = make_product(db, loja, "Casaco disputado", "120.00")
        compradores = [make_user(db, f"disputa{n}@test.local").id for n in range(2)]
        db.commit()
        ids = {
            "loja": loja.id,
            "seller": loja.seller_id,
            "dono": loja.seller.user_id,
            "peca": peca.id,
        }

    largada = threading.Barrier(2)
    resultados: list[str] = []

    def comprar(buyer_id: int) -> None:
        with Session(pg_engine) as db:
            controller = OrderController(db)
            data = OrderCreate(product_ids=[ids["peca"]], delivery_address=ENDERECO)
            largada.wait()
            try:
                controller.create(buyer_id, data)
                resultados.append("criado")
            except Conflict as erro:
                resultados.append(erro.code)

    threads = [threading.Thread(target=comprar, args=(b,)) for b in compradores]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert sorted(resultados) == ["PIECE_UNAVAILABLE", "criado"]
        with Session(pg_engine) as db:
            pedidos = db.scalars(select(Order).where(Order.store_id == ids["loja"]))
            assert len(pedidos.all()) == 1
            assert db.get(Product, ids["peca"]).status == "reservado"
    finally:
        with Session(pg_engine) as db:
            pedidos = select(Order.id).where(Order.store_id == ids["loja"])
            db.execute(
                delete(OrderStatusHistory).where(
                    OrderStatusHistory.order_id.in_(pedidos)
                )
            )
            db.execute(delete(OrderItem).where(OrderItem.order_id.in_(pedidos)))
            db.execute(delete(Order).where(Order.store_id == ids["loja"]))
            db.execute(
                delete(ProductImage).where(ProductImage.product_id == ids["peca"])
            )
            db.execute(delete(Product).where(Product.id == ids["peca"]))
            db.execute(delete(Store).where(Store.id == ids["loja"]))
            db.execute(delete(Seller).where(Seller.id == ids["seller"]))
            db.execute(delete(User).where(User.id.in_([ids["dono"], *compradores])))
            db.commit()
