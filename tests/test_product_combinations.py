"""Peças que combinam com a peça aberta (BE-US030-1, back-end#328).

A semelhança usa `cosine_distance`, que só existe no Postgres com pgvector:
esses testes rodam com `pg_client` e a marca `postgres`. O 404 e o fallback
sem vetor não comparam vetores e rodam também sem banco de verdade.

Vetores "one-hot" deixam a ordem previsível: o mesmo eixo dá distância 0, um
eixo diferente dá 1.
"""

from decimal import Decimal
from itertools import count

import pytest
from sqlalchemy.orm import Session

from app.config import settings
from app.constants.embedding import EMBEDDING_DIM
from app.controllers.combination_controller import LIMITE_DE_COMBINACOES
from app.models import Product, Seller, Store, User

MODELO = settings.GOOGLE_EMBEDDING_MODEL
_documentos = count(1)


def eixo(index: int, value: float = 1.0) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    vector[index] = value
    return vector


def perto_de(index: int, *outros: tuple[int, float]) -> list[float]:
    """O eixo `index` mais um pouco de outros eixos: quanto maior o peso,
    mais perto daquele eixo a peça fica."""
    vector = eixo(index)
    for outro, peso in outros:
        vector[outro] = peso
    return vector


def loja(db: Session, nome: str) -> Store:
    store = Store(
        name=nome,
        seller=Seller(
            user=User(
                name=nome,
                email=f"{nome.lower().replace(' ', '.')}@test.local",
                password_hash="x",
            ),
            document_type="CPF",
            document_value=f"{next(_documentos):011d}",
        ),
    )
    db.add(store)
    db.flush()
    return store


def peca(
    db: Session,
    store: Store,
    nome: str,
    categoria: str | None,
    vetor: list[float] | None = None,
    *,
    preco: str = "100.00",
    status: str = "ativo",
) -> Product:
    product = Product(
        store=store,
        name=nome,
        category=categoria,
        price=Decimal(preco),
        status=status,
        embedding=vetor,
        embedding_model=MODELO if vetor is not None else None,
    )
    db.add(product)
    db.flush()
    return product


def combinar(client, product_id: int):
    return client.get(f"/api/products/{product_id}/combinations")


def ids(body) -> list[int]:
    return [piece["id"] for piece in body["pieces"]]


# --- Com vetor (Postgres) ----------------------------------------------------


@pytest.mark.postgres
def test_combinar_uma_calca_nao_devolve_nenhuma_calca(pg_client, pg_session):
    """As calças são as mais parecidas no vetor, e mesmo assim nenhuma volta.
    A categoria compara sem acento e sem caixa (RN-41)."""
    store = loja(pg_session, "Aurora")
    origem = peca(pg_session, store, "Calça jeans", "Calças", eixo(0))
    peca(pg_session, store, "Calça igual", "Calças", eixo(0))
    peca(pg_session, store, "Calça sem acento", "calcas", eixo(0))
    sapato = peca(pg_session, store, "Sapato", "Sapatos", perto_de(1, (0, 0.9)))
    camisa = peca(pg_session, store, "Camisa", "Camisas", perto_de(2, (0, 0.5)))
    pg_session.commit()

    response = combinar(pg_client, origem.id)

    assert response.status_code == 200
    body = response.json()
    assert body["match_type"] == "exact"
    assert ids(body) == [sapato.id, camisa.id]
    assert {piece["category"] for piece in body["pieces"]} == {"Sapatos", "Camisas"}


@pytest.mark.postgres
def test_a_peca_de_origem_nunca_aparece(pg_client, pg_session):
    store = loja(pg_session, "Aurora")
    origem = peca(pg_session, store, "Peça sem categoria", None, eixo(0))
    bolsa = peca(pg_session, store, "Bolsa", "Bolsas", eixo(1))
    pg_session.commit()

    body = combinar(pg_client, origem.id).json()

    assert origem.id not in ids(body)
    assert ids(body) == [bolsa.id]


@pytest.mark.postgres
def test_so_volta_peca_ativa(pg_client, pg_session):
    store = loja(pg_session, "Aurora")
    origem = peca(pg_session, store, "Calça", "Calças", eixo(0))
    for status in ("vendido", "reservado", "rascunho", "despublicado"):
        peca(pg_session, store, f"Sapato {status}", "Sapatos", eixo(0), status=status)
    ativo = peca(pg_session, store, "Sapato ativo", "Sapatos", eixo(1))
    pg_session.commit()

    body = combinar(pg_client, origem.id).json()

    assert ids(body) == [ativo.id]


@pytest.mark.postgres
@pytest.mark.parametrize("status", ["vendido", "reservado"])
def test_origem_comprada_responde_200(pg_client, pg_session, status):
    """O gatilho de depois da compra (RN-63): a origem não precisa estar ativa."""
    store = loja(pg_session, "Aurora")
    origem = peca(pg_session, store, "Calça", "Calças", eixo(0), status=status)
    sapato = peca(pg_session, store, "Sapato", "Sapatos", eixo(0))
    pg_session.commit()

    response = combinar(pg_client, origem.id)

    assert response.status_code == 200
    assert response.json()["match_type"] == "exact"
    assert ids(response.json()) == [sapato.id]


