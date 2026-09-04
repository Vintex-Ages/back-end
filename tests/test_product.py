from decimal import Decimal

from app.models.address import Address
from app.models.product import Product
from app.models.product_image import ProductImage
from app.models.store import Store


def test_product_persists_with_store_and_images(db_session):
    product = Product(
        store=Store(
            seller_id=1,
            name="Brechó Aurora",
            address=Address(
                street="Rua da Praia",
                number="100",
                city="Porto Alegre",
                state="RS",
                zip_code="90010000",
            ),
        ),
        name="Jaqueta jeans vintage",
        description="Jaqueta oversized, lavagem clara.",
        category="Jaquetas",
        style="Vintage",
        brand="Levi's",
        color="Azul",
        size="M",
        condition="Bom",
        price=Decimal("149.90"),
        images=[
            ProductImage(image_url="https://cdn.vintex.test/0.jpg", position=0),
        ],
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    saved = db_session.get(Product, product.id)

    assert saved is not None
    assert saved.name == "Jaqueta jeans vintage"
    assert saved.quantity == 1
    assert saved.status == "ativo"
    assert saved.store.name == "Brechó Aurora"
    assert saved.images[0].image_url == "https://cdn.vintex.test/0.jpg"
