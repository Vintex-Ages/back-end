"""Seed de peças e imagens, distribuídas entre as lojas de `app.seeds.lojas`.

Uso::

    python -m app.seeds.pecas

Rode `python -m app.seeds.lojas` antes. Idempotente: se já houver o número
alvo de peças, não faz nada.

As peças saem de `MODELOS`, um catálogo de peças plausíveis de brechó por
estilo: cada modelo amarra tipo, marcas, cores, faixa de preço, composição e
uma descrição no vocabulário do estilo. Antes, cada atributo era sorteado
sozinho, e o seed criava "Lacoste Scarpin" por R$ 48 com estilo gótico. A
recomendação pelo perfil (back-end#253) compara o texto da peça com o texto
do estilo escolhido; com atributos sorteados, ela não tinha o que acertar.
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.constants.catalog import CATEGORIES
from app.constants.catalog import COLORS as CATALOGO_CORES
from app.constants.catalog import CONDITIONS as CATALOGO_CONSERVACAO
from app.constants.styles import STYLES as CATALOGO_ESTILOS
from app.core.clock import utcnow_naive
from app.database import SessionLocal
from app.models import Product, ProductImage, Store

logger = logging.getLogger("vintex.seeds")

TOTAL = 60

# Vindas de `app/constants/catalog.py`: sao o vocabulario que os filtros
# comparam por igualdade e que o prompt da IA cita. Duas copias divergiriam.
COLORS = list(CATALOGO_CORES)
CONDITIONS = list(CATALOGO_CONSERVACAO)
STYLES = [estilo["value"] for estilo in CATALOGO_ESTILOS]

SIZES: dict[str, list[str]] = {
    "Roupas": ["PP", "P", "M", "G", "GG"],
    "Sapatos": ["36", "38", "40", "42"],
    # O catálogo não tem "tamanho único": acessório usa a faixa de letras.
    "Acessórios": ["P", "M", "G"],
}


@dataclass(frozen=True)
class Modelo:
    """Uma peça plausível de brechó, de um estilo só.

    `preco` é a faixa em reais de uma peça seminova; a conservação sorteada
    sobe ou desce o valor (`FATOR_CONSERVACAO`). `descricao` fala a língua do
    estilo, porque é ela que mais pesa no vetor da peça.
    """

    estilo: str
    categoria: str
    tipo: str
    nome: str
    marcas: tuple[str, ...]
    cores: tuple[str, ...]
    preco: tuple[int, int]
    composicao: str
    descricao: str


MODELOS: tuple[Modelo, ...] = (
    # --- Vintage 80s / 90s: jaquetas de couro, jeans pesados, peças históricas
    Modelo(
        "vintage-80-90",
        "Roupas",
        "Jaqueta",
        "Jaqueta jeans trucker anos 90",
        ("Levi's", "Lee", "Wrangler"),
        ("Azul", "Preto"),
        (140, 260),
        "100% algodão",
        "Jeans pesado de lavagem clara, modelagem reta e botões de metal. "
        "Peça original dos anos 90.",
    ),
    Modelo(
        "vintage-80-90",
        "Roupas",
        "Calça jeans",
        "Calça jeans mom cintura alta",
        ("Levi's", "Lee", "Forum"),
        ("Azul", "Preto"),
        (90, 180),
        "100% algodão",
        "Corte mom dos anos 90, cintura alta e lavagem estonada. "
        "Jeans grosso, sem elastano.",
    ),
    Modelo(
        "vintage-80-90",
        "Roupas",
        "Jaqueta",
        "Jaqueta de couro motoqueiro",
        ("Ellus", "Forum", "Zara"),
        ("Preto",),
        (220, 420),
        "Couro legítimo, forro em poliéster",
        "Jaqueta de couro com zíper diagonal e gola larga, no estilo dos "
        "anos 80. Couro encorpado, já amaciado pelo tempo.",
    ),
    Modelo(
        "vintage-80-90",
        "Roupas",
        "Camiseta",
        "Camiseta de banda anos 90",
        ("Hering", "Hanes"),
        ("Preto", "Branco"),
        (45, 110),
        "100% algodão",
        "Camiseta de banda com estampa desbotada pelo tempo, gola canelada e "
        "malha encorpada. Peça histórica dos anos 90.",
    ),
    Modelo(
        "vintage-80-90",
        "Sapatos",
        "Tênis",
        "Tênis cano alto clássico",
        ("Converse", "Adidas", "Nike"),
        ("Branco", "Preto", "Vermelho"),
        (120, 260),
        "Lona e borracha",
        "Tênis cano alto retrô de solado vulcanizado, o clássico dos anos 80.",
    ),
    Modelo(
        "vintage-80-90",
        "Acessórios",
        "Cinto",
        "Cinto de couro com fivela western",
        ("Levi's", "Ellus"),
        ("Bege", "Preto"),
        (60, 140),
        "Couro bovino",
        "Cinto largo de couro com fivela de metal trabalhada, estilo western "
        "dos anos 80.",
    ),
    # --- Streetwear urbano: oversized, moletons gráficos, sneakers raros
    Modelo(
        "streetwear",
        "Roupas",
        "Moletom",
        "Moletom oversized com capuz",
        ("Nike", "Adidas", "Champion"),
        ("Preto", "Azul", "Verde", "Branco"),
        (110, 240),
        "80% algodão, 20% poliéster",
        "Moletom oversized com capuz e bolso canguru, estampa gráfica no "
        "peito. Caimento largo, felpado por dentro.",
    ),
    Modelo(
        "streetwear",
        "Roupas",
        "Camiseta",
        "Camiseta oversized estampada",
        ("Vans", "Nike", "Element"),
        ("Estampado", "Preto", "Branco"),
        (50, 120),
        "100% algodão",
        "Camiseta de malha pesada, modelagem oversized e estampa gráfica "
        "grande nas costas.",
    ),
    Modelo(
        "streetwear",
        "Roupas",
        "Calça",
        "Calça cargo larga",
        ("Nike", "Adidas", "Element"),
        ("Preto", "Verde", "Bege"),
        (100, 210),
        "100% algodão (sarja)",
        "Calça cargo de sarja com bolsos laterais e barra com regulagem. "
        "Caimento largo, visual de rua.",
    ),
    Modelo(
        "streetwear",
        "Sapatos",
        "Tênis",
        "Tênis de basquete cano médio",
        ("Nike", "Adidas", "Fila"),
        ("Branco", "Preto", "Vermelho"),
        (180, 420),
        "Couro sintético e borracha",
        "Sneaker de basquete chunky, solado alto e amortecido. "
        "Modelo de coleção, difícil de achar.",
    ),
    Modelo(
        "streetwear",
        "Acessórios",
        "Boné",
        "Boné aba curva",
        ("New Era", "Nike", "Vans"),
        ("Preto", "Azul", "Verde"),
        (45, 120),
        "100% algodão",
        "Boné de aba curva com logo bordado e regulagem atrás.",
    ),
    Modelo(
        "streetwear",
        "Acessórios",
        "Mochila",
        "Mochila urbana",
        ("Nike", "Adidas", "Jansport"),
        ("Preto", "Azul", "Verde"),
        (90, 200),
        "Poliéster",
        "Mochila com compartimento para notebook e alças acolchoadas, visual "
        "esportivo urbano.",
    ),
    # --- Alfaiataria & elegância: blazers estruturados, seda, cortes clássicos
    Modelo(
        "alfaiataria",
        "Roupas",
        "Blazer",
        "Blazer estruturado de alfaiataria",
        ("Zara", "Le Lis Blanc", "Shoulder"),
        ("Preto", "Bege", "Azul"),
        (130, 320),
        "Poliéster e viscose, forro em acetato",
        "Blazer de corte reto com ombreiras leves e botões forrados. "
        "Alfaiataria de caimento estruturado.",
    ),
    Modelo(
        "alfaiataria",
        "Roupas",
        "Camisa",
        "Camisa de seda",
        ("Animale", "Le Lis Blanc", "Shoulder"),
        ("Branco", "Bege", "Azul"),
        (110, 260),
        "100% seda",
        "Camisa de seda de caimento fluido, punho com abotoadura e gola "
        "clássica. Elegante para o trabalho.",
    ),
    Modelo(
        "alfaiataria",
        "Roupas",
        "Calça",
        "Calça pantalona de alfaiataria",
        ("Zara", "Animale", "Shoulder"),
        ("Preto", "Bege", "Branco"),
        (90, 220),
        "Viscose e elastano",
        "Calça pantalona de cintura alta, com pregas e vinco marcado. "
        "Corte clássico de alfaiataria.",
    ),
    Modelo(
        "alfaiataria",
        "Sapatos",
        "Scarpin",
        "Scarpin de couro bico fino",
        ("Arezzo", "Schutz", "Santa Lolla"),
        ("Preto", "Bege", "Vermelho"),
        (120, 280),
        "Couro legítimo",
        "Scarpin de salto médio e bico fino, couro macio. Clássico e elegante.",
    ),
    Modelo(
        "alfaiataria",
        "Sapatos",
        "Mocassim",
        "Mocassim de couro",
        ("Democrata", "Reserva", "Arezzo"),
        ("Preto", "Bege"),
        (140, 300),
        "Couro legítimo",
        "Mocassim de couro com costura aparente e sola de couro. "
        "Acabamento de sapato social.",
    ),
    Modelo(
        "alfaiataria",
        "Acessórios",
        "Bolsa",
        "Bolsa estruturada de couro",
        ("Arezzo", "Schutz", "Santa Lolla"),
        ("Preto", "Bege", "Branco"),
        (150, 380),
        "Couro legítimo",
        "Bolsa de mão estruturada, alça de ombro removível e ferragens "
        "douradas. Peça clássica e elegante.",
    ),
    # --- Gótico & dark: tons escuros, coturnos tratorados, rendas e couro
    Modelo(
        "gotico-dark",
        "Sapatos",
        "Bota",
        "Coturno tratorado de couro",
        ("Dr. Martens", "Democrata"),
        ("Preto",),
        (180, 450),
        "Couro legítimo, solado de borracha",
        "Coturno de cano médio com solado tratorado e oito ilhoses. "
        "Couro preto, visual dark.",
    ),
    Modelo(
        "gotico-dark",
        "Roupas",
        "Vestido",
        "Vestido midi de renda",
        ("Zara", "Forum", "Lança Perfume"),
        ("Preto", "Vermelho"),
        (90, 210),
        "Renda de poliamida, forro em viscose",
        "Vestido midi de renda com mangas transparentes e decote quadrado. "
        "Romântico e sombrio, em tom escuro.",
    ),
    Modelo(
        "gotico-dark",
        "Roupas",
        "Casaco",
        "Sobretudo longo de lã",
        ("Zara", "Ellus", "Forum"),
        ("Preto",),
        (180, 380),
        "Lã e poliéster",
        "Sobretudo longo com gola larga e cinto na cintura. Tom escuro, "
        "caimento pesado.",
    ),
    Modelo(
        "gotico-dark",
        "Roupas",
        "Blusa",
        "Blusa de tela com renda",
        ("Zara", "Forum"),
        ("Preto",),
        (60, 130),
        "Poliamida e elastano",
        "Blusa justa de tela transparente, mangas longas e detalhes de renda. "
        "Estética dark.",
    ),
    Modelo(
        "gotico-dark",
        "Acessórios",
        "Cinto",
        "Cinto de couro com rebites",
        ("Zara", "Ellus"),
        ("Preto",),
        (50, 120),
        "Couro sintético e metal",
        "Cinto de couro preto com rebites e fivela de metal escuro.",
    ),
    Modelo(
        "gotico-dark",
        "Acessórios",
        "Bolsa",
        "Bolsa transversal com tachas",
        ("Zara", "Santa Lolla"),
        ("Preto",),
        (70, 160),
        "Couro sintético",
        "Bolsa transversal pequena em couro preto, com tachas e corrente.",
    ),
    # --- Boho chic & romântico: vestidos fluidos, florais, tecidos naturais
    Modelo(
        "boho-romantico",
        "Roupas",
        "Vestido",
        "Vestido longo floral",
        ("Farm", "Antix", "Cantão"),
        ("Estampado", "Branco", "Verde"),
        (120, 260),
        "100% viscose",
        "Vestido longo e fluido com estampa floral, alças finas e saia evasê. "
        "Tecido leve e romântico.",
    ),
    Modelo(
        "boho-romantico",
        "Roupas",
        "Blusa",
        "Bata de linho bordada",
        ("Farm", "Cantão", "Antix"),
        ("Branco", "Bege"),
        (70, 160),
        "100% linho",
        "Bata ampla de linho com bordado à mão na gola e mangas bufantes. "
        "Tecido natural, fresco.",
    ),
    Modelo(
        "boho-romantico",
        "Roupas",
        "Saia",
        "Saia longa estampada",
        ("Farm", "Antix"),
        ("Estampado", "Vermelho", "Verde"),
        (80, 170),
        "100% viscose",
        "Saia longa de cintura alta, com babados e estampa floral. " "Caimento fluido.",
    ),
    Modelo(
        "boho-romantico",
        "Sapatos",
        "Sandália",
        "Rasteira de couro trançado",
        ("Arezzo", "Dakota", "Cantão"),
        ("Bege", "Branco"),
        (60, 150),
        "Couro legítimo",
        "Rasteira de tiras de couro trançado à mão, solado baixo e "
        "confortável. Toque artesanal.",
    ),
    Modelo(
        "boho-romantico",
        "Acessórios",
        "Bolsa",
        "Bolsa de palha com franjas",
        ("Farm", "Cantão", "Arezzo"),
        ("Bege",),
        (60, 150),
        "Palha natural e algodão",
        "Bolsa de palha trançada com franjas e alça de couro. "
        "Fibra natural, feita à mão.",
    ),
    Modelo(
        "boho-romantico",
        "Acessórios",
        "Chapéu",
        "Chapéu de palha aba larga",
        ("Farm", "Cantão"),
        ("Bege",),
        (50, 120),
        "Palha natural",
        "Chapéu de palha natural com aba larga e fita de tecido floral.",
    ),
    # --- Y2K anos 2000: cintura baixa, bolsas baguete, óculos retrô
    Modelo(
        "y2k",
        "Roupas",
        "Calça jeans",
        "Calça jeans cintura baixa flare",
        ("Ellus", "Colcci", "Triton"),
        ("Azul", "Branco"),
        (90, 200),
        "98% algodão, 2% elastano",
        "Calça de cintura baixa com boca de sino e lavagem média, o jeans "
        "dos anos 2000.",
    ),
    Modelo(
        "y2k",
        "Roupas",
        "Camiseta",
        "Baby look cropped estampada",
        ("Colcci", "Triton", "Zara"),
        ("Estampado", "Branco", "Vermelho"),
        (40, 100),
        "Algodão e elastano",
        "Baby look justa e cropped, com estampa brilhante. " "Clássico dos anos 2000.",
    ),
    Modelo(
        "y2k",
        "Roupas",
        "Saia",
        "Minissaia jeans cintura baixa",
        ("Colcci", "Triton", "Zara"),
        ("Azul", "Preto"),
        (60, 140),
        "98% algodão, 2% elastano",
        "Minissaia de cintura baixa com cinto de ilhoses. Y2K anos 2000.",
    ),
    Modelo(
        "y2k",
        "Sapatos",
        "Tênis",
        "Tênis plataforma",
        ("Fila", "Puma", "Converse"),
        ("Branco", "Preto"),
        (120, 260),
        "Couro sintético e borracha",
        "Tênis de plataforma alta com solado chunky, febre dos anos 2000.",
    ),
    Modelo(
        "y2k",
        "Acessórios",
        "Bolsa",
        "Bolsa baguete de ombro",
        ("Colcci", "Zara", "Santa Lolla"),
        ("Branco", "Vermelho", "Azul", "Preto"),
        (70, 170),
        "Couro sintético",
        "Bolsa baguete pequena de alça curta e fecho de metal. " "Ícone dos anos 2000.",
    ),
    Modelo(
        "y2k",
        "Acessórios",
        "Óculos de sol",
        "Óculos de sol oval retrô",
        ("Chilli Beans", "Zara"),
        ("Preto", "Vermelho", "Branco"),
        (50, 120),
        "Acetato",
        "Óculos de sol de lente oval pequena e armação fina, retrô anos 2000.",
    ),
)

# Tipo de peça por categoria, saído dos modelos (o teste de vocabulário
# confere que as categorias são as do catálogo).
TIPOS: dict[str, list[str]] = {
    categoria: sorted({m.tipo for m in MODELOS if m.categoria == categoria})
    for categoria in CATEGORIES
}

# Cada brechó tem uma cara: a página da loja mostra um acervo coerente, não
# um pouco de tudo. Loja que não estiver aqui recebe peças de todos os estilos.
ESTILOS_DA_LOJA: dict[str, tuple[str, ...]] = {
    "Brechó Mercado Público": ("vintage-80-90", "alfaiataria"),
    "Garimpo da Redenção": ("boho-romantico", "vintage-80-90", "y2k"),
    "Roupa Rodada": ("streetwear", "y2k"),
    "Segunda Chance Modas": ("alfaiataria", "boho-romantico"),
    "Baú da Vó Nair": ("vintage-80-90", "boho-romantico"),
    "Desapego Serrano": ("alfaiataria", "gotico-dark"),
    "Ateliê Reviver": ("gotico-dark", "streetwear", "y2k"),
}

# Brechó tem mais peça usada que nova: pesos aproximados do que se vê à venda.
PESO_CONSERVACAO: dict[str, int] = {
    "Novo com etiqueta": 10,
    "Seminovo": 40,
    "Usado": 35,
    "Marcas de uso": 15,
}
FATOR_CONSERVACAO: dict[str, float] = {
    "Novo com etiqueta": 1.25,
    "Seminovo": 1.0,
    "Usado": 0.8,
    "Marcas de uso": 0.6,
}
NOTA_CONSERVACAO: dict[str, str] = {
    "Novo com etiqueta": "Nunca usada, ainda com etiqueta.",
    "Seminovo": "Usada poucas vezes, sem marcas aparentes.",
    "Usado": "Em bom estado, com o desgaste natural do uso.",
    "Marcas de uso": "Tem marcas de uso visíveis nas fotos; o preço já considera isso.",
}


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


def _estilo_para(store: Store, rodada: int) -> str:
    """Os estilos da loja em rodízio: cada loja passa por todos os seus."""
    estilos = ESTILOS_DA_LOJA.get(store.name, tuple(STYLES))
    return estilos[rodada % len(estilos)]


def _preco(modelo: Modelo, condicao: str, rng: random.Random) -> Decimal:
    """Faixa do modelo ajustada pela conservação, terminada em ,90."""
    minimo, maximo = modelo.preco
    valor = rng.uniform(minimo, maximo) * FATOR_CONSERVACAO[condicao]
    return Decimal(f"{max(math.floor(valor), 19)}.90")


def _descricao(modelo: Modelo, color: str, size: str, condition: str) -> str:
    """Como o vendedor escreveria: o modelo, a cor, o tamanho e o estado.
    Acessório não cita tamanho, que para bolsa ou óculos não diz nada."""
    tamanho = "" if modelo.categoria == "Acessórios" else f" Tamanho {size}."
    return (
        f"{modelo.descricao} Cor: {color.lower()}.{tamanho} "
        f"{NOTA_CONSERVACAO[condition]}"
    )


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
        estilo = _estilo_para(store, index // len(stores))
        modelo = rng.choice([m for m in MODELOS if m.estilo == estilo])
        brand = rng.choice(modelo.marcas)
        color = rng.choice(modelo.cores)
        size = rng.choice(SIZES[modelo.categoria])
        condition = rng.choices(
            CONDITIONS, weights=[PESO_CONSERVACAO[c] for c in CONDITIONS]
        )[0]

        product = Product(
            store=store,
            name=f"{modelo.nome} {brand}",
            description=_descricao(modelo, color, size, condition),
            category=modelo.categoria,
            style=modelo.estilo,
            brand=brand,
            color=color,
            size=size,
            condition=condition,
            composition=modelo.composicao,
            price=_preco(modelo, condition, rng),
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
