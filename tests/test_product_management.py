from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal

from sqlalchemy import event

from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.seller import Seller
from app.models.store import Store
from app.models.user import User

# Campos que toda transicao de peca tem que devolver. O front trata publish,
# unpublish e republish num mapeador so, que le `store.id`; um schema reduzido
# em qualquer das tres derruba a tela do vendedor (#230).
CAMPOS_DA_TRANSICAO = ("store", "images", "ai_corrections")


def make_store(db_session, user_id: int, name: str) -> Store:
    user = User(
        id=user_id,
        name=f"Owner {name}",
        email=f"{name.lower()}@test.local",
        password_hash="not-a-real-password",
    )
    seller = Seller(
        user=user,
        document_type="CPF",
        document_value=str(user_id).zfill(11),
    )
    store = Store(name=name, seller=seller)
    db_session.add(store)
    db_session.flush()
    return store


def make_product(db_session, store: Store, name: str, status: str) -> Product:
    product = Product(
        store=store,
        name=name,
        price=Decimal("99.90"),
        status=status,
    )
    db_session.add(product)
    db_session.flush()
    return product


def test_seller_lists_all_statuses_and_filters(client, db_session, auth_headers):
    store = make_store(db_session, 10, "Aurora")
    make_product(db_session, store, "Ativa", "ativo")
    sold = make_product(db_session, store, "Vendida", "vendido")
    make_product(db_session, store, "Fora do ar", "despublicado")
    db_session.commit()

    response = client.get("/api/users/me/products", headers=auth_headers(10))

    assert response.status_code == 200
    assert response.json()["total"] == 3
    assert {item["id"] for item in response.json()["items"]} >= {sold.id}

    response = client.get(
        "/api/users/me/products?status=vendido", headers=auth_headers(10)
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["status"] == "vendido"


def test_seller_cannot_see_or_edit_another_sellers_product(
    client, db_session, auth_headers
):
    own_store = make_store(db_session, 20, "Own")
    other_store = make_store(db_session, 21, "Other")
    other_product = make_product(db_session, other_store, "Other product", "ativo")
    make_product(db_session, own_store, "Own product", "ativo")
    db_session.commit()

    response = client.get("/api/users/me/products", headers=auth_headers(20))
    assert response.status_code == 200
    assert all(item["id"] != other_product.id for item in response.json()["items"])

    response = client.patch(
        f"/api/users/me/products/{other_product.id}",
        json={"name": "Tampered"},
        headers=auth_headers(20),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


def test_sold_product_cannot_be_edited(client, db_session, auth_headers):
    store = make_store(db_session, 30, "Sold")
    product = make_product(db_session, store, "Sold product", "vendido")
    db_session.commit()

    response = client.patch(
        f"/api/users/me/products/{product.id}",
        json={"name": "Changed"},
        headers=auth_headers(30),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PRODUCT_SOLD"


def test_draft_product_can_be_edited_with_patch(client, db_session, auth_headers):
    store = make_store(db_session, 35, "Draft")
    product = make_product(db_session, store, "Draft product", "despublicado")
    db_session.commit()

    response = client.patch(
        f"/api/users/me/products/{product.id}",
        json={"name": "Edited draft"},
        headers=auth_headers(35),
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Edited draft"


def test_update_rejects_explicit_null_for_required_field(
    client, db_session, auth_headers
):
    store = make_store(db_session, 36, "Null")
    product = make_product(db_session, store, "Null product", "ativo")
    db_session.commit()

    response = client.patch(
        f"/api/users/me/products/{product.id}",
        json={"price": None},
        headers=auth_headers(36),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_product_can_be_unpublished(client, db_session, auth_headers):
    """Ciclo completo: sai da vitrine e volta. A volta e pelo `publish`, que
    exige foto -- por isso a peca nasce com uma aqui."""
    store = make_store(db_session, 40, "Cycle")
    product = com_foto(
        db_session, make_product(db_session, store, "Cycle product", "ativo")
    )
    db_session.commit()

    response = client.post(
        f"/api/users/me/products/{product.id}/unpublish",
        headers=auth_headers(40),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "despublicado"
    assert db_session.get(Product, product.id) is not None

    response = client.put(
        f"/api/users/me/products/{product.id}",
        json={"name": "No PUT"},
        headers=auth_headers(40),
    )
    assert response.status_code == 405

    response = client.post(
        f"/api/users/me/products/{product.id}/publish",
        headers=auth_headers(40),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ativo"


def test_sold_product_cannot_change_status(client, db_session, auth_headers):
    store = make_store(db_session, 41, "Locked")
    product = make_product(db_session, store, "Sold product", "vendido")
    db_session.commit()

    response = client.post(
        f"/api/users/me/products/{product.id}/unpublish",
        headers=auth_headers(41),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PRODUCT_SOLD"

    response = client.post(
        f"/api/users/me/products/{product.id}/publish",
        headers=auth_headers(41),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PRODUCT_SOLD"


def test_rascunho_nao_se_despublica(client, db_session, auth_headers):
    """Rascunho nao esta na vitrine, entao nao ha o que tirar dela."""
    store = make_store(db_session, 42, "DraftGuard")
    product = make_product(db_session, store, "Draft product", "rascunho")
    db_session.commit()

    response = client.post(
        f"/api/users/me/products/{product.id}/unpublish",
        headers=auth_headers(42),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PRODUCT_NOT_EDITABLE"


def test_rota_republish_nao_existe_mais(client, db_session, auth_headers):
    """A `#145` sempre declarou que `republish` nao existe: publicar rascunho e
    republicar despublicada sao a mesma transicao. A rota foi criada no `#157`
    como contorno e virou o unico caminho que publicava peca sem foto -- ela
    devolvia 200 com `images: []` e a peca entrava no feed. Saiu na `#230`.

    Este teste existe para que reintroduzi-la exija apagar um teste."""
    store = make_store(db_session, 44, "SemRota")
    product = make_product(db_session, store, "Peca", "despublicado")
    db_session.commit()

    response = client.post(
        f"/api/users/me/products/{product.id}/republish",
        headers=auth_headers(44),
    )

    assert response.status_code == 404


def test_unpublished_product_cannot_be_unpublished_again(
    client, db_session, auth_headers
):
    store = make_store(db_session, 43, "Twice")
    product = make_product(db_session, store, "Off product", "despublicado")
    db_session.commit()

    response = client.post(
        f"/api/users/me/products/{product.id}/unpublish",
        headers=auth_headers(43),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PRODUCT_NOT_EDITABLE"


def com_foto(db_session, product: Product) -> Product:
    """Peca publicavel precisa de foto. Peca que ja esteve no ar sempre tem uma;
    o `make_product` nao cria, entao os testes de republicacao criam aqui."""
    db_session.add(
        ProductImage(product=product, image_url="https://exemplo/1.jpg", position=0)
    )
    db_session.flush()
    return product


def test_publish_republica_peca_despublicada(client, db_session, auth_headers):
    """A `#145` declarou uma transicao unica para `ativo`, vindo de rascunho ou
    de despublicado. O front chama `publish` nos dois casos; ate a `#230` o
    segundo devolvia 409 e o vendedor nao conseguia voltar a anunciar."""
    store = make_store(db_session, 60, "Volta")
    product = com_foto(
        db_session, make_product(db_session, store, "Peca de volta", "despublicado")
    )
    db_session.commit()

    response = client.post(
        f"/api/users/me/products/{product.id}/publish",
        headers=auth_headers(60),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ativo"


def test_publish_recusa_peca_ja_publicada(client, db_session, auth_headers):
    store = make_store(db_session, 61, "Ja no ar")
    product = com_foto(
        db_session, make_product(db_session, store, "Peca ativa", "ativo")
    )
    db_session.commit()

    response = client.post(
        f"/api/users/me/products/{product.id}/publish",
        headers=auth_headers(61),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


def test_publish_recusa_peca_vendida(client, db_session, auth_headers):
    """RN-53: vendida e imutavel, e responde com o codigo proprio -- quem chama
    precisa distinguir "ja esta no ar" de "nao mexe mais nesta"."""
    store = make_store(db_session, 62, "Vendida")
    product = com_foto(
        db_session, make_product(db_session, store, "Peca vendida", "vendido")
    )
    db_session.commit()

    response = client.post(
        f"/api/users/me/products/{product.id}/publish",
        headers=auth_headers(62),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PRODUCT_SOLD"


def test_publish_recusa_peca_reservada(client, db_session, auth_headers):
    """Peca reservada esta num pedido aberto. Se voltasse para `ativo`, entraria
    no feed e no carrinho de outra pessoa, e a mesma peca fecharia dois pedidos
    (RN-46)."""
    store = make_store(db_session, 67, "Reservada")
    product = com_foto(
        db_session, make_product(db_session, store, "Peca reservada", "reservado")
    )
    db_session.commit()

    response = client.post(
        f"/api/users/me/products/{product.id}/publish",
        headers=auth_headers(67),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PRODUCT_NOT_EDITABLE"
    db_session.refresh(product)
    assert product.status == "reservado"


def test_unpublish_recusa_peca_reservada(client, db_session, auth_headers):
    """Mesma recusa do `publish`, explicita e nao herdada do `!= ativo`."""
    store = make_store(db_session, 68, "Reservada off")
    product = com_foto(
        db_session, make_product(db_session, store, "Peca em pedido", "reservado")
    )
    db_session.commit()

    response = client.post(
        f"/api/users/me/products/{product.id}/unpublish",
        headers=auth_headers(68),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PRODUCT_NOT_EDITABLE"
    db_session.refresh(product)
    assert product.status == "reservado"


def test_update_recusa_peca_reservada(client, db_session, auth_headers):
    """O comprador fechou o pedido com esta peca (back-end#247): editar agora a
    faria diferente do que ele comprou."""
    store = make_store(db_session, 69, "Em pedido")
    product = com_foto(
        db_session, make_product(db_session, store, "Peca no pedido", "reservado")
    )
    db_session.commit()

    response = client.patch(
        f"/api/users/me/products/{product.id}",
        json={"name": "Outro nome"},
        headers=auth_headers(69),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PRODUCT_NOT_EDITABLE"
    db_session.refresh(product)
    assert product.name == "Peca no pedido"


def test_republicar_exige_foto(client, db_session, auth_headers):
    """Com o `republish` fora, `publish` e o unico caminho para `ativo`, e ele
    exige foto nos dois sentidos. Era isto que a rota `republish` furava: peca
    despublicada sem imagem voltava com 200 e entrava no feed publico."""
    store = make_store(db_session, 63, "Sem foto")
    product = make_product(db_session, store, "Peca sem foto", "despublicado")
    db_session.commit()

    response = client.post(
        f"/api/users/me/products/{product.id}/publish",
        headers=auth_headers(63),
    )

    assert response.status_code == 422
    assert response.json()["error"]["fields"]["images"]


def test_as_transicoes_devolvem_o_mesmo_contrato(client, db_session, auth_headers):
    """Nenhum teste comparava os schemas das transicoes entre si, e foi por isso
    que `unpublish` passou por dois CIs verdes devolvendo
    `ProductManagementResponse` enquanto o front esperava o schema completo."""
    store = make_store(db_session, 64, "Contrato")
    product = com_foto(
        db_session, make_product(db_session, store, "Peca do contrato", "rascunho")
    )
    db_session.commit()

    respostas = {
        "publish": client.post(
            f"/api/users/me/products/{product.id}/publish",
            headers=auth_headers(64),
        ),
        "unpublish": client.post(
            f"/api/users/me/products/{product.id}/unpublish",
            headers=auth_headers(64),
        ),
        "republicar pelo publish": client.post(
            f"/api/users/me/products/{product.id}/publish",
            headers=auth_headers(64),
        ),
    }

    for rota, response in respostas.items():
        assert response.status_code == 200, f"{rota}: {response.text}"
        corpo = response.json()
        for campo in CAMPOS_DA_TRANSICAO:
            assert campo in corpo, f"{rota} nao devolveu `{campo}`"
        assert corpo["store"]["id"] == store.id, f"{rota}: store.id errado"
        assert isinstance(
            corpo["price"], float
        ), f"{rota}: price veio {type(corpo['price']).__name__}, esperado float"


def test_publish_recusa_peca_de_outro_vendedor(client, db_session, auth_headers):
    """404 e nao 403, pela mesma regra que `_get_owned` documenta: peca de outro
    vendedor responde igual a peca inexistente. A `#230` alargou os estados que
    o `publish` aceita, e essa fronteira nao tinha teste nesta rota."""
    dono = make_store(db_session, 65, "Dono")
    make_store(db_session, 66, "Intruso")
    product = com_foto(
        db_session, make_product(db_session, dono, "Peca do dono", "despublicado")
    )
    db_session.commit()

    response = client.post(
        f"/api/users/me/products/{product.id}/publish",
        headers=auth_headers(66),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"
    assert db_session.get(Product, product.id).status == "despublicado"


@contextmanager
def contar_consultas(db_session) -> Iterator[list[str]]:
    """Guarda o SQL de cada consulta executada dentro do bloco."""
    consultas: list[str] = []

    def registrar(conn, cursor, statement, *args) -> None:
        consultas.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", registrar)
    try:
        yield consultas
    finally:
        event.remove(engine, "before_cursor_execute", registrar)


def test_listagem_devolve_a_capa_de_posicao_zero(client, db_session, auth_headers):
    store = make_store(db_session, 10, "Aurora")
    com_capa = make_product(db_session, store, "Com foto", "ativo")
    # Inseridas fora de ordem: a capa é a de menor posição, não a primeira gravada.
    db_session.add_all(
        [
            ProductImage(
                product=com_capa, image_url="https://exemplo/2.jpg", position=1
            ),
            ProductImage(
                product=com_capa, image_url="https://exemplo/1.jpg", position=0
            ),
        ]
    )
    rascunho = make_product(db_session, store, "Rascunho sem foto", "rascunho")
    db_session.commit()

    response = client.get("/api/users/me/products", headers=auth_headers(10))

    assert response.status_code == 200
    capas = {item["id"]: item["cover_image_url"] for item in response.json()["items"]}
    assert capas == {com_capa.id: "https://exemplo/1.jpg", rascunho.id: None}


def test_listagem_busca_as_capas_sem_uma_consulta_por_peca(
    client, db_session, auth_headers
):
    """N+1 (#86): com uma consulta por peça, a página maior faria mais
    consultas. A capa vem na própria consulta da página, então o número de
    consultas não muda com o número de peças."""
    store = make_store(db_session, 10, "Aurora")

    def nova_peca_com_foto(nome: str) -> None:
        com_foto(db_session, make_product(db_session, store, nome, "ativo"))

    nova_peca_com_foto("Primeira")
    db_session.commit()
    with contar_consultas(db_session) as uma_peca:
        response = client.get("/api/users/me/products", headers=auth_headers(10))
    assert response.status_code == 200

    for nome in ("Segunda", "Terceira", "Quarta"):
        nova_peca_com_foto(nome)
    db_session.commit()
    with contar_consultas(db_session) as quatro_pecas:
        response = client.get("/api/users/me/products", headers=auth_headers(10))

    assert response.status_code == 200
    assert all(item["cover_image_url"] for item in response.json()["items"])
    assert len(quatro_pecas) == len(uma_peca)
    assert sum("product_images" in sql for sql in quatro_pecas) == 1
