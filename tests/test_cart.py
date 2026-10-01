"""Carrinho do comprador agrupado por loja (issue #147)."""

from decimal import Decimal

import pytest

from app.models import CartItem, Product, Seller, Store, User
from app.seeds.lojas import seed_lojas
from app.seeds.pecas import seed_pecas

CART_URL = "/api/users/me/cart"
ITEMS_URL = f"{CART_URL}/items"


def make_user(db_session, email: str) -> User:
    user = User(name=email, email=email, password_hash="not-a-real-password")
    db_session.add(user)
    db_session.flush()
    return user


def make_store(db_session, name: str, document: str) -> Store:
    owner = make_user(db_session, f"{document}@loja.test")
    store = Store(
        name=name,
        seller=Seller(user=owner, document_type="CPF", document_value=document),
    )
    db_session.add(store)
    db_session.flush()
    return store


def make_product(
    db_session, store: Store, name: str, price: str, status: str = "ativo"
) -> Product:
    product = Product(store=store, name=name, price=Decimal(price), status=status)
    db_session.add(product)
    db_session.flush()
    return product


@pytest.fixture
def as_user(auth_headers):
    """Sessão real de um usuário. Antes da `#151`, era o cabeçalho `X-User-Id`."""

    def _as_user(user: User) -> dict[str, str]:
        return auth_headers(user.id)

    return _as_user


@pytest.fixture
def add(as_user):
    """Põe uma peça no carrinho de um usuário, com a sessão dele."""

    def _add(client, user: User, product: Product):
        return client.post(
            ITEMS_URL, json={"product_id": product.id}, headers=as_user(user)
        )

    return _add


def group_of(body: dict, store: Store) -> dict:
    return next(g for g in body["items"] if g["store"]["id"] == store.id)


@pytest.fixture
def cenario(db_session):
    """Dois compradores e duas lojas: Aurora (2 peças) e Brisa (1 peça)."""
    compradora = make_user(db_session, "compradora@test.local")
    outra = make_user(db_session, "outra@test.local")
    aurora = make_store(db_session, "Brechó Aurora", "11111111111")
    brisa = make_store(db_session, "Brechó Brisa", "22222222222")
    jaqueta = make_product(db_session, aurora, "Jaqueta jeans", "100.00")
    saia = make_product(db_session, aurora, "Saia midi", "50.50")
    bota = make_product(db_session, brisa, "Bota couro", "80.00")
    db_session.commit()
    return {
        "compradora": compradora,
        "outra": outra,
        "aurora": aurora,
        "brisa": brisa,
        "jaqueta": jaqueta,
        "saia": saia,
        "bota": bota,
    }


def test_adicionar_peca_ao_carrinho(client, db_session, cenario, add):
    response = add(client, cenario["compradora"], cenario["jaqueta"])

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    grupo = group_of(body, cenario["aurora"])
    assert grupo["store"]["name"] == "Brechó Aurora"
    assert grupo["items"] == [
        {
            "product_id": cenario["jaqueta"].id,
            "name": "Jaqueta jeans",
            "price": 100.0,
            "cover_image_url": None,
            "status": "ativo",
            "available": True,
        }
    ]
    assert grupo["subtotal"] == 100.0


def test_adicionar_mesma_peca_de_novo_devolve_sucesso_sem_duplicar(
    client,
    db_session,
    cenario,
    add,
):
    primeira = add(client, cenario["compradora"], cenario["jaqueta"])
    segunda = add(client, cenario["compradora"], cenario["jaqueta"])

    assert segunda.status_code == 200
    assert segunda.json() == primeira.json()
    assert (
        db_session.query(CartItem).filter_by(user_id=cenario["compradora"].id).count()
        == 1
    )


def test_listar_agrupa_por_loja_com_subtotal(client, cenario, as_user, add):
    for peca in ("jaqueta", "saia", "bota"):
        add(client, cenario["compradora"], cenario[peca])

    response = client.get(CART_URL, headers=as_user(cenario["compradora"]))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [g["store"]["name"] for g in body["items"]] == [
        "Brechó Aurora",
        "Brechó Brisa",
    ]
    aurora = group_of(body, cenario["aurora"])
    assert [i["name"] for i in aurora["items"]] == ["Jaqueta jeans", "Saia midi"]
    assert aurora["subtotal"] == 150.5
    assert group_of(body, cenario["brisa"])["subtotal"] == 80.0


def test_paginacao_e_por_loja_e_nunca_parte_uma_loja(client, cenario, as_user, add):
    for peca in ("jaqueta", "saia", "bota"):
        add(client, cenario["compradora"], cenario[peca])

    response = client.get(
        CART_URL,
        params={"page": 1, "page_size": 1},
        headers=as_user(cenario["compradora"]),
    )

    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1
    assert len(body["items"][0]["items"]) == 2  # a Aurora vem inteira


