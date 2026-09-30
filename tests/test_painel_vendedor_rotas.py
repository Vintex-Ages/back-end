"""GET da peça do vendedor (#234) e resumo financeiro por período (#146).

As duas rotas que o front da Sprint 2 já chama e que não existiam: o painel
mostrava "ainda não disponível" no resumo, e a tela de edição não carregava a
peça. Cada critério de aceite das duas issues tem um teste aqui.
"""

from datetime import timedelta
from decimal import Decimal

from app.core.clock import utcnow_naive
from app.models.product import Product
from app.models.seller import Seller
from app.models.store import Store
from app.models.user import User

PECAS_URL = "/api/users/me/products"
RESUMO_URL = "/api/users/me/sales/summary"


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
    return {"X-User-Id": str(user.id)}


# --------------------------------------------------------------------- #234


def test_get_da_peca_devolve_rascunho(client, db_session):
    user, store = _vendedor(db_session, email="a@v.com")
    peca = _peca(db_session, store, status="rascunho", name="Rascunho")

    r = client.get(f"{PECAS_URL}/{peca.id}", headers=_h(user))

    assert r.status_code == 200
    corpo = r.json()
    assert corpo["status"] == "rascunho"
    assert corpo["name"] == "Rascunho"
    # O mapeador do front lê os três; sem eles a tela de edição quebra.
    assert corpo["store"]["id"] == store.id
    assert corpo["images"] == []
    assert corpo["ai_corrections"] == []


def test_get_da_peca_devolve_despublicada(client, db_session):
    user, store = _vendedor(db_session, email="b@v.com")
    peca = _peca(db_session, store, status="despublicado")

    r = client.get(f"{PECAS_URL}/{peca.id}", headers=_h(user))

    assert r.status_code == 200
    assert r.json()["status"] == "despublicado"


def test_get_da_peca_de_outro_vendedor_responde_404(client, db_session):
    dona, loja_da_dona = _vendedor(db_session, email="dona@v.com")
    intrusa, _ = _vendedor(db_session, email="intrusa@v.com")
    peca = _peca(db_session, loja_da_dona, status="rascunho")

    r = client.get(f"{PECAS_URL}/{peca.id}", headers=_h(intrusa))

    # 404 e não 403: um 403 confirmaria que aquele id existe.
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


def test_get_da_peca_inexistente_responde_404(client, db_session):
    user, _ = _vendedor(db_session, email="c@v.com")

    r = client.get(f"{PECAS_URL}/999999", headers=_h(user))

    assert r.status_code == 404


def test_price_sai_como_numero(client, db_session):
    user, store = _vendedor(db_session, email="d@v.com")
    peca = _peca(db_session, store, price=Decimal("129.90"))

    corpo = client.get(f"{PECAS_URL}/{peca.id}", headers=_h(user)).json()

    assert corpo["price"] == 129.9
    assert isinstance(corpo["price"], float)


# --------------------------------------------------------------------- #146


def test_resumo_sem_venda_devolve_zero_e_nao_erro(client, db_session):
    user, store = _vendedor(db_session, email="e@v.com")
    _peca(db_session, store, status="ativo")

    r = client.get(RESUMO_URL, params={"period": "all"}, headers=_h(user))

    assert r.status_code == 200
    assert r.json() == {
        "period": "all",
        "sold_count": 0,
        "gross": 0.0,
        "commission": 0.0,
        "net": 0.0,
    }


def test_resumo_aplica_a_comissao_de_9_porcento(client, db_session):
    user, store = _vendedor(db_session, email="f@v.com")
    agora = utcnow_naive()
    _peca(db_session, store, status="vendido", price=Decimal("100.00"), sold_at=agora)
    _peca(db_session, store, status="vendido", price=Decimal("50.00"), sold_at=agora)

    corpo = client.get(RESUMO_URL, params={"period": "all"}, headers=_h(user)).json()

    assert corpo["sold_count"] == 2
    assert corpo["gross"] == 150.0
    assert corpo["commission"] == 13.5
    assert corpo["net"] == 136.5


