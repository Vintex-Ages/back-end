"""Seed de peças e imagens, distribuídas entre as lojas de `app.seeds.lojas`.

Uso::

    python -m app.seeds.pecas

Rode `python -m app.seeds.lojas` antes. Idempotente: se já houver o número
alvo de peças, não faz nada.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.constants.catalog import COLORS as CATALOGO_CORES
from app.constants.catalog import CONDITIONS as CATALOGO_CONSERVACAO
from app.core.clock import utcnow_naive
from app.database import SessionLocal
from app.models import Product, ProductImage, Store

logger = logging.getLogger("vintex.seeds")

TOTAL = 60

# Valores de atributo — o mesmo vocabulário que os filtros do catálogo esperam.
TIPOS: dict[str, list[str]] = {
    "Roupas": ["Camiseta", "Calça jeans", "Jaqueta", "Vestido", "Moletom", "Camisa"],
    "Sapatos": ["Tênis", "Bota", "Sandália", "Sapatênis", "Scarpin"],
    "Acessórios": ["Bolsa", "Cinto", "Boné", "Óculos de sol", "Carteira", "Mochila"],
}
SIZES: dict[str, list[str]] = {
    "Roupas": ["PP", "P", "M", "G", "GG"],
    "Sapatos": ["36", "38", "40", "42"],
    "Acessórios": ["P", "M", "G"],
}
BRANDS = [
    "Levi's",
    "Nike",
    "Adidas",
    "Zara",
    "C&A",
    "Renner",
    "Hering",
    "Lacoste",
    "Farm",
    "Osklen",
]
# Vindas de `app/constants/catalog.py`: sao o vocabulario que os filtros
# comparam por igualdade e que o prompt da IA cita. Duas copias divergiriam.
COLORS = list(CATALOGO_CORES)
CONDITIONS = list(CATALOGO_CONSERVACAO)
STYLES = [
    "vintage-80-90",
    "streetwear",
    "alfaiataria",
    "gotico-dark",
    "boho-romantico",
    "y2k",
]


def _status_for(index: int) -> str:
    if index < 8:
        return "vendido"
    if index < 12:
        return "despublicado"
    return "ativo"


def _sold_at_for(index: int) -> datetime | None:
    """Data da venda das oito vendidas, espalhada pelos últimos 42 dias.

    Uma a cada seis dias. Sem data nenhuma, o resumo financeiro (back-end#146)
    mostra R$ 0,00 nos três períodos, porque não existe checkout nesta sprint e
    o seed é o único lugar que cria peça vendida.

    O espaçamento é sobre o índice global, e as peças são distribuídas entre as
    lojas (`stores[index % len(stores)]`): as vendidas de uma mesma loja ficam
    `6 * len(stores)` dias apart, ou seja 42 dias com sete lojas. Consequência,
    medida: um vendedor tem uma venda só, e `month`, `30d` e `all` devolvem o
    mesmo número para ele. Para o seletor de período mostrar valores diferentes
    na demonstração, o seed precisaria dar mais de uma venda à mesma loja —
    decisão de dado de demonstração, não desta função.
    """
    if _status_for(index) != "vendido":
        return None
    return utcnow_naive() - timedelta(days=index * 6)


def seed_pecas(session: Session, *, total: int = TOTAL) -> list[Product]:
    """Cria `total` peças distribuídas entre as lojas. Não faz commit."""
    if session.query(Product).count() >= total:
        return session.query(Product).all()

    stores: list[Store] = session.query(Store).order_by(Store.id).all()
    if not stores:
        raise RuntimeError("Nenhuma loja. Rode `python -m app.seeds.lojas` primeiro.")

    rng = random.Random(42)
    products: list[Product] = []
    for index in range(total):
        store = stores[index % len(stores)]
        category = rng.choice(list(TIPOS))
        tipo = rng.choice(TIPOS[category])
        brand = rng.choice(BRANDS)
        color = rng.choice(COLORS)
        size = rng.choice(SIZES[category])
        condition = rng.choice(CONDITIONS)
        price = Decimal(str(round(rng.uniform(19.9, 459.9), 2)))

        product = Product(
            store=store,
            name=f"{brand} {tipo} {color}",
            description=(
                f"{tipo} {brand}, cor {color.lower()}, tamanho {size}. "
                f"Estado: {condition.lower()}."
            ),
            category=category,
            style=rng.choice(STYLES),
            brand=brand,
            color=color,
            size=size,
            condition=condition,
            price=price,
            quantity=1,
            status=_status_for(index),
            sold_at=_sold_at_for(index),
        )
        for position in range(rng.randint(1, 3)):
            product.images.append(
                ProductImage(
                    image_url=f"https://picsum.photos/seed/vintex-{index}-{position}/600/800",
                    position=position,
                )
            )
        session.add(product)
        products.append(product)

    session.flush()
    return products


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    session = SessionLocal()
    try:
        products = seed_pecas(session)
        session.commit()
        vendidas = sum(1 for p in products if p.status == "vendido")
        logger.info("Peças no banco: %d (%d vendidas).", len(products), vendidas)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    run()
