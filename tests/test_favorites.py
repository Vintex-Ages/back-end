"""Favoritos do comprador (back-end#252).

O formato do item é o que o front lê no `favoriteService` (front-end#390): o
mesmo do feed, com `status`, num `Page` de `{items, page, page_size, total}`.
"""

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import Favorite, Product, Seller, Store, User

FAVORITES_URL = "/api/users/me/favorites"


def make_user(session: Session, email: str) -> User:
    user = User(name=email, email=email, password_hash="not-a-real-password")
    session.add(user)
    session.flush()
    return user


def make_store(session: Session, name: str, document: str) -> Store:
    owner = make_user(session, f"{document}@loja.test")
    store = Store(
        name=name,
        seller=Seller(user=owner, document_type="CPF", document_value=document),
    )
    session.add(store)
    session.flush()
    return store


def make_product(
    session: Session, store: Store, name: str, price: str, status: str = "ativo"
) -> Product:
    product = Product(store=store, name=name, price=Decimal(price), status=status)
    session.add(product)
    session.flush()
    return product


def montar_cenario(session: Session) -> dict:
    """Duas compradoras e uma loja com duas peças à venda."""
    compradora = make_user(session, "compradora@test.local")
    outra = make_user(session, "outra@test.local")
    aurora = make_store(session, "Brechó Aurora", "11111111111")
    jaqueta = make_product(session, aurora, "Jaqueta jeans", "159.90")
    saia = make_product(session, aurora, "Saia midi", "50.50")
    session.commit()
    return {
        "compradora": compradora,
        "outra": outra,
        "aurora": aurora,
        "jaqueta": jaqueta,
        "saia": saia,
    }


@pytest.fixture
def cenario(db_session):
    return montar_cenario(db_session)


@pytest.fixture
def as_user(auth_headers):
    def _as_user(user: User) -> dict[str, str]:
        return auth_headers(user.id)

    return _as_user


@pytest.fixture
def favoritar(as_user):
    def _favoritar(client, user: User, product_id: int):
        return client.put(f"{FAVORITES_URL}/{product_id}", headers=as_user(user))

    return _favoritar


@pytest.fixture
def desfavoritar(as_user):
    def _desfavoritar(client, user: User, product_id: int):
        return client.delete(f"{FAVORITES_URL}/{product_id}", headers=as_user(user))

    return _desfavoritar


@pytest.fixture
def listar(as_user):
    def _listar(client, user: User, **params):
        return client.get(FAVORITES_URL, params=params, headers=as_user(user))

    return _listar


def test_favoritar_e_listar_devolve_a_peca_no_formato_do_feed(
    client, cenario, favoritar, listar
):
    resposta = favoritar(client, cenario["compradora"], cenario["jaqueta"].id)

    assert resposta.status_code == 204
    assert resposta.content == b""
    lista = listar(client, cenario["compradora"])
    assert lista.status_code == 200
    assert lista.json() == {
        "items": [
            {
                "id": cenario["jaqueta"].id,
                "name": "Jaqueta jeans",
                "price": 159.9,
                "cover_image_url": None,
                "status": "ativo",
                "store": {
                    "id": cenario["aurora"].id,
                    "name": "Brechó Aurora",
                    "verified": False,
                },
            }
        ],
        "page": 1,
        "page_size": 20,
        "total": 1,
    }


def test_favoritar_duas_vezes_responde_204_e_lista_a_peca_uma_vez(
    client, db_session, cenario, favoritar, listar
):
    primeira = favoritar(client, cenario["compradora"], cenario["jaqueta"].id)
    segunda = favoritar(client, cenario["compradora"], cenario["jaqueta"].id)

    assert (primeira.status_code, segunda.status_code) == (204, 204)
    body = listar(client, cenario["compradora"]).json()
    assert [item["id"] for item in body["items"]] == [cenario["jaqueta"].id]
    assert body["total"] == 1
    assert db_session.query(Favorite).count() == 1


def test_desfavoritar_tira_a_peca_da_lista(
    client, cenario, favoritar, desfavoritar, listar
):
    favoritar(client, cenario["compradora"], cenario["jaqueta"].id)

    resposta = desfavoritar(client, cenario["compradora"], cenario["jaqueta"].id)

    assert resposta.status_code == 204
    assert resposta.content == b""
    assert listar(client, cenario["compradora"]).json()["total"] == 0


def test_desfavoritar_duas_vezes_responde_204_nas_duas(
    client, cenario, favoritar, desfavoritar
):
    favoritar(client, cenario["compradora"], cenario["jaqueta"].id)

    primeira = desfavoritar(client, cenario["compradora"], cenario["jaqueta"].id)
    segunda = desfavoritar(client, cenario["compradora"], cenario["jaqueta"].id)

    assert (primeira.status_code, segunda.status_code) == (204, 204)


