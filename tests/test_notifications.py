"""Avisos in-app: a venda ao vendedor e o favorito ao anunciante (back-end#261).

Os dois eventos da RN-85 passam pelas rotas de verdade: a aprovação do
comprovante (`/api/admin/payments/{id}/approve`, #251) e o favorito
(`/api/users/me/favorites/{id}`, #252). Nada é enviado para fora (RN-84): não
há cliente de e-mail nem de push para conferir, só a linha no banco.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.controllers.order_controller import OrderController
from app.models import (
    Notification,
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

NOTIFICATIONS_URL = "/api/users/me/notifications"
FAVORITES_URL = "/api/users/me/favorites"

ENDERECO = {
    "zip_code": "90020000",
    "street": "Rua dos Andradas",
    "number": "100",
    "city": "Porto Alegre",
    "state": "RS",
}


def make_user(db: Session, email: str, *, is_admin: bool = False) -> User:
    user = User(
        name=email.split("@")[0],
        email=email,
        password_hash="not-a-real-password",
        is_admin=is_admin,
    )
    db.add(user)
    db.flush()
    return user


def make_product(db: Session, store: Store, name: str) -> Product:
    product = Product(
        store=store,
        name=name,
        price=Decimal("100.00"),
        status="ativo",
        images=[ProductImage(image_url=f"https://cdn.test/{name}.jpg", position=0)],
    )
    db.add(product)
    db.flush()
    return product


def montar_cenario(db: Session) -> dict:
    """A loja Aurora com duas peças, duas compradoras e a administradora."""
    vendedora = make_user(db, "aurora@loja.test")
    aurora = Store(
        name="Aurora",
        pix_key="aurora@pix",
        seller=Seller(
            user=vendedora, document_type="CPF", document_value="52998224725"
        ),
    )
    db.add(aurora)
    db.flush()
    jaqueta = make_product(db, aurora, "Jaqueta")
    saia = make_product(db, aurora, "Saia")
    compradora = make_user(db, "compradora@test.local")
    outra = make_user(db, "outra@test.local")
    admin = make_user(db, "admin@test.local", is_admin=True)
    db.commit()
    return {
        "vendedora": vendedora,
        "jaqueta": jaqueta,
        "saia": saia,
        "compradora": compradora,
        "outra": outra,
        "admin": admin,
    }


@pytest.fixture
def cenario(db_session):
    return montar_cenario(db_session)


def pedido_em_analise(db: Session, compradora: User, pecas: list[Product]) -> Order:
    """Pedido criado e com comprovante enviado, como a #249 deixa."""
    resposta = OrderController(db).create(
        compradora.id,
        OrderCreate(product_ids=[peca.id for peca in pecas], delivery_address=ENDERECO),
    )
    order = db.get(Order, resposta.id)
    assert order is not None
    order.status = "em_analise"
    db.add(OrderStatusHistory(order_id=order.id, status="em_analise"))
    db.add(Payment(order_id=order.id, receipt_key=f"payments/receipts/{order.id}"))
    db.commit()
    return order


def listar(client, auth_headers, user: User, **params):
    return client.get(NOTIFICATIONS_URL, params=params, headers=auth_headers(user.id))


def favoritar(client, auth_headers, user: User, product: Product):
    return client.put(f"{FAVORITES_URL}/{product.id}", headers=auth_headers(user.id))


def avisos_no_banco(db: Session) -> list[Notification]:
    return list(db.scalars(select(Notification).order_by(Notification.id)))


# --- venda -----------------------------------------------------------------------


def test_aprovar_o_comprovante_avisa_a_vendedora_da_venda(
    client, db_session, cenario, auth_headers
):
    pedido = pedido_em_analise(
        db_session, cenario["compradora"], [cenario["jaqueta"], cenario["saia"]]
    )

    resposta = client.post(
        f"/api/admin/payments/{pedido.id}/approve",
        headers=auth_headers(cenario["admin"].id, is_admin=True),
    )
    assert resposta.status_code == 200

    body = listar(client, auth_headers, cenario["vendedora"]).json()
    assert body["total"] == 1
    assert body["unread_count"] == 1
    aviso = body["items"][0]
    assert aviso["type"] == "sale"
    assert aviso["order_id"] == pedido.id
    # Um aviso por pedido, com a primeira peça dele.
    assert aviso["product_id"] == cenario["jaqueta"].id
    assert aviso["product_name"] == "Jaqueta"
    assert aviso["is_read"] is False
    assert aviso["created_at"]


