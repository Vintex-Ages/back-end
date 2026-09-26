"""Repository e controller de loja pública (BE-US007-2, back-end#142)."""

from decimal import Decimal

from app.models.address import Address
from app.models.product import Product
from app.models.seller import Seller
from app.models.store import Store
from app.models.user import User
from app.repositories.store_repository import StoreRepository


def persist_store(
    db_session,
    name: str = "Brechó Teste",
    verified: bool = False,
    with_address: bool = True,
) -> Store:
    user = User(
        name=f"{name} owner",
        email=f"{name.lower().replace(' ', '.')}@test.local",
        password_hash="not-a-real-password",
    )
    seller = Seller(
        user=user,
        document_type="CPF",
        document_value=str(abs(hash(name)))[:11].zfill(11),
        verified=verified,
    )
    address = (
        Address(
            street="Rua Sete de Setembro",
            number="1020",
            neighborhood="Centro Histórico",
            city="Porto Alegre",
            state="RS",
            zip_code="90010-190",
        )
        if with_address
        else None
    )
    store = Store(
        name=name, description="Peças de segunda mão.", seller=seller, address=address
    )
    db_session.add(store)
    db_session.commit()
    db_session.refresh(store)
    return store


def persist_product(
    db_session, store: Store, status: str = "ativo", price: str = "99.90"
) -> Product:
    product = Product(store=store, name="Jaqueta", price=Decimal(price), status=status)
    db_session.add(product)
    db_session.commit()
    return product


def test_get_by_id_devolve_loja_com_seller_e_address(db_session):
    store = persist_store(db_session, verified=True)

    encontrada = StoreRepository(db_session).get_by_id(store.id)

    assert encontrada is not None
    assert encontrada.seller.verified is True
    assert encontrada.address.city == "Porto Alegre"


def test_get_by_id_devolve_none_para_loja_inexistente(db_session):
    encontrada = StoreRepository(db_session).get_by_id(999999)

    assert encontrada is None


def test_get_metrics_conta_anunciadas_e_vendidas(db_session):
    store = persist_store(db_session)
    persist_product(db_session, store, status="ativo")
    persist_product(db_session, store, status="vendido")
    persist_product(db_session, store, status="despublicado")

    metrics = StoreRepository(db_session).get_metrics(store.id)

    assert metrics["products_listed"] == 3
    assert metrics["products_sold"] == 1


def test_get_metrics_sem_pecas_devolve_zero(db_session):
    store = persist_store(db_session)

    metrics = StoreRepository(db_session).get_metrics(store.id)

    assert metrics["products_listed"] == 0
    assert metrics["products_sold"] == 0


def test_active_products_query_so_traz_pecas_ativas_da_loja(db_session):
    store = persist_store(db_session, name="Brechó A")
    outra_loja = persist_store(db_session, name="Brechó B")
    ativo = persist_product(db_session, store, status="ativo")
    persist_product(db_session, store, status="vendido")
    persist_product(db_session, outra_loja, status="ativo")

    stmt = StoreRepository(db_session).active_products_query(store.id)
    resultado = db_session.scalars(stmt).all()

    assert [p.id for p in resultado] == [ativo.id]
