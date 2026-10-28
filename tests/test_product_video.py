"""O vídeo curto vinculado à peça (back-end#270).

Um por peça, em `video_url`, separado da galeria: não conta como a foto que
publicar exige (RN-47) e não vira capa. A duração (RN-48) é conferida no
upload, em `test_video_duration.py`; aqui só a URL do vídeo entra.
"""

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import Product, ProductImage, Seller, Store, User

PRODUCTS_URL = "/api/users/me/products"
MEDIA = "http://localhost:8000/api/media"
VIDEO = f"{MEDIA}/products/videos/aaa111"
OUTRO_VIDEO = f"{MEDIA}/products/videos/bbb222"
FOTO = f"{MEDIA}/products/photos/ccc333"


def make_store(db: Session) -> tuple[User, Store]:
    user = User(name="Aurora", email="aurora@loja.test", password_hash="x")
    store = Store(
        name="Aurora",
        seller=Seller(user=user, document_type="CPF", document_value="52998224725"),
    )
    db.add(store)
    db.commit()
    return user, store


def make_product(
    db: Session,
    store: Store,
    *,
    status: str = "ativo",
    video_url: str | None = None,
    fotos: tuple[str, ...] = (FOTO,),
) -> Product:
    product = Product(
        store=store,
        name="Jaqueta",
        price=Decimal("100.00"),
        status=status,
        video_url=video_url,
        images=[
            ProductImage(image_url=url, position=posicao)
            for posicao, url in enumerate(fotos)
        ],
    )
    db.add(product)
    db.commit()
    return product


@pytest.fixture
def vendedora(db_session):
    return make_store(db_session)


@pytest.fixture
def como_vendedora(vendedora, auth_headers):
    return auth_headers(vendedora[0].id)


def editar(client, headers, product: Product, **campos):
    return client.patch(f"{PRODUCTS_URL}/{product.id}", json=campos, headers=headers)


# --- criar e devolver ------------------------------------------------------------


def test_rascunho_criado_com_video_devolve_o_video(client, vendedora, como_vendedora):
    resposta = client.post(
        PRODUCTS_URL,
        json={"name": "Jaqueta", "price": "100.00", "video_url": VIDEO},
        headers=como_vendedora,
    )

    assert resposta.status_code == 201
    assert resposta.json()["video_url"] == VIDEO
    assert resposta.json()["images"] == []


def test_rascunho_sem_video_devolve_null(client, vendedora, como_vendedora):
    resposta = client.post(
        PRODUCTS_URL,
        json={"name": "Jaqueta", "price": "100.00"},
        headers=como_vendedora,
    )

    assert resposta.json()["video_url"] is None


def test_detail_devolve_o_video_depois_das_fotos(client, db_session, vendedora):
    product = make_product(
        db_session, vendedora[1], video_url=VIDEO, fotos=(FOTO, f"{FOTO}-2")
    )

    media = client.get(f"/api/products/{product.id}").json()["media"]

    assert media == [
        {"type": "image", "url": FOTO, "position": 0},
        {"type": "image", "url": f"{FOTO}-2", "position": 1},
        {"type": "video", "url": VIDEO, "position": 2},
    ]


def test_detail_sem_video_so_tem_fotos(client, db_session, vendedora):
    product = make_product(db_session, vendedora[1])

    media = client.get(f"/api/products/{product.id}").json()["media"]

    assert [item["type"] for item in media] == ["image"]


def test_vendedora_ve_o_video_no_proprio_detalhe(
    client, db_session, vendedora, como_vendedora
):
    product = make_product(db_session, vendedora[1], status="rascunho", video_url=VIDEO)

    resposta = client.get(f"{PRODUCTS_URL}/{product.id}", headers=como_vendedora)

    assert resposta.json()["video_url"] == VIDEO


# --- trocar e remover ------------------------------------------------------------


def test_trocar_o_video_substitui_o_anterior(
    client, db_session, vendedora, como_vendedora
):
    product = make_product(db_session, vendedora[1], video_url=VIDEO)

    resposta = editar(client, como_vendedora, product, video_url=OUTRO_VIDEO)

    assert resposta.status_code == 200
    assert resposta.json()["video_url"] == OUTRO_VIDEO
    db_session.refresh(product)
    assert product.video_url == OUTRO_VIDEO


def test_null_remove_o_video(client, db_session, vendedora, como_vendedora):
    product = make_product(db_session, vendedora[1], video_url=VIDEO)

    resposta = editar(client, como_vendedora, product, video_url=None)

    assert resposta.status_code == 200
    assert resposta.json()["video_url"] is None
    media = client.get(f"/api/products/{product.id}").json()["media"]
    assert [item["type"] for item in media] == ["image"]


def test_editar_outro_campo_mantem_o_video(
    client, db_session, vendedora, como_vendedora
):
    product = make_product(db_session, vendedora[1], video_url=VIDEO)

    resposta = editar(client, como_vendedora, product, price="90.00")

    assert resposta.json()["video_url"] == VIDEO


def test_peca_vendida_nao_troca_o_video(client, db_session, vendedora, como_vendedora):
    product = make_product(db_session, vendedora[1], status="vendido", video_url=VIDEO)

    resposta = editar(client, como_vendedora, product, video_url=None)

    assert resposta.status_code == 409
    db_session.refresh(product)
    assert product.video_url == VIDEO


# --- o vídeo não substitui a foto ------------------------------------------------


def test_publicar_so_com_video_e_sem_foto_continua_recusado(
    client, db_session, vendedora, como_vendedora
):
    product = make_product(
        db_session, vendedora[1], status="rascunho", video_url=VIDEO, fotos=()
    )

    resposta = client.post(
        f"{PRODUCTS_URL}/{product.id}/publish", headers=como_vendedora
    )

    assert resposta.status_code == 422
    assert "images" in resposta.json()["error"]["fields"]
    db_session.refresh(product)
    assert product.status == "rascunho"


@pytest.mark.parametrize("metodo", ["post", "patch"])
def test_video_na_galeria_de_fotos_e_recusado(
    client, db_session, vendedora, como_vendedora, metodo
):
    """Na galeria ele contaria como a foto que publicar exige (RN-47)."""
    if metodo == "post":
        resposta = client.post(
            PRODUCTS_URL,
            json={"name": "Jaqueta", "price": "100.00", "images": [VIDEO]},
            headers=como_vendedora,
        )
    else:
        product = make_product(db_session, vendedora[1], status="rascunho", fotos=())
        resposta = editar(client, como_vendedora, product, images=[VIDEO])

    assert resposta.status_code == 422
    assert "images" in resposta.json()["error"]["fields"]


@pytest.mark.parametrize(
    "url", [FOTO, f"{MEDIA}/products/labels/ddd444", "https://youtube.com/watch?v=x"]
)
def test_video_url_que_nao_e_video_e_recusada(
    client, db_session, vendedora, como_vendedora, url
):
    """Só a URL do envio com `kind=video`, que é onde a duração é conferida."""
    product = make_product(db_session, vendedora[1])

    resposta = editar(client, como_vendedora, product, video_url=url)

    assert resposta.status_code == 422
    assert "video_url" in resposta.json()["error"]["fields"]
    db_session.refresh(product)
    assert product.video_url is None
