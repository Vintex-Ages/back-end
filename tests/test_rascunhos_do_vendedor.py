"""Listar e descartar os rascunhos do vendedor (BE-US019-7, back-end#271).

O rascunho existe no banco porque guarda o andamento da análise de IA
(`ai_status`/`ai_suggestions`), mas não aparecia em tela nenhuma: a listagem do
painel não deixava filtrar por ele. Cada critério de aceite da issue tem um
teste aqui.
"""

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.models.product import Product
from app.models.product_ai_correction import ProductAiCorrection
from app.models.product_image import ProductImage
from app.models.seller import Seller
from app.models.store import Store
from app.models.user import User

PECAS_URL = "/api/users/me/products"
FOTO = "https://cdn.test/rascunho.jpg"


def _vendedor(db, *, email: str) -> tuple[User, Store]:
    """Vendedora com loja. O documento é único porque `sellers` tem `UQ` nele."""
    user = User(name="Vendedora", email=email, password_hash="x")
    db.add(user)
    db.flush()
    seller = Seller(
        user_id=user.id,
        document_type="CPF",
        document_value=f"{user.id:011d}",
    )
    db.add(seller)
    db.flush()
    store = Store(seller_id=seller.id, name=f"Brechó de {email}")
    db.add(store)
    db.flush()
    return user, store


def _peca(db, store: Store, **kwargs) -> Product:
    dados = dict(
        store_id=store.id,
        name="Jaqueta jeans",
        price=Decimal("100.00"),
        quantity=1,
        status="ativo",
    )
    dados.update(kwargs)
    product = Product(**dados)
    db.add(product)
    db.flush()
    return product


def _h(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.is_admin)}"}


