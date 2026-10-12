from decimal import Decimal

from app.core.security import create_access_token
from app.models.address import Address
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.seller import Seller
from app.models.store import Store
from app.models.user import User


def make_store_with_address(db_session, name: str) -> Store:
    user = User(
        name=f"{name} owner",
        email=f"{name.lower().replace(' ', '.')}@test.local",
        password_hash="not-a-real-password",
    )
    seller = Seller(
        user=user,
        document_type="CPF",
        document_value=str(abs(hash(name)))[:11].zfill(11),
    )
    address = Address(
        street="Rua dos Andradas",
        number="100",
        city="Porto Alegre",
        state="RS",
        zip_code="90020000",
    )
    store = Store(
        name=name,
        seller=seller,
        address=address,
        logo_url="https://cdn.test/logo.png",
    )
    db_session.add(store)
    db_session.flush()
    return store


def test_detail_retorna_atributos_media_e_loja(client, db_session):
    store = make_store_with_address(db_session, "Brechó Aurora")
    product = Product(
        store=store,
        name="Jaqueta jeans",
        description="Peça dos anos 90",
        category="Jaquetas",
        style="vintage",
        brand="Levi's",
        color="Azul",
        size="M",
        condition="Usado - bom estado",
        price=Decimal("199.90"),
        status="ativo",
        images=[
            ProductImage(image_url="https://cdn.test/b.jpg", position=2),
            ProductImage(image_url="https://cdn.test/a.jpg", position=1),
        ],
    )
    db_session.add(product)
    db_session.commit()

    response = client.get(f"/api/products/{product.id}")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "id": product.id,
        "name": "Jaqueta jeans",
        "description": "Peça dos anos 90",
        "category": "Jaquetas",
        "style": "vintage",
        "brand": "Levi's",
        "color": "Azul",
        "size": "M",
        "condition": "Usado - bom estado",
        "price": 199.90,
        "status": "ativo",
        "city": "Porto Alegre",
        "state": "RS",
        "media": [
            {"type": "image", "url": "https://cdn.test/a.jpg", "position": 1},
            {"type": "image", "url": "https://cdn.test/b.jpg", "position": 2},
        ],
        "store": {
            "id": store.id,
            "name": "Brechó Aurora",
            "logo_url": "https://cdn.test/logo.png",
            "verified": False,
        },
    }


def test_detail_de_peca_vendida_responde_200_com_status(client, db_session):
    store = make_store_with_address(db_session, "Brechó Central")
    product = Product(
        store=store,
        name="Camisa vendida",
        price=Decimal("50.00"),
        status="vendido",
    )
    db_session.add(product)
    db_session.commit()

    response = client.get(f"/api/products/{product.id}")

    assert response.status_code == 200
    assert response.json()["status"] == "vendido"


def test_detail_de_peca_despublicada_responde_404(client, db_session):
    store = make_store_with_address(db_session, "Brechó Oculto")
    product = Product(
        store=store,
        name="Peça despublicada",
        price=Decimal("30.00"),
        status="despublicado",
    )
    db_session.add(product)
    db_session.commit()

    response = client.get(f"/api/products/{product.id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


def test_detail_de_peca_em_rascunho_responde_404(client, db_session):
    """Rascunho nao e publico (back-end#238).

    Medido contra a API de pe em 30/09: `GET /api/products/{id}` de uma peca em
    rascunho respondia **200**, sem token nenhum, com nome, preco e loja. Ela
    nao aparece no feed, que filtra por `ativo`; chega-se nela pelo id, que e
    sequencial.
    """
    store = make_store_with_address(db_session, "Brechó do Rascunho")
    product = Product(
        store=store,
        name="Peça secreta em rascunho",
        price=Decimal("99.90"),
        status="rascunho",
    )
    db_session.add(product)
    db_session.commit()

    response = client.get(f"/api/products/{product.id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"
    # 404 e nao 403: um 403 confirmaria que aquele id existe.
    assert "rascunho" not in response.text
    assert "secreta" not in response.text


def test_detail_de_rascunho_e_404_tambem_para_o_dono(client, db_session):
    """O dono tambem nao ve o proprio rascunho por esta rota.

    A rota e de catalogo, e nao muda de resposta por quem pergunta. Quem precisa
    do proprio rascunho usa `GET /users/me/products/{id}` (back-end#234).
    """
    store = make_store_with_address(db_session, "Brechó da Dona")
    product = Product(
        store=store,
        name="Rascunho da dona",
        price=Decimal("50.00"),
        status="rascunho",
    )
    db_session.add(product)
    db_session.commit()

    # Token montado aqui, e nao por fixture: a fixture `auth_headers` chega com
    # a back-end#151, que e outro PR. Este teste nao depende dela.
    token = create_access_token(store.seller.user_id, False)
    response = client.get(
        f"/api/products/{product.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_detail_de_id_inexistente_responde_404(client, db_session):
    response = client.get("/api/products/999999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


def test_detail_sem_endereco_na_loja_devolve_cidade_vazia(client, db_session):
    store = make_store_with_address(db_session, "Brechó Sem Endereço")
    store.address = None
    product = Product(
        store=store,
        name="Bolsa",
        price=Decimal("80.00"),
        status="ativo",
    )
    db_session.add(product)
    db_session.commit()

    response = client.get(f"/api/products/{product.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["city"] == ""
    assert body["state"] == ""
    assert body["media"] == []


def test_detail_expoe_verified_do_vendedor(client, db_session):
    store = make_store_with_address(db_session, "Brechó Verificado")
    store.seller.verified = True
    product = Product(
        store=store,
        name="Vestido",
        price=Decimal("120.00"),
        status="ativo",
    )
    db_session.add(product)
    db_session.commit()

    response = client.get(f"/api/products/{product.id}")

    assert response.status_code == 200
    assert response.json()["store"]["verified"] is True
