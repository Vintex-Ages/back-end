"""Busca por semelhança paginada, filtrada e com distância (back-end#246).

`cosine_distance` só existe no Postgres com pgvector: roda com `pg_session`.
Vetores "one-hot" deixam a distância previsível: o mesmo eixo dá 0, um eixo
diferente dá 1.
"""

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.config import settings
from app.constants.embedding import EMBEDDING_DIM
from app.core.pagination import PageParams
from app.models import Address, Product, Seller, Store, User
from app.repositories.product_repository import ProductRepository
from app.schemas.product_schema import ProductFilters

pytestmark = pytest.mark.postgres

MODELO = settings.GOOGLE_EMBEDDING_MODEL


def eixo(index: int, value: float = 1.0) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    vector[index] = value
    return vector


def loja(db: Session, nome: str, cidade: str | None = None) -> Store:
    store = Store(
        name=nome,
        seller=Seller(
            user=User(name=nome, email=f"{nome.lower()}@test.local", password_hash="x"),
            document_type="CPF",
            document_value=f"{abs(hash(nome)) % 10**11:011d}",
        ),
        address=(
            Address(
                street="Rua", number="1", city=cidade, state="RS", zip_code="90000000"
            )
            if cidade
            else None
        ),
    )
    db.add(store)
    db.flush()
    return store


def peca(
    db: Session,
    store: Store,
    nome: str,
    vetor: list[float] | None,
    *,
    modelo: str | None = MODELO,
    categoria: str | None = None,
    preco: str = "100.00",
    status: str = "ativo",
) -> Product:
    product = Product(
        store=store,
        name=nome,
        price=Decimal(preco),
        category=categoria,
        status=status,
        embedding=vetor,
        embedding_model=modelo if vetor is not None else None,
    )
    db.add(product)
    db.flush()
    return product


def buscar(db: Session, vetor, page=1, page_size=20, modelo=MODELO, **filtros):
    return ProductRepository(db).find_similar(
        vetor,
        modelo,
        PageParams(page=page, page_size=page_size),
        ProductFilters(**filtros),
    )


def ids(rows) -> list[int]:
    return [row["id"] for row in rows]


def test_devolve_pagina_com_total_e_nao_lista_fixa_de_cinco(pg_session: Session):
    store = loja(pg_session, "Aurora")
    pecas = [peca(pg_session, store, f"P{i}", eixo(i)) for i in range(7)]
    pg_session.commit()
    pergunta = eixo(0)
    for i in range(1, 7):
        pergunta[i] = 1.0 / (i + 1)  # aproxima mais as de índice menor

    primeira, total = buscar(pg_session, pergunta, page=1, page_size=3)
    terceira, _ = buscar(pg_session, pergunta, page=3, page_size=3)

    assert total == 7
    assert ids(primeira) == [p.id for p in pecas[:3]]
    assert ids(terceira) == [pecas[6].id]


def test_devolve_a_distancia_de_cada_peca_em_ordem_crescente(pg_session: Session):
    store = loja(pg_session, "Aurora")
    igual = peca(pg_session, store, "Igual", eixo(0))
    oposta = peca(pg_session, store, "Ortogonal", eixo(1))
    pg_session.commit()

    rows, _ = buscar(pg_session, eixo(0))

    assert ids(rows) == [igual.id, oposta.id]
    assert rows[0]["distance"] == pytest.approx(0.0, abs=1e-6)
    assert rows[1]["distance"] == pytest.approx(1.0, abs=1e-6)


def test_filtro_combinado_com_semelhanca_devolve_so_o_que_casa_nos_dois(
    pg_session: Session,
):
    """A mais parecida é de outra categoria: o filtro tira ela, por E lógico."""
    store = loja(pg_session, "Aurora")
    peca(pg_session, store, "Jaqueta igual", eixo(0), categoria="Jaquetas")
    calca_perto = peca(pg_session, store, "Calça perto", eixo(1), categoria="Calças")
    calca_cara = peca(
        pg_session, store, "Calça cara", eixo(1), categoria="Calças", preco="500.00"
    )
    pg_session.commit()
    pergunta = eixo(0)
    pergunta[1] = 0.5

    rows, total = buscar(
        pg_session, pergunta, category="Calças", price_max=Decimal("200")
    )

    assert ids(rows) == [calca_perto.id]
    assert total == 1
    assert calca_cara.id not in ids(rows)


def test_aceita_os_filtros_de_localizacao_da_loja(pg_session: Session):
    """Os mesmos filtros do feed, inclusive cidade, que vem do endereço da loja."""
    poa = loja(pg_session, "Aurora", cidade="Porto Alegre")
    pel = loja(pg_session, "Sul", cidade="Pelotas")
    sem_endereco = loja(pg_session, "Sem")
    de_poa = peca(pg_session, poa, "Em POA", eixo(1))
    peca(pg_session, pel, "Em Pelotas", eixo(0))
    peca(pg_session, sem_endereco, "Sem endereço", eixo(0))
    pg_session.commit()

    rows, _ = buscar(pg_session, eixo(0), city="porto alegre")
    sem_filtro, total = buscar(pg_session, eixo(0))

    assert ids(rows) == [de_poa.id]
    assert total == 3, "sem filtro de cidade, a loja sem endereço continua"


def test_vetor_de_outro_modelo_nao_entra(pg_session: Session):
    """Distância entre espaços vetoriais diferentes é ruído com cara de resultado."""
    store = loja(pg_session, "Aurora")
    do_modelo = peca(pg_session, store, "Mesmo modelo", eixo(1))
    peca(pg_session, store, "Outro modelo", eixo(0), modelo="text-embedding-antigo")
    peca(pg_session, store, "Sem nome de modelo", eixo(0), modelo=None)
    peca(pg_session, store, "Sem vetor", None)
    pg_session.commit()

    rows, total = buscar(pg_session, eixo(0))

    assert ids(rows) == [do_modelo.id]
    assert total == 1


def test_sem_limiar_uma_busca_sem_nada_parecido_ainda_devolve_as_mais_proximas(
    pg_session: Session,
):
    """RN-61: a distância não autoriza cortar. Quem chama decide como rotular."""
    store = loja(pg_session, "Aurora")
    pecas = [peca(pg_session, store, f"P{i}", eixo(i)) for i in (1, 2, 3)]
    pg_session.commit()

    rows, total = buscar(pg_session, eixo(0))  # ortogonal a todas: distância 1

    assert total == 3
    assert sorted(ids(rows)) == sorted(p.id for p in pecas)
    assert all(row["distance"] == pytest.approx(1.0, abs=1e-6) for row in rows)


@pytest.mark.parametrize("status", ["rascunho", "reservado", "vendido", "despublicado"])
def test_so_peca_ativa_entra(pg_session: Session, status: str):
    store = loja(pg_session, "Aurora")
    ativa = peca(pg_session, store, "Ativa", eixo(1))
    peca(pg_session, store, "Fora", eixo(0), status=status)
    pg_session.commit()

    rows, _ = buscar(pg_session, eixo(0))

    assert ids(rows) == [ativa.id]


def test_empate_de_distancia_tem_ordem_estavel(pg_session: Session):
    store = loja(pg_session, "Aurora")
    pecas = [peca(pg_session, store, f"Igual {i}", eixo(0)) for i in range(4)]
    pg_session.commit()

    primeira, _ = buscar(pg_session, eixo(0), page=1, page_size=2)
    segunda, _ = buscar(pg_session, eixo(0), page=2, page_size=2)

    assert ids(primeira) + ids(segunda) == [p.id for p in pecas]