@pytest.mark.postgres
def test_conjunto_de_duas_lojas_traz_a_loja_e_o_total(pg_client, pg_session):
    aurora = loja(pg_session, "Aurora")
    bento = loja(pg_session, "Bento")
    origem = peca(pg_session, aurora, "Calça", "Calças", eixo(0))
    sapato = peca(pg_session, aurora, "Sapato", "Sapatos", eixo(0), preco="89.90")
    bolsa = peca(pg_session, bento, "Bolsa", "Bolsas", eixo(1), preco="120.50")
    pg_session.commit()

    body = combinar(pg_client, origem.id).json()

    assert ids(body) == [sapato.id, bolsa.id]
    assert [piece["store"] for piece in body["pieces"]] == [
        {"id": aurora.id, "name": "Aurora"},
        {"id": bento.id, "name": "Bento"},
    ]
    assert body["total_amount"] == pytest.approx(210.40)
    assert body["total_amount"] == pytest.approx(
        sum(piece["price"] for piece in body["pieces"])
    )


@pytest.mark.postgres
def test_preco_e_loja_sao_os_do_registro(pg_client, pg_session):
    """Nunca inventa peça, preço ou loja (RN-65)."""
    store = loja(pg_session, "Aurora")
    origem = peca(pg_session, store, "Calça", "Calças", eixo(0))
    peca(pg_session, store, "Sapato", "Sapatos", eixo(0), preco="59.99")
    peca(pg_session, store, "Bolsa", "Bolsas", eixo(1), preco="149.00")
    pg_session.commit()

    body = combinar(pg_client, origem.id).json()

    assert body["pieces"]
    for piece in body["pieces"]:
        registro = pg_session.get(Product, piece["id"])
        assert registro is not None
        assert piece["price"] == pytest.approx(float(registro.price))
        assert piece["store"] == {"id": registro.store.id, "name": registro.store.name}
        assert piece["category"] == registro.category


@pytest.mark.postgres
def test_devolve_no_maximo_o_limite_na_ordem_da_semelhanca(pg_client, pg_session):
    store = loja(pg_session, "Aurora")
    origem = peca(pg_session, store, "Calça", "Calças", eixo(0))
    pecas = [
        peca(
            pg_session,
            store,
            f"Sapato {i}",
            "Sapatos",
            perto_de(i + 1, (0, 1 - i / 10)),
        )
        for i in range(LIMITE_DE_COMBINACOES + 2)
    ]
    pg_session.commit()

    body = combinar(pg_client, origem.id).json()

    assert ids(body) == [p.id for p in pecas[:LIMITE_DE_COMBINACOES]]


@pytest.mark.postgres
def test_origem_com_vetor_sem_peca_parecida_cai_para_o_fallback(pg_client, pg_session):
    """As outras peças ainda não têm vetor (catálogo sem backfill): vem o
    catálogo de outras categorias, e não lista vazia (RN-61)."""
    store = loja(pg_session, "Aurora")
    origem = peca(pg_session, store, "Calça", "Calças", eixo(0))
    sapato = peca(pg_session, store, "Sapato", "Sapatos")
    peca(pg_session, store, "Outra calça", "Calças")
    pg_session.commit()

    body = combinar(pg_client, origem.id).json()

    assert body["match_type"] == "fallback"
    assert ids(body) == [sapato.id]


# --- Sem vetor (roda também sem Postgres) ------------------------------------


def test_peca_inexistente_responde_404(client):
    response = combinar(client, 999999)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


def test_origem_sem_vetor_devolve_outras_categorias_em_fallback(client, db_session):
    store = loja(db_session, "Aurora")
    origem = peca(db_session, store, "Calça", "Calças")
    peca(db_session, store, "Outra calça", "calças")
    sapato = peca(db_session, store, "Sapato", "Sapatos", preco="80.00")
    bolsa = peca(db_session, store, "Bolsa", "Bolsas", preco="40.00")
    db_session.commit()

    response = combinar(client, origem.id)

    assert response.status_code == 200
    body = response.json()
    assert body["match_type"] == "fallback"
    assert set(ids(body)) == {sapato.id, bolsa.id}
    assert body["total_amount"] == pytest.approx(120.0)


def test_resposta_segue_o_contrato(client, db_session):
    store = loja(db_session, "Aurora")
    origem = peca(db_session, store, "Calça", "Calças")
    peca(db_session, store, "Sapato", "Sapatos")
    db_session.commit()

    body = combinar(client, origem.id).json()

    assert set(body) == {"pieces", "match_type", "total_amount"}
    assert set(body["pieces"][0]) == {
        "id",
        "name",
        "price",
        "category",
        "cover_image_url",
        "store",
    }
    assert set(body["pieces"][0]["store"]) == {"id", "name"}
