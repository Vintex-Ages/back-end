import pytest

from app.constants.catalog import CATEGORIES, COLORS, SIZES
from app.models import Product
from app.seeds.lojas import seed_lojas
from app.seeds.pecas import (
    ESTILOS_DA_LOJA,
    FATOR_CONSERVACAO,
    MODELOS,
    STYLES,
    seed_pecas,
)


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


# --- Seed perto da realidade: a recomendação pelo perfil (back-end#253)
# compara o texto da peça com o do estilo, e atributo sorteado não dá match.


def test_modelos_usam_o_vocabulario_do_catalogo():
    for modelo in MODELOS:
        assert modelo.estilo in STYLES, modelo.nome
        assert modelo.categoria in CATEGORIES, modelo.nome
        assert set(modelo.cores) <= set(COLORS), modelo.nome
        assert modelo.preco[0] < modelo.preco[1], modelo.nome


def test_todo_estilo_tem_modelos_e_loja():
    for estilo in STYLES:
        assert any(m.estilo == estilo for m in MODELOS), estilo
        assert any(estilo in estilos for estilos in ESTILOS_DA_LOJA.values()), estilo


def test_peca_herda_estilo_categoria_e_composicao_do_modelo(db_session, lojas):
    products = seed_pecas(db_session)
    db_session.commit()

    for product in products:
        modelo = next(m for m in MODELOS if product.name.startswith(m.nome))
        assert product.style == modelo.estilo
        assert product.category == modelo.categoria
        assert product.composition == modelo.composicao
        assert product.brand in modelo.marcas
        assert product.color in modelo.cores
        assert product.size in SIZES


def test_cada_loja_so_tem_os_seus_estilos(db_session, lojas):
    products = seed_pecas(db_session)
    db_session.commit()

    for product in products:
        assert product.style in ESTILOS_DA_LOJA[product.store.name], product.name
    assert {p.style for p in products} == set(STYLES)


def test_preco_fica_na_faixa_do_modelo_ajustada_pela_conservacao(db_session, lojas):
    products = seed_pecas(db_session)
    db_session.commit()

    for product in products:
        modelo = next(m for m in MODELOS if product.name.startswith(m.nome))
        fator = FATOR_CONSERVACAO[product.condition]
        minimo, maximo = modelo.preco
        assert minimo * fator - 1 <= product.price <= maximo * fator + 1
        assert str(product.price).endswith(".90")


def test_rodar_duas_vezes_nao_duplica(db_session, lojas):
    seed_pecas(db_session)
    db_session.commit()
    primeira = db_session.query(Product).count()

    seed_pecas(db_session)
    db_session.commit()
    assert db_session.query(Product).count() == primeira