def test_remover_item_recalcula_subtotal_da_loja(client, cenario, as_user, add):
    for peca in ("jaqueta", "saia", "bota"):
        add(client, cenario["compradora"], cenario[peca])

    response = client.delete(
        f"{ITEMS_URL}/{cenario['jaqueta'].id}",
        headers=as_user(cenario["compradora"]),
    )

    assert response.status_code == 200
    body = response.json()
    aurora = group_of(body, cenario["aurora"])
    assert [i["name"] for i in aurora["items"]] == ["Saia midi"]
    assert aurora["subtotal"] == 50.5
    assert group_of(body, cenario["brisa"])["subtotal"] == 80.0


def test_remover_ultima_peca_da_loja_tira_a_loja_do_carrinho(
    client, cenario, as_user, add
):
    add(client, cenario["compradora"], cenario["bota"])

    response = client.delete(
        f"{ITEMS_URL}/{cenario['bota'].id}", headers=as_user(cenario["compradora"])
    )

    assert response.json()["items"] == []
    assert response.json()["total"] == 0


def test_peca_vendida_vem_marcada_e_nao_entra_na_conta(
    client, db_session, as_user, add
):
    # Nesta sprint nada marca peça como vendida além do seed (não há
    # checkout), então usamos uma das peças que ele já cria como vendidas.
    # Ela entra direto no carrinho, simulando que foi vendida depois de
    # ser adicionada — o POST recusa peça já vendida.
    seed_lojas(db_session)
    pecas = seed_pecas(db_session)
    vendida = next(p for p in pecas if p.status == "vendido")
    ativa = next(
        p for p in pecas if p.status == "ativo" and p.store_id == vendida.store_id
    )
    compradora = make_user(db_session, "compradora@test.local")
    db_session.add(CartItem(user_id=compradora.id, product_id=vendida.id))
    db_session.commit()
    add(client, compradora, ativa)

    response = client.get(CART_URL, headers=as_user(compradora))

    assert response.status_code == 200
    grupo = response.json()["items"][0]
    itens = {i["product_id"]: i for i in grupo["items"]}
    assert itens[vendida.id]["available"] is False
    assert itens[vendida.id]["status"] == "vendido"
    assert itens[ativa.id]["available"] is True
    assert grupo["subtotal"] == float(ativa.price)


def test_adicionar_peca_ja_vendida_devolve_409(client, db_session, cenario, add):
    vendida = make_product(
        db_session, cenario["aurora"], "Vestido", "70.00", status="vendido"
    )
    db_session.commit()

    response = add(client, cenario["compradora"], vendida)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PRODUCT_UNAVAILABLE"


def test_adicionar_peca_ja_no_carrinho_que_foi_vendida_devolve_sucesso(
    client,
    db_session,
    cenario,
    add,
):
    add(client, cenario["compradora"], cenario["jaqueta"])
    cenario["jaqueta"].status = "vendido"
    db_session.commit()

    response = add(client, cenario["compradora"], cenario["jaqueta"])

    assert response.status_code == 200
    assert group_of(response.json(), cenario["aurora"])["subtotal"] == 0.0


@pytest.mark.parametrize("status", ["inexistente", "despublicado"])
def test_adicionar_peca_inexistente_ou_despublicada_devolve_404(
    client,
    db_session,
    cenario,
    status,
    as_user,
):
    if status == "inexistente":
        product_id = 999_999
    else:
        product_id = make_product(
            db_session, cenario["aurora"], "Camisa", "40.00", status="despublicado"
        ).id
        db_session.commit()

    response = client.post(
        ITEMS_URL,
        json={"product_id": product_id},
        headers=as_user(cenario["compradora"]),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


def test_adicionar_sem_product_id_valido_devolve_422(client, cenario, as_user):
    response = client.post(
        ITEMS_URL, json={"product_id": 0}, headers=as_user(cenario["compradora"])
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "product_id" in response.json()["error"]["fields"]


def test_remover_peca_que_nao_esta_no_carrinho_devolve_404(client, cenario, as_user):
    response = client.delete(
        f"{ITEMS_URL}/{cenario['jaqueta'].id}",
        headers=as_user(cenario["compradora"]),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CART_ITEM_NOT_FOUND"


def test_ninguem_ve_o_carrinho_de_outra_pessoa(client, cenario, as_user, add):
    add(client, cenario["compradora"], cenario["jaqueta"])

    response = client.get(CART_URL, headers=as_user(cenario["outra"]))

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0


def test_ninguem_remove_item_do_carrinho_de_outra_pessoa(client, cenario, as_user, add):
    add(client, cenario["compradora"], cenario["jaqueta"])

    response = client.delete(
        f"{ITEMS_URL}/{cenario['jaqueta'].id}", headers=as_user(cenario["outra"])
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CART_ITEM_NOT_FOUND"
    carrinho = client.get(CART_URL, headers=as_user(cenario["compradora"])).json()
    assert carrinho["total"] == 1


def test_mesma_peca_pode_estar_no_carrinho_de_duas_pessoas(client, cenario, add):
    add(client, cenario["compradora"], cenario["jaqueta"])

    response = add(client, cenario["outra"], cenario["jaqueta"])

    assert response.status_code == 200
    assert response.json()["total"] == 1
