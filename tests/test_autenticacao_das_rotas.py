"""As doze rotas da Sprint 2 exigem sessão (back-end#151).

Até esta issue, `get_current_user_id` lia o id de um cabeçalho `X-User-Id` e, na
falta dele, devolvia o usuário do seed. Medido contra a API de pé em 30/09, isso
significava:

- `GET /api/users/me/products` sem token nenhum devolvia 200 com tudo, inclusive
  rascunho;
- `POST /api/users/me/products` sem token criava peça;
- `PATCH /api/users/me/products/{id}` sem token renomeava peça alheia;
- `POST /api/users/me/store/verification` sem token concedia o selo Confiável;
- `X-User-Id: 1|2|3` devolvia a loja de cada vendedor, uma por uma;
- dois usuários logados diferentes viam as mesmas peças e a mesma loja.

Cada um desses tem um teste aqui. O arquivo existe para que o buraco não volte
em silêncio: se alguém tirar a dependência de uma rota, um destes quebra.
"""

from decimal import Decimal

import pytest

from app.models.product import Product
from app.models.seller import Seller
from app.models.store import Store
from app.models.user import User

# As doze rotas que resolviam identidade pelo placeholder, escritas a mao.
#
# `POST /api/users/me/media` nao entra: ela ja usava a autenticacao real.
# `GET /api/users/me/products/{id}` tambem nao: e a rota que a back-end#234
# acrescenta, no PR de #234/#146. Quando aquele PR entrar, esta lista ganha
# mais uma linha.
ROTAS_PRIVADAS = [
    ("get", "/api/users/me/products"),
    ("post", "/api/users/me/products"),
    ("patch", "/api/users/me/products/1"),
    ("post", "/api/users/me/products/1/publish"),
    ("post", "/api/users/me/products/1/unpublish"),
    ("get", "/api/users/me/products/1/ai-status"),
    ("get", "/api/users/me/cart"),
    ("post", "/api/users/me/cart/items"),
    ("delete", "/api/users/me/cart/items/1"),
    ("get", "/api/users/me/store"),
    ("post", "/api/users/me/store"),
    ("post", "/api/users/me/store/verification"),
]

COM_CORPO = {"post", "patch", "put"}


def _chamar(client, metodo: str, caminho: str, **kwargs):
    """`client.get` nao aceita `json=`; so os metodos com corpo recebem."""
    if metodo in COM_CORPO:
        kwargs.setdefault("json", {})
    return getattr(client, metodo)(caminho, **kwargs)


def _vendedora(db, *, email: str, documento: str) -> tuple[User, Store]:
    user = User(name="Vendedora", email=email, password_hash="x")
    db.add(user)
    db.flush()
    seller = Seller(user_id=user.id, document_type="CPF", document_value=documento)
    db.add(seller)
    db.flush()
    store = Store(seller_id=seller.id, name=f"Brechó de {email}")
    db.add(store)
    db.flush()
    return user, store


def _peca(db, store: Store, **kwargs) -> Product:
    dados = dict(
        store_id=store.id,
        name="Jaqueta",
        price=Decimal("100.00"),
        quantity=1,
        status="ativo",
    )
    dados.update(kwargs)
    product = Product(**dados)
    db.add(product)
    db.flush()
    return product


@pytest.mark.parametrize(("metodo", "caminho"), ROTAS_PRIVADAS)
def test_rota_privada_sem_token_responde_401(client, db_session, metodo, caminho):
    resposta = _chamar(client, metodo, caminho)

    assert (
        resposta.status_code == 401
    ), f"{metodo.upper()} {caminho} respondeu {resposta.status_code}"
    assert resposta.json()["error"]["code"] == "AUTH_REQUIRED"


@pytest.mark.parametrize(("metodo", "caminho"), ROTAS_PRIVADAS)
def test_rota_privada_com_token_invalido_responde_401(
    client, db_session, metodo, caminho
):
    resposta = _chamar(
        client, metodo, caminho, headers={"Authorization": "Bearer nao.e.um.token"}
    )

    assert resposta.status_code == 401
    assert resposta.json()["error"]["code"] == "AUTH_REQUIRED"


def test_x_user_id_nao_muda_mais_a_identidade(client, db_session, auth_headers):
    """O cabeçalho que personificava qualquer vendedor deixou de valer.

    Com o placeholder, `X-User-Id: <id>` devolvia a loja daquele vendedor.
    """
    ana, loja_da_ana = _vendedora(
        db_session, email="ana@v.com", documento="00000000001"
    )
    bia, loja_da_bia = _vendedora(
        db_session, email="bia@v.com", documento="00000000002"
    )
    db_session.commit()

    cabecalhos = auth_headers(ana.id)
    cabecalhos["X-User-Id"] = str(bia.id)

    resposta = client.get("/api/users/me/store", headers=cabecalhos)

    assert resposta.status_code == 200
    # A sessão manda; o cabeçalho é ignorado.
    assert resposta.json()["id"] == loja_da_ana.id
    assert resposta.json()["id"] != loja_da_bia.id