def _contar(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def test_filtro_de_rascunho_lista_so_rascunho(client, db_session):
    """A aba de rascunhos pede `?status=rascunho` e recebe só o que é rascunho."""
    user, store = _vendedor(db_session, email="lista.rascunho@v.com")
    _peca(db_session, store, name="Anunciada", status="ativo")
    _peca(db_session, store, name="Vendida", status="vendido")
    rascunho = _peca(db_session, store, name="Rascunho", status="rascunho")
    db_session.add(ProductImage(product=rascunho, image_url=FOTO, position=0))
    db_session.commit()

    resposta = client.get(f"{PECAS_URL}?status=rascunho", headers=_h(user))

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["total"] == 1
    assert [item["id"] for item in corpo["items"]] == [rascunho.id]
    assert corpo["items"][0]["status"] == "rascunho"
    # A aba mostra nome e foto; rascunho sem foto vem com capa nula.
    assert corpo["items"][0]["name"] == "Rascunho"
    assert corpo["items"][0]["cover_image_url"] == FOTO


def test_sem_filtro_a_listagem_continua_sem_rascunho(client, db_session):
    """RN-51: rascunho entra separado, nunca misturado ao que está no ar."""
    user, store = _vendedor(db_session, email="sem.filtro@v.com")
    ativa = _peca(db_session, store, name="Anunciada", status="ativo")
    vendida = _peca(db_session, store, name="Vendida", status="vendido")
    fora = _peca(db_session, store, name="Fora do ar", status="despublicado")
    reservada = _peca(db_session, store, name="Reservada", status="reservado")
    _peca(db_session, store, name="Rascunho", status="rascunho")
    db_session.commit()

    corpo = client.get(PECAS_URL, headers=_h(user)).json()

    assert corpo["total"] == 4
    assert {item["id"] for item in corpo["items"]} == {
        ativa.id,
        vendida.id,
        fora.id,
        reservada.id,
    }
    assert all(item["status"] != "rascunho" for item in corpo["items"])

    # Os filtros que já existiam continuam valendo.
    ativos = client.get(f"{PECAS_URL}?status=ativo", headers=_h(user)).json()
    assert ativos["total"] == 1
    assert ativos["items"][0]["id"] == ativa.id


def test_descartar_rascunho_apaga_a_peca_as_fotos_e_as_correcoes(client, db_session):
    """Descartar é apagar: peça, imagens e correções da IA, e nada mais."""
    user, store = _vendedor(db_session, email="descarta@v.com")
    anunciada = _peca(db_session, store, name="Anunciada", status="ativo")
    rascunho = _peca(
        db_session,
        store,
        name="Rascunho",
        status="rascunho",
        ai_status="done",
        ai_suggestions={"category": "Vestidos"},
    )
    db_session.add_all(
        [
            ProductImage(product=rascunho, image_url=FOTO, position=0),
            ProductImage(product=rascunho, image_url=FOTO, position=1),
            ProductAiCorrection(
                product=rascunho,
                field="category",
                suggested="Vestidos",
                final="Vestido longo",
            ),
        ]
    )
    db_session.commit()
    id_do_rascunho = rascunho.id

    resposta = client.delete(f"{PECAS_URL}/{id_do_rascunho}", headers=_h(user))

    assert resposta.status_code == 204
    assert resposta.content == b""
    assert db_session.get(Product, id_do_rascunho) is None
    assert _contar(db_session, ProductImage) == 0
    assert _contar(db_session, ProductAiCorrection) == 0

    # Sumiu da lista e da tela de edição; a anunciada continua lá.
    assert (
        client.get(f"{PECAS_URL}/{id_do_rascunho}", headers=_h(user)).status_code == 404
    )
    assert (
        client.get(f"{PECAS_URL}?status=rascunho", headers=_h(user)).json()["total"]
        == 0
    )
    assert (
        client.get(f"{PECAS_URL}?status=ativo", headers=_h(user)).json()["total"] == 1
    )
    assert db_session.get(Product, anunciada.id) is not None


@pytest.mark.parametrize(
    ("status", "codigo"),
    [
        ("ativo", "PRODUCT_NOT_EDITABLE"),
        ("despublicado", "PRODUCT_NOT_EDITABLE"),
        ("reservado", "PRODUCT_NOT_EDITABLE"),
        ("vendido", "PRODUCT_SOLD"),
    ],
)
def test_descartar_peca_que_nao_e_rascunho_e_recusado(
    client, db_session, status, codigo
):
    """Peça publicada não se descarta; vendida responde com o código próprio."""
    user, store = _vendedor(db_session, email=f"nao.descarta.{status}@v.com")
    peca = _peca(db_session, store, status=status)
    db_session.commit()

    resposta = client.delete(f"{PECAS_URL}/{peca.id}", headers=_h(user))

    assert resposta.status_code == 409
    assert resposta.json()["error"]["code"] == codigo
    assert db_session.get(Product, peca.id) is not None


def test_descartar_rascunho_de_outro_vendedor_responde_404(client, db_session):
    """404 e não 403: um 403 confirmaria que aquele id existe."""
    _dona, loja_da_dona = _vendedor(db_session, email="dona@v.com")
    intrusa, _ = _vendedor(db_session, email="intrusa@v.com")
    rascunho = _peca(db_session, loja_da_dona, status="rascunho")
    db_session.commit()

    resposta = client.delete(f"{PECAS_URL}/{rascunho.id}", headers=_h(intrusa))

    assert resposta.status_code == 404
    assert resposta.json()["error"]["code"] == "PRODUCT_NOT_FOUND"
    assert db_session.get(Product, rascunho.id) is not None


def test_listagem_de_rascunho_nao_mostra_peca_de_outro_vendedor(client, db_session):
    """A listagem não responde 404: o filtro é sempre do próprio vendedor, e o
    rascunho alheio simplesmente não aparece."""
    _dona, loja_da_dona = _vendedor(db_session, email="dona.lista@v.com")
    intrusa, _ = _vendedor(db_session, email="intrusa.lista@v.com")
    _peca(db_session, loja_da_dona, status="rascunho")
    db_session.commit()

    corpo = client.get(f"{PECAS_URL}?status=rascunho", headers=_h(intrusa)).json()

    assert corpo["total"] == 0
    assert corpo["items"] == []


def test_descartar_rascunho_inexistente_responde_404(client, db_session):
    user, _ = _vendedor(db_session, email="inexistente@v.com")

    resposta = client.delete(f"{PECAS_URL}/999999", headers=_h(user))

    assert resposta.status_code == 404
    assert resposta.json()["error"]["code"] == "PRODUCT_NOT_FOUND"
