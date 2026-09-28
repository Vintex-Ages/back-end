"""Estilos disponíveis para o onboarding, versionados junto ao código."""

from typing import Final

STYLES: Final[list[dict[str, str]]] = [
    {
        "type": "estilo",
        "value": "vintage-80-90",
        "label": "Vintage 80s / 90s",
        "description": "Jaquetas de couro, jeans pesados e peças históricas",
    },
    {
        "type": "estilo",
        "value": "streetwear",
        "label": "Streetwear Urbano",
        "description": "Oversized, moletons gráficos e sneakers raros",
    },
    {
        "type": "estilo",
        "value": "alfaiataria",
        "label": "Alfaiataria & Elegância",
        "description": "Blazers estruturados, camisas de seda e cortes clássicos",
    },
    {
        "type": "estilo",
        "value": "gotico-dark",
        "label": "Gótico & Dark Aesthetic",
        "description": "Tons escuros, coturnos tratorados, rendas e couro",
    },
    {
        "type": "estilo",
        "value": "boho-romantico",
        "label": "Boho Chic & Romântico",
        "description": "Vestidos fluidos, estampas florais e tecidos naturais",
    },
    {
        "type": "estilo",
        "value": "y2k",
        "label": "Y2K Anos 2000",
        "description": "Cintura baixa, bolsas baguete e óculos retrô",
    },
]
