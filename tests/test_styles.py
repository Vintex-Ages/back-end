"""Contrato do catálogo de estilos do onboarding (task #79)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

EXPECTED_STYLES: list[dict[str, str]] = [
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


def test_styles_retorna_catalogo_completo() -> None:
    resp = client.get("/api/styles", follow_redirects=False)

    assert resp.status_code == 200
    body = resp.json()
    assert "styles" in body
    assert len(body["styles"]) == 6
    for style in body["styles"]:
        assert set(style) == {"type", "value", "label", "description"}
    assert body["styles"] == EXPECTED_STYLES


def test_styles_presente_no_openapi() -> None:
    resp = client.get("/openapi.json")

    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert "/api/styles" in paths
    assert "get" in paths["/api/styles"]
