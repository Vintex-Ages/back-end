from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.address import Address
from app.models.product import Product
from app.models.seller import Seller
from app.models.store import Store
from app.models.user import User

pytestmark = pytest.mark.postgres


def criar_loja(db: Session, nome: str) -> Store:
    user = User(
        name=f"{nome} owner",
        email=f"{nome.lower().replace(' ', '.')}@test.local",
        password_hash="not-a-real-password",
    )
    seller = Seller(
        user=user,
        document_type="CPF",
        document_value=str(abs(hash(nome)))[:11].zfill(11),
    )
    address = Address(
        street="Rua dos Andradas",
        number="100",
        city="Porto Alegre",
        state="RS",
        zip_code="90020000",
    )
    store = Store(name=nome, seller=seller, address=address)
    db.add(store)
    db.flush()
    return store


def criar_peca(
    db: Session,
    store: Store,
    nome: str,
    categoria: str = "Jaquetas",
    marca: str = "Levi's",
    status: str = "ativo",
) -> Product:
    product = Product(
        store=store,
        name=nome,
        category=categoria,
        brand=marca,
        price=Decimal("99.90"),
        status=status,
    )
    db.add(product)
    db.flush()
    return product


def test_busca_encontra_ignorando_acento_e_caixa(
    pg_client: TestClient, pg_session: Session
) -> None:
    loja = criar_loja(pg_session, "Brechó Aurora")
    criar_peca(pg_session, loja, "Jaquêta Jeans CLÁSSICA")
    pg_session.commit()

    for termo in ("jaqueta", "JAQUETA", "Jaquêta"):
        resposta = pg_client.get("/api/products", params={"q": termo})

        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["match_type"] == "exact"
        assert corpo["suggestions"] is None
        assert [item["name"] for item in corpo["items"]] == ["Jaquêta Jeans CLÁSSICA"]
        assert corpo["total"] == 1


def test_busca_encontra_por_pedaco_de_palavra(
    pg_client: TestClient, pg_session: Session
) -> None:
    loja = criar_loja(pg_session, "Brechó Central")
    criar_peca(pg_session, loja, "Jaqueta de Couro")
    pg_session.commit()

    resposta = pg_client.get("/api/products", params={"q": "jaque"})

    assert resposta.status_code == 200
    assert resposta.json()["total"] == 1


def test_busca_sem_resultado_devolve_alternativas_e_motivo(
    pg_client: TestClient, pg_session: Session
) -> None:
    loja = criar_loja(pg_session, "Brechó Sul")
    criar_peca(pg_session, loja, "Jaqueta Corta-Vento", categoria="Jaquetas")
    pg_session.commit()

    resposta = pg_client.get("/api/products", params={"q": "jaqueta xadrez"})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["match_type"] == "fallback"
    assert corpo["items"] == []
    assert corpo["total"] == 0
    assert "jaqueta xadrez" in corpo["suggestions"]["reason"]
    assert [item["name"] for item in corpo["suggestions"]["items"]] == [
        "Jaqueta Corta-Vento"
    ]


def test_termo_sem_nenhuma_relacao_ainda_devolve_o_catalogo(
    pg_client: TestClient, pg_session: Session
) -> None:
    loja = criar_loja(pg_session, "Brechó Norte")
    criar_peca(pg_session, loja, "Bolsa de Palha", categoria="Bolsas", marca="Osklen")
    pg_session.commit()

    resposta = pg_client.get("/api/products", params={"q": "zzzzz"})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["match_type"] == "fallback"
    assert corpo["items"] == []
    assert len(corpo["suggestions"]["items"]) == 1


def test_catalogo_vazio_devolve_vazio_sem_erro(
    pg_client: TestClient, pg_session: Session
) -> None:
    resposta = pg_client.get("/api/products", params={"q": "jaqueta"})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["items"] == []
    assert corpo["total"] == 0
    assert corpo["suggestions"] is None


def test_feed_sem_termo_mantem_o_contrato_anterior(
    pg_client: TestClient, pg_session: Session
) -> None:
    loja = criar_loja(pg_session, "Brechó Leste")
    criar_peca(pg_session, loja, "Camisa Linho")
    pg_session.commit()

    resposta = pg_client.get("/api/products")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["match_type"] == "exact"
    assert corpo["suggestions"] is None
    assert corpo["total"] == 1
    assert corpo["page"] == 1
    assert corpo["page_size"] == 20


def test_peca_vendida_nao_aparece_na_busca(
    pg_client: TestClient, pg_session: Session
) -> None:
    loja = criar_loja(pg_session, "Brechó Oeste")
    criar_peca(pg_session, loja, "Jaqueta Vendida", status="vendido")
    criar_peca(pg_session, loja, "Jaqueta Ativa")
    pg_session.commit()

    resposta = pg_client.get("/api/products", params={"q": "jaqueta"})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert [item["name"] for item in corpo["items"]] == ["Jaqueta Ativa"]