def test_criar_o_pedido_e_rejeitar_o_comprovante_nao_avisam(
    client, db_session, cenario, auth_headers
):
    """A venda só se confirma na aprovação (RN-21): checkout não é venda."""
    pedido = pedido_em_analise(db_session, cenario["compradora"], [cenario["jaqueta"]])
    assert avisos_no_banco(db_session) == []

    client.post(
        f"/api/admin/payments/{pedido.id}/reject",
        headers=auth_headers(cenario["admin"].id, is_admin=True),
        json={"reason": "Comprovante ilegível."},
    )

    assert avisos_no_banco(db_session) == []


# --- favorito --------------------------------------------------------------------


def test_favoritar_avisa_a_dona_da_peca(client, cenario, auth_headers):
    assert favoritar(client, auth_headers, cenario["compradora"], cenario["saia"])

    body = listar(client, auth_headers, cenario["vendedora"]).json()
    assert body["unread_count"] == 1
    aviso = body["items"][0]
    assert (aviso["type"], aviso["product_id"], aviso["product_name"]) == (
        "favorite",
        cenario["saia"].id,
        "Saia",
    )
    assert aviso["order_id"] is None
    # O anunciante sabe que alguém favoritou, não quem.
    assert "actor_id" not in aviso


def test_desfavoritar_nao_avisa_e_favoritar_de_novo_nao_duplica(
    client, db_session, cenario, auth_headers
):
    compradora, saia = cenario["compradora"], cenario["saia"]
    favoritar(client, auth_headers, compradora, saia)
    client.delete(f"{FAVORITES_URL}/{saia.id}", headers=auth_headers(compradora.id))
    favoritar(client, auth_headers, compradora, saia)
    favoritar(client, auth_headers, compradora, saia)

    assert len(avisos_no_banco(db_session)) == 1


def test_duas_pessoas_favoritando_geram_dois_avisos(
    client, db_session, cenario, auth_headers
):
    favoritar(client, auth_headers, cenario["compradora"], cenario["saia"])
    favoritar(client, auth_headers, cenario["outra"], cenario["saia"])

    assert len(avisos_no_banco(db_session)) == 2


def test_vendedora_favoritando_a_propria_peca_nao_e_avisada(
    client, db_session, cenario, auth_headers
):
    resposta = favoritar(client, auth_headers, cenario["vendedora"], cenario["saia"])

    assert resposta.status_code == 204
    assert avisos_no_banco(db_session) == []


def test_favorito_recusado_nao_avisa(client, db_session, cenario, auth_headers):
    cenario["saia"].status = "rascunho"
    db_session.commit()

    resposta = favoritar(client, auth_headers, cenario["compradora"], cenario["saia"])

    assert resposta.status_code == 404
    assert avisos_no_banco(db_session) == []


# --- leitura ---------------------------------------------------------------------


def test_lista_vem_do_mais_recente_para_o_mais_antigo(client, cenario, auth_headers):
    favoritar(client, auth_headers, cenario["compradora"], cenario["jaqueta"])
    favoritar(client, auth_headers, cenario["compradora"], cenario["saia"])

    body = listar(client, auth_headers, cenario["vendedora"]).json()

    assert [item["product_id"] for item in body["items"]] == [
        cenario["saia"].id,
        cenario["jaqueta"].id,
    ]


def test_contagem_de_nao_lidas_vale_para_todas_as_paginas(
    client, cenario, auth_headers
):
    favoritar(client, auth_headers, cenario["compradora"], cenario["jaqueta"])
    favoritar(client, auth_headers, cenario["compradora"], cenario["saia"])
    favoritar(client, auth_headers, cenario["outra"], cenario["saia"])

    body = listar(
        client, auth_headers, cenario["vendedora"], page=1, page_size=1
    ).json()

    assert len(body["items"]) == 1
    assert (body["total"], body["unread_count"]) == (3, 3)
    assert (body["page"], body["page_size"]) == (1, 1)


def test_quem_nao_tem_aviso_recebe_lista_vazia(client, cenario, auth_headers):
    body = listar(client, auth_headers, cenario["compradora"]).json()

    assert body == {
        "items": [],
        "page": 1,
        "page_size": 20,
        "total": 0,
        "unread_count": 0,
    }


# --- marcar como lida ------------------------------------------------------------


def test_marcar_uma_como_lida(client, cenario, auth_headers):
    favoritar(client, auth_headers, cenario["compradora"], cenario["jaqueta"])
    favoritar(client, auth_headers, cenario["compradora"], cenario["saia"])
    vendedora = cenario["vendedora"]
    mais_recente = listar(client, auth_headers, vendedora).json()["items"][0]

    resposta = client.post(
        f"{NOTIFICATIONS_URL}/{mais_recente['id']}/read",
        headers=auth_headers(vendedora.id),
    )

    assert resposta.status_code == 204
    body = listar(client, auth_headers, vendedora).json()
    assert [item["is_read"] for item in body["items"]] == [True, False]
    assert body["unread_count"] == 1


