import pytest

from app.models import Product
from app.seeds.lojas import seed_lojas
from app.seeds.pecas import seed_pecas


@pytest.fixture
def lojas(db_session):
    seed_lojas(db_session)
    db_session.commit()


def test_exige_lojas(db_session):
    with pytest.raises(RuntimeError):
        seed_pecas(db_session)


def test_cria_pelo_menos_50_pecas_com_5_vendidas(db_session, lojas):
    products = seed_pecas(db_session)
    db_session.commit()

    assert len(products) >= 50
    vendidas = [p for p in products if p.status == "vendido"]
    assert len(vendidas) >= 5


def test_toda_peca_tem_atributos_e_imagem(db_session, lojas):
    products = seed_pecas(db_session)
    db_session.commit()

    for product in products:
        assert product.category and product.size and product.brand
        assert product.color and product.condition and product.description
        assert product.price > 0
        assert product.quantity == 1
        assert len(product.images) >= 1
        assert product.images[0].position == 0


def test_distribuida_entre_lojas_com_precos_variados(db_session, lojas):
    products = seed_pecas(db_session)
    db_session.commit()

    lojas_usadas = {p.store_id for p in products}
    assert len(lojas_usadas) >= 3
    precos = {p.price for p in products}
    assert min(precos) < 100 and max(precos) > 200


def test_rodar_duas_vezes_nao_duplica(db_session, lojas):
    seed_pecas(db_session)
    db_session.commit()
    primeira = db_session.query(Product).count()

    seed_pecas(db_session)
    db_session.commit()
    assert db_session.query(Product).count() == primeira
