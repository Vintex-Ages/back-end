from app.models import Store
from app.seeds.lojas import seed_lojas


def test_cria_pelo_menos_cinco_lojas_em_tres_cidades(db_session):
    stores = seed_lojas(db_session)
    db_session.commit()

    assert len(stores) >= 5
    cidades = {store.address.city for store in stores}
    assert len(cidades) >= 3
    assert all(store.address.state == "RS" for store in stores)


def test_cada_loja_tem_endereco_vendedor_e_pix(db_session):
    stores = seed_lojas(db_session)
    db_session.commit()

    for store in stores:
        assert store.address is not None
        assert store.address.street and store.address.zip_code
        assert store.seller is not None
        assert store.seller.user is not None
        assert store.pix_key


def test_nomes_sao_plausiveis_nao_genericos(db_session):
    stores = seed_lojas(db_session)
    db_session.commit()

    for store in stores:
        assert not store.name.lower().startswith("loja")


def test_rodar_duas_vezes_nao_duplica(db_session):
    seed_lojas(db_session)
    db_session.commit()
    primeira = db_session.query(Store).count()

    seed_lojas(db_session)
    db_session.commit()
    segunda = db_session.query(Store).count()

    assert primeira == segunda