def test_x_user_id_sozinho_nao_abre_sessao(client, db_session):
    ana, _ = _vendedora(db_session, email="ana@v.com", documento="00000000001")
    db_session.commit()

    resposta = client.get("/api/users/me/store", headers={"X-User-Id": str(ana.id)})

    assert resposta.status_code == 401


def test_cada_vendedora_ve_a_propria_loja(client, db_session, auth_headers):
    """Duas sessões, duas lojas. Antes as duas caíam na loja do usuário do seed."""
    ana, loja_da_ana = _vendedora(
        db_session, email="ana@v.com", documento="00000000001"
    )
    bia, loja_da_bia = _vendedora(
        db_session, email="bia@v.com", documento="00000000002"
    )
    db_session.commit()

    da_ana = client.get("/api/users/me/store", headers=auth_headers(ana.id)).json()
    da_bia = client.get("/api/users/me/store", headers=auth_headers(bia.id)).json()

    assert da_ana["id"] == loja_da_ana.id
    assert da_bia["id"] == loja_da_bia.id
    assert da_ana["id"] != da_bia["id"]


def test_cada_vendedora_ve_as_proprias_pecas(client, db_session, auth_headers):
    ana, loja_da_ana = _vendedora(
        db_session, email="ana@v.com", documento="00000000001"
    )
    bia, loja_da_bia = _vendedora(
        db_session, email="bia@v.com", documento="00000000002"
    )
    _peca(db_session, loja_da_ana, name="Peça da Ana")
    _peca(db_session, loja_da_bia, name="Peça da Bia")
    db_session.commit()

    da_ana = client.get("/api/users/me/products", headers=auth_headers(ana.id)).json()
    da_bia = client.get("/api/users/me/products", headers=auth_headers(bia.id)).json()

    assert [p["name"] for p in da_ana["items"]] == ["Peça da Ana"]
    assert [p["name"] for p in da_bia["items"]] == ["Peça da Bia"]


def test_ninguem_renomeia_peca_alheia(client, db_session, auth_headers):
    """`PATCH` sem token renomeava peça de qualquer vendedor. Agora recusa."""
    ana, loja_da_ana = _vendedora(
        db_session, email="ana@v.com", documento="00000000001"
    )
    bia, _ = _vendedora(db_session, email="bia@v.com", documento="00000000002")
    peca = _peca(db_session, loja_da_ana, name="Peça da Ana")
    db_session.commit()

    sem_sessao = client.patch(
        f"/api/users/me/products/{peca.id}", json={"name": "Renomeada por anônimo"}
    )
    da_bia = client.patch(
        f"/api/users/me/products/{peca.id}",
        json={"name": "Renomeada pela Bia"},
        headers=auth_headers(bia.id),
    )

    assert sem_sessao.status_code == 401
    assert da_bia.status_code == 404
    db_session.refresh(peca)
    assert peca.name == "Peça da Ana"


def test_selo_confiavel_exige_sessao(client, db_session, auth_headers):
    """`POST /store/verification` sem token concedia o selo. Agora recusa."""
    ana, loja_da_ana = _vendedora(
        db_session, email="ana@v.com", documento="52998224725"
    )
    db_session.commit()

    sem_sessao = client.post("/api/users/me/store/verification")

    assert sem_sessao.status_code == 401
    db_session.refresh(loja_da_ana)
    assert loja_da_ana.seller.verified is not True


def test_carrinho_nao_vaza_sem_sessao(client, db_session, auth_headers):
    ana, loja = _vendedora(db_session, email="ana@v.com", documento="00000000001")
    peca = _peca(db_session, loja)
    db_session.commit()

    client.post(
        "/api/users/me/cart/items",
        json={"product_id": peca.id},
        headers=auth_headers(ana.id),
    )

    sem_sessao = client.get("/api/users/me/cart")

    assert sem_sessao.status_code == 401


def test_token_de_usuario_que_nao_existe_responde_401(client, db_session, auth_headers):
    """Token assinado para um id inexistente não vale.

    `get_current_user` resolve o `sub` contra o banco; sem usuário, é 401 e não
    uma sessão fantasma.
    """
    resposta = client.get("/api/users/me/store", headers=auth_headers(999999))

    assert resposta.status_code == 401
    assert resposta.json()["error"]["code"] == "AUTH_REQUIRED"