def test_marcar_de_novo_responde_204_e_guarda_a_primeira_leitura(
    client, db_session, cenario, auth_headers
):
    favoritar(client, auth_headers, cenario["compradora"], cenario["saia"])
    vendedora = cenario["vendedora"]
    aviso = avisos_no_banco(db_session)[0]
    url = f"{NOTIFICATIONS_URL}/{aviso.id}/read"

    assert client.post(url, headers=auth_headers(vendedora.id)).status_code == 204
    db_session.refresh(aviso)
    lida_em = aviso.read_at
    assert client.post(url, headers=auth_headers(vendedora.id)).status_code == 204

    db_session.refresh(aviso)
    assert aviso.read_at == lida_em


def test_marcar_todas_como_lidas(client, cenario, auth_headers):
    favoritar(client, auth_headers, cenario["compradora"], cenario["jaqueta"])
    favoritar(client, auth_headers, cenario["compradora"], cenario["saia"])
    vendedora = cenario["vendedora"]

    resposta = client.post(
        f"{NOTIFICATIONS_URL}/read", headers=auth_headers(vendedora.id)
    )

    assert resposta.status_code == 204
    body = listar(client, auth_headers, vendedora).json()
    assert body["unread_count"] == 0
    assert all(item["is_read"] for item in body["items"])


def test_marcar_inexistente_responde_404(client, cenario, auth_headers):
    resposta = client.post(
        f"{NOTIFICATIONS_URL}/999/read", headers=auth_headers(cenario["vendedora"].id)
    )

    assert resposta.status_code == 404
    assert resposta.json()["error"]["code"] == "NOTIFICATION_NOT_FOUND"


# --- isolamento ------------------------------------------------------------------


def test_aviso_de_outra_pessoa_nao_aparece_nem_pode_ser_marcado(
    client, db_session, cenario, auth_headers
):
    favoritar(client, auth_headers, cenario["compradora"], cenario["saia"])
    aviso = avisos_no_banco(db_session)[0]
    intrusa = cenario["outra"]

    assert listar(client, auth_headers, intrusa).json()["total"] == 0
    resposta = client.post(
        f"{NOTIFICATIONS_URL}/{aviso.id}/read", headers=auth_headers(intrusa.id)
    )
    # 404 e não 403: um 403 confirmaria que o id existe.
    assert resposta.status_code == 404
    client.post(f"{NOTIFICATIONS_URL}/read", headers=auth_headers(intrusa.id))

    db_session.refresh(aviso)
    assert aviso.read_at is None


@pytest.mark.parametrize(
    ("metodo", "caminho"),
    [
        ("get", NOTIFICATIONS_URL),
        ("post", f"{NOTIFICATIONS_URL}/read"),
        ("post", f"{NOTIFICATIONS_URL}/1/read"),
    ],
)
def test_sem_token_as_tres_rotas_respondem_401(client, db_session, metodo, caminho):
    """Exige login (RN-27), com o corpo das outras ações protegidas."""
    resposta = getattr(client, metodo)(caminho)

    assert resposta.status_code == 401
    assert resposta.json()["error"]["code"] == "AUTH_REQUIRED"


# --- banco -----------------------------------------------------------------------


@pytest.mark.postgres
def test_favoritar_de_novo_no_postgres_nao_duplica_o_aviso(
    pg_client, pg_session, auth_headers
):
    """O `ON CONFLICT` no índice único parcial criado pela migration."""
    cenario = montar_cenario(pg_session)
    headers = auth_headers(cenario["compradora"].id)
    url = f"{FAVORITES_URL}/{cenario['saia'].id}"

    assert pg_client.put(url, headers=headers).status_code == 204
    assert pg_client.delete(url, headers=headers).status_code == 204
    assert pg_client.put(url, headers=headers).status_code == 204

    body = pg_client.get(
        NOTIFICATIONS_URL, headers=auth_headers(cenario["vendedora"].id)
    ).json()
    assert body["total"] == 1


@pytest.mark.postgres
def test_tipo_fora_da_lista_e_recusado_pelo_banco(pg_session):
    from sqlalchemy.exc import IntegrityError

    cenario = montar_cenario(pg_session)
    pg_session.add(
        Notification(
            user_id=cenario["vendedora"].id,
            type="email",
            product_id=cenario["saia"].id,
        )
    )
    with pytest.raises(IntegrityError):
        pg_session.flush()
