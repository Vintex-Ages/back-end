"""Avaliação da loja por estrelas (back-end#267).

"Pedido entregue" é o status derivado `concluido`: três dias depois da
aprovação do comprovante (RN-83 simula a entrega). Os testes recuam a data da
aprovação no histórico em vez de esperar, que é o que a leitura do pedido
olha.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import utcnow_naive
from app.models import (
    Order,
    OrderItem,
    OrderStatusHistory,
    Product,
    Seller,
    Store,
    StoreRating,
    User,
)

STORES_URL = "/api/stores"


def make_user(db: Session, email: str) -> User:
    user = User(name=email, email=email, password_hash="not-a-real-password")
    db.add(user)
    db.flush()
    return user


def make_store(db: Session, name: str, document: str) -> Store:
    store = Store(
        name=name,
        pix_key=f"{name}@pix",
        seller=Seller(
            user=make_user(db, f"{document}@loja.test"),
            document_type="CPF",
            document_value=document,
        ),
    )
    db.add(store)
    db.flush()
    return store


def make_order(
    db: Session,
    buyer: User,
    store: Store,
    *,
    aprovado_ha: timedelta | None = timedelta(days=4),
) -> Order:
    """Pedido de uma peça vendida. `aprovado_ha` é há quanto tempo o
    comprovante foi aprovado; `None` deixa o pedido aguardando comprovante."""
    product = Product(
        store=store, name="Jaqueta", price=Decimal("100.00"), status="vendido"
    )
    db.add(product)
    db.flush()
    agora = utcnow_naive()
    history = [OrderStatusHistory(status="aguardando_comprovante", changed_at=agora)]
    if aprovado_ha is not None:
        history.append(
            OrderStatusHistory(status="confirmado", changed_at=agora - aprovado_ha)
        )
    order = Order(
        buyer_id=buyer.id,
        store_id=store.id,
        status="aguardando_comprovante" if aprovado_ha is None else "confirmado",
        product_amount=Decimal("100.00"),
        commission_rate=Decimal("0.0900"),
        platform_fee=Decimal("9.00"),
        total_amount=Decimal("100.00"),
        expires_at=agora + timedelta(days=3),
        delivery_street="Rua dos Andradas",
        delivery_number="100",
        delivery_city="Porto Alegre",
        delivery_state="RS",
        delivery_zip_code="90020000",
        items=[
            OrderItem(
                store_id=store.id,
                product_id=product.id,
                name=product.name,
                price=product.price,
            )
        ],
        status_history=history,
    )
    db.add(order)
    db.commit()
    return order


@pytest.fixture
def cenario(db_session):
    aurora = make_store(db_session, "Aurora", "52998224725")
    outra_loja = make_store(db_session, "Bazar", "11144477735")
    compradora = make_user(db_session, "compradora@test.local")
    db_session.commit()
    return {"aurora": aurora, "outra_loja": outra_loja, "compradora": compradora}


@pytest.fixture
def avaliar(client, auth_headers):
    def _avaliar(user: User, store: Store, order_id: int, score: object = 5):
        return client.post(
            f"{STORES_URL}/{store.id}/ratings",
            json={"order_id": order_id, "score": score},
            headers=auth_headers(user.id),
        )

    return _avaliar


def perfil(client, store: Store) -> dict:
    return client.get(f"{STORES_URL}/{store.id}").json()["metrics"]


# --- avaliar ---------------------------------------------------------------------


def test_quem_recebeu_o_pedido_avalia_a_loja(db_session, cenario, avaliar):
    pedido = make_order(db_session, cenario["compradora"], cenario["aurora"])

    resposta = avaliar(cenario["compradora"], cenario["aurora"], pedido.id, 4)

    assert resposta.status_code == 201
    body = resposta.json()
    assert (body["store_id"], body["order_id"], body["score"]) == (
        cenario["aurora"].id,
        pedido.id,
        4,
    )
    assert body["created_at"]
    gravada = db_session.scalar(select(StoreRating))
    assert gravada is not None
    assert gravada.author_id == cenario["compradora"].id


def test_avaliar_o_mesmo_pedido_duas_vezes_responde_409(db_session, cenario, avaliar):
    pedido = make_order(db_session, cenario["compradora"], cenario["aurora"])
    avaliar(cenario["compradora"], cenario["aurora"], pedido.id, 5)

    resposta = avaliar(cenario["compradora"], cenario["aurora"], pedido.id, 1)

    assert resposta.status_code == 409
    assert resposta.json()["error"]["code"] == "ALREADY_RATED"
    assert db_session.scalars(select(StoreRating.score)).all() == [5]


def test_dois_pedidos_entregues_da_mesma_loja_avaliam_duas_vezes(
    db_session, cenario, avaliar
):
    """Uma por pedido, não uma por pessoa (RN-76)."""
    primeiro = make_order(db_session, cenario["compradora"], cenario["aurora"])
    segundo = make_order(db_session, cenario["compradora"], cenario["aurora"])

    assert (
        avaliar(cenario["compradora"], cenario["aurora"], primeiro.id).status_code
        == 201
    )
    assert (
        avaliar(cenario["compradora"], cenario["aurora"], segundo.id).status_code == 201
    )


# --- quem não pode avaliar -------------------------------------------------------


def test_quem_nao_comprou_recebe_403(db_session, cenario, avaliar):
    pedido = make_order(db_session, cenario["compradora"], cenario["aurora"])
    curiosa = make_user(db_session, "curiosa@test.local")
    db_session.commit()

    resposta = avaliar(curiosa, cenario["aurora"], pedido.id)

    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "RATING_NOT_ALLOWED"


@pytest.mark.parametrize(
    ("aprovado_ha", "situacao"),
    [
        (None, "aguardando comprovante"),
        (timedelta(hours=1), "recém-aprovado"),
        (timedelta(days=2), "enviado, ainda não entregue"),
    ],
)
def test_pedido_ainda_nao_entregue_recebe_403(
    db_session, cenario, avaliar, aprovado_ha, situacao
):
    pedido = make_order(
        db_session, cenario["compradora"], cenario["aurora"], aprovado_ha=aprovado_ha
    )

    resposta = avaliar(cenario["compradora"], cenario["aurora"], pedido.id)

    assert resposta.status_code == 403, situacao
    assert db_session.scalar(select(StoreRating)) is None


def test_pedido_de_outra_loja_nao_avalia_esta(db_session, cenario, avaliar):
    pedido = make_order(db_session, cenario["compradora"], cenario["outra_loja"])

    resposta = avaliar(cenario["compradora"], cenario["aurora"], pedido.id)

    assert resposta.status_code == 403


def test_pedido_inexistente_responde_como_pedido_alheio(cenario, avaliar):
    """Mesma resposta de quem não comprou: uma diferente confirmaria o id."""
    resposta = avaliar(cenario["compradora"], cenario["aurora"], 999)

    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "RATING_NOT_ALLOWED"


def test_loja_inexistente_responde_404(cenario, client, auth_headers):
    resposta = client.post(
        f"{STORES_URL}/999/ratings",
        json={"order_id": 1, "score": 5},
        headers=auth_headers(cenario["compradora"].id),
    )

    assert resposta.status_code == 404
    assert resposta.json()["error"]["code"] == "STORE_NOT_FOUND"


@pytest.mark.parametrize("score", [0, 6, -1, "cinco", None, 4.5])
def test_nota_fora_de_1_a_5_responde_422(db_session, cenario, avaliar, score):
    pedido = make_order(db_session, cenario["compradora"], cenario["aurora"])

    resposta = avaliar(cenario["compradora"], cenario["aurora"], pedido.id, score)

    assert resposta.status_code == 422
    assert "score" in resposta.json()["error"]["fields"]


def test_comentario_nao_e_aceito_nem_gravado(db_session, cenario, client, auth_headers):
    """Só estrelas (RN-75): o campo a mais é ignorado e não há onde gravá-lo."""
    pedido = make_order(db_session, cenario["compradora"], cenario["aurora"])

    resposta = client.post(
        f"{STORES_URL}/{cenario['aurora'].id}/ratings",
        json={"order_id": pedido.id, "score": 5, "comment": "Amei!"},
        headers=auth_headers(cenario["compradora"].id),
    )

    assert resposta.status_code == 201
    assert "comment" not in resposta.json()
    assert "comment" not in StoreRating.__table__.columns


def test_sem_token_responde_401(client, cenario):
    resposta = client.post(
        f"{STORES_URL}/{cenario['aurora'].id}/ratings",
        json={"order_id": 1, "score": 5},
    )

    assert resposta.status_code == 401
    assert resposta.json()["error"]["code"] == "AUTH_REQUIRED"


# --- perfil da loja --------------------------------------------------------------


def test_perfil_mostra_a_media_e_a_contagem_de_tres_notas(
    client, db_session, cenario, avaliar
):
    for nota in (5, 4, 4):
        pedido = make_order(db_session, cenario["compradora"], cenario["aurora"])
        assert avaliar(cenario["compradora"], cenario["aurora"], pedido.id, nota)

    metrics = perfil(client, cenario["aurora"])

    # 13 / 3 = 4,333..., com uma casa.
    assert (metrics["rating"], metrics["rating_count"]) == (4.3, 3)


def test_loja_sem_avaliacao_devolve_media_nula_e_nao_zero(client, cenario):
    metrics = perfil(client, cenario["aurora"])

    assert metrics["rating"] is None
    assert metrics["rating_count"] == 0


def test_nota_de_uma_loja_nao_entra_na_media_da_outra(
    client, db_session, cenario, avaliar
):
    pedido = make_order(db_session, cenario["compradora"], cenario["outra_loja"])
    avaliar(cenario["compradora"], cenario["outra_loja"], pedido.id, 1)

    assert perfil(client, cenario["aurora"])["rating"] is None
    assert perfil(client, cenario["outra_loja"])["rating"] == 1.0


# --- banco -----------------------------------------------------------------------


@pytest.mark.parametrize("score", [0, 6])
def test_nota_fora_de_1_a_5_e_recusada_pelo_banco(db_session, cenario, score):
    """O CHECK, e não só o schema: gravar direto pelo model também falha."""
    pedido = make_order(db_session, cenario["compradora"], cenario["aurora"])
    db_session.add(
        StoreRating(
            order_id=pedido.id,
            store_id=cenario["aurora"].id,
            author_id=cenario["compradora"].id,
            score=score,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.postgres
def test_check_e_unique_valem_no_postgres(pg_session):
    """A tabela criada pela migration recusa nota fora da faixa e o segundo
    voto no mesmo pedido."""
    aurora = make_store(pg_session, "Aurora", "52998224725")
    compradora = make_user(pg_session, "compradora@test.local")
    pedido = make_order(pg_session, compradora, aurora)

    def nota(score: int) -> StoreRating:
        return StoreRating(
            order_id=pedido.id,
            store_id=aurora.id,
            author_id=compradora.id,
            score=score,
        )

    with pytest.raises(IntegrityError):
        with pg_session.begin_nested():
            pg_session.add(nota(6))
            pg_session.flush()

    pg_session.add(nota(5))
    pg_session.flush()
    with pytest.raises(IntegrityError):
        with pg_session.begin_nested():
            pg_session.add(nota(4))
            pg_session.flush()