def test_comissao_arredonda_para_cima_no_meio_centavo(client, db_session):
    """Bruto que cai no meio centavo, e cujos três valores não são exatos em
    base 2.

    `33.33 * 0.09 = 2.9997`, que arredonda para `3.00` em `ROUND_HALF_UP`, e o
    líquido sai por subtração: `30.33`. A versão anterior deste teste conferia o
    fechamento só com `13.5 + 136.5 == 150.0`, valores exatos em binário — a
    asserção não podia falhar e por isso não provava nada.
    """
    user, store = _vendedor(db_session, email="f2@v.com")
    _peca(
        db_session,
        store,
        status="vendido",
        price=Decimal("33.33"),
        sold_at=utcnow_naive(),
    )

    corpo = client.get(RESUMO_URL, params={"period": "all"}, headers=_h(user)).json()

    assert corpo["gross"] == 33.33
    assert corpo["commission"] == 3.0
    assert corpo["net"] == 30.33
    # Fecha no centavo. A conta vive em `Decimal` (`app/core/comissao.py`); o
    # JSON sai em float por contrato com o front, que faz `Number(...)`.
    assert round(corpo["commission"] + corpo["net"], 2) == corpo["gross"]


def test_resumo_de_30_dias_corta_a_venda_antiga(client, db_session):
    user, store = _vendedor(db_session, email="g@v.com")
    agora = utcnow_naive()
    _peca(
        db_session,
        store,
        status="vendido",
        price=Decimal("10.00"),
        sold_at=agora - timedelta(days=5),
    )
    _peca(
        db_session,
        store,
        status="vendido",
        price=Decimal("900.00"),
        sold_at=agora - timedelta(days=60),
    )

    corpo = client.get(RESUMO_URL, params={"period": "30d"}, headers=_h(user)).json()

    assert corpo["sold_count"] == 1
    assert corpo["gross"] == 10.0


def test_resumo_do_mes_comeca_no_dia_primeiro(client, db_session):
    user, store = _vendedor(db_session, email="h@v.com")
    primeiro = utcnow_naive().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    _peca(db_session, store, status="vendido", price=Decimal("20.00"), sold_at=primeiro)
    _peca(
        db_session,
        store,
        status="vendido",
        price=Decimal("700.00"),
        sold_at=primeiro - timedelta(seconds=1),
    )

    corpo = client.get(RESUMO_URL, params={"period": "month"}, headers=_h(user)).json()

    assert corpo["sold_count"] == 1
    assert corpo["gross"] == 20.0


def test_resumo_nao_soma_venda_de_outra_loja(client, db_session):
    user, store = _vendedor(db_session, email="i@v.com")
    _outra, loja_alheia = _vendedor(db_session, email="j@v.com")
    agora = utcnow_naive()
    _peca(db_session, store, status="vendido", price=Decimal("10.00"), sold_at=agora)
    _peca(
        db_session,
        loja_alheia,
        status="vendido",
        price=Decimal("999.00"),
        sold_at=agora,
    )

    corpo = client.get(RESUMO_URL, params={"period": "all"}, headers=_h(user)).json()

    assert corpo["sold_count"] == 1
    assert corpo["gross"] == 10.0


def test_venda_sem_data_entra_no_tudo_e_fica_fora_do_periodo(client, db_session):
    """Peça vendida antes da migration não tem data.

    No "tudo" ela conta, porque ali não há intervalo. Num período ela fica de
    fora: contá-la seria afirmar que a venda caiu naquele intervalo.
    """
    user, store = _vendedor(db_session, email="k@v.com")
    _peca(db_session, store, status="vendido", price=Decimal("80.00"), sold_at=None)

    tudo = client.get(RESUMO_URL, params={"period": "all"}, headers=_h(user)).json()
    mes = client.get(RESUMO_URL, params={"period": "month"}, headers=_h(user)).json()

    assert tudo["sold_count"] == 1
    assert tudo["gross"] == 80.0
    assert mes["sold_count"] == 0