@pytest.mark.parametrize("product_id", ["peca_nao_favoritada", 999999])
def test_desfavoritar_o_que_nao_esta_favoritado_responde_204(
    client, cenario, desfavoritar, product_id
):
    if product_id == "peca_nao_favoritada":
        product_id = cenario["saia"].id

    resposta = desfavoritar(client, cenario["compradora"], product_id)

    assert resposta.status_code == 204


def test_lista_vem_do_mais_recente_para_o_mais_antigo(
    client, cenario, favoritar, listar
):
    favoritar(client, cenario["compradora"], cenario["jaqueta"].id)
    favoritar(client, cenario["compradora"], cenario["saia"].id)

    body = listar(client, cenario["compradora"]).json()

    assert [item["name"] for item in body["items"]] == ["Saia midi", "Jaqueta jeans"]


def test_peca_vendida_continua_na_lista_com_o_status(
    client, db_session, cenario, favoritar, listar
):
    favoritar(client, cenario["compradora"], cenario["jaqueta"].id)
    cenario["jaqueta"].status = "vendido"
    db_session.commit()

    body = listar(client, cenario["compradora"]).json()

    assert body["total"] == 1
    assert body["items"][0]["status"] == "vendido"


@pytest.mark.parametrize("status", ["reservado", "vendido"])
def test_favoritar_peca_reservada_ou_vendida_e_aceito(
    client, db_session, cenario, favoritar, listar, status
):
    """O coração aparece no detalhe público, e ele abre peça reservada e
    vendida (RN-44)."""
    cenario["jaqueta"].status = status
    db_session.commit()

    resposta = favoritar(client, cenario["compradora"], cenario["jaqueta"].id)

    assert resposta.status_code == 204
    assert listar(client, cenario["compradora"]).json()["items"][0]["status"] == status


def test_favoritar_peca_inexistente_responde_404(client, cenario, favoritar):
    resposta = favoritar(client, cenario["compradora"], 999999)

    assert resposta.status_code == 404
    assert resposta.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


@pytest.mark.parametrize("status", ["rascunho", "despublicado"])
def test_favoritar_peca_fora_da_vitrine_responde_404_como_o_detalhe(
    client, db_session, cenario, favoritar, status
):
    cenario["jaqueta"].status = status
    db_session.commit()

    resposta = favoritar(client, cenario["compradora"], cenario["jaqueta"].id)

    assert resposta.status_code == 404
    assert resposta.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


def test_peca_despublicada_sai_da_lista_e_volta_ao_republicar(
    client, db_session, cenario, favoritar, listar
):
    favoritar(client, cenario["compradora"], cenario["jaqueta"].id)

    cenario["jaqueta"].status = "despublicado"
    db_session.commit()
    assert listar(client, cenario["compradora"]).json()["total"] == 0

    cenario["jaqueta"].status = "ativo"
    db_session.commit()
    assert listar(client, cenario["compradora"]).json()["total"] == 1


def test_cada_pessoa_ve_e_mexe_so_nos_proprios_favoritos(
    client, cenario, favoritar, desfavoritar, listar
):
    favoritar(client, cenario["compradora"], cenario["jaqueta"].id)

    assert listar(client, cenario["outra"]).json()["total"] == 0
    desfavoritar(client, cenario["outra"], cenario["jaqueta"].id)
    assert listar(client, cenario["compradora"]).json()["total"] == 1


def test_lista_e_paginada(client, cenario, favoritar, listar):
    favoritar(client, cenario["compradora"], cenario["jaqueta"].id)
    favoritar(client, cenario["compradora"], cenario["saia"].id)

    body = listar(client, cenario["compradora"], page=2, page_size=1).json()

    assert body["page"] == 2
    assert body["page_size"] == 1
    assert body["total"] == 2
    assert [item["name"] for item in body["items"]] == ["Jaqueta jeans"]


@pytest.mark.parametrize(
    ("metodo", "caminho"),
    [
        ("get", FAVORITES_URL),
        ("put", f"{FAVORITES_URL}/1"),
        ("delete", f"{FAVORITES_URL}/1"),
    ],
)
def test_sem_token_as_tres_rotas_respondem_401(client, db_session, metodo, caminho):
    """Mesmo corpo das outras ações protegidas, que o front já trata (RN-27)."""
    resposta = getattr(client, metodo)(caminho)

    assert resposta.status_code == 401
    assert resposta.json()["error"]["code"] == "AUTH_REQUIRED"


@pytest.mark.postgres
def test_favoritar_duas_vezes_no_postgres_nao_duplica(
    pg_client, pg_session, auth_headers
):
    """O `ON CONFLICT` do Postgres, na tabela criada pela migration."""
    cenario = montar_cenario(pg_session)
    headers = auth_headers(cenario["compradora"].id)
    url = f"{FAVORITES_URL}/{cenario['jaqueta'].id}"

    assert pg_client.put(url, headers=headers).status_code == 204
    assert pg_client.put(url, headers=headers).status_code == 204

    body = pg_client.get(FAVORITES_URL, headers=headers).json()
    assert [item["id"] for item in body["items"]] == [cenario["jaqueta"].id]
    assert body["items"][0]["price"] == 159.9
