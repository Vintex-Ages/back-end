"""Painel geral da administradora (back-end#269).

Só leitura: junta as contagens e as vendas por loja e devolve o contrato da
tela. A guarda de papel fica no router (`app/views/admin_routes.py`), como nas
demais rotas de administração (RN-32).
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.repositories.dashboard_repository import DashboardRepository
from app.schemas.admin_dashboard_schema import AdminDashboardResponse, StoreSalesEntry


class AdminDashboardController:
    """Os números gerais da plataforma para a administradora (back-end#269)."""

    def __init__(self, db: Session):
        self.dashboard = DashboardRepository(db)

    def summary(self) -> AdminDashboardResponse:
        """Uma resposta com os seis números e a lista por loja.

        Volume e comissão são somados da lista que já veio agrupada: uma
        consulta a menos, e os totais nunca discordam das linhas do ranking.
        """
        lojas, usuarios, pecas = self.dashboard.counts()
        por_loja = self.dashboard.sales_by_store()
        return AdminDashboardResponse(
            stores_count=lojas,
            users_count=usuarios,
            active_products_count=pecas,
            sales_volume=sum((amount for _, _, amount, _ in por_loja), Decimal("0")),
            commission_total=sum((fee for _, _, _, fee in por_loja), Decimal("0")),
            sales_by_store=[
                StoreSalesEntry(store_id=store_id, store_name=name, amount=amount)
                for store_id, name, amount, _ in por_loja
            ],
        )
