"""Agregações do painel geral da administradora (back-end#269).

Todos os números saem de tabela que já existe — nenhuma tabela nova (a
história diz isso explicitamente). O resumo por vendedor do painel do vendedor
(`ProductRepository.sales_summary`) é a referência de ideia, mas aqui a leitura
é do **pedido**, não da peça: é o histórico de pagamento que manda (RN-22).

Duas idas ao banco, qualquer que seja o tamanho da plataforma: uma traz as três
contagens em subconsultas escalares, a outra agrupa os pedidos confirmados por
loja. O volume e a comissão acumulados saem da própria lista agrupada, sem uma
terceira consulta.
"""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.product import Product
from app.models.store import Store
from app.models.user import User


def _dinheiro(valor: object) -> Decimal:
    """Soma do banco como `Decimal`, inclusive quando o dialeto devolve outro tipo."""
    if valor is None:
        return Decimal("0")
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


class DashboardRepository:
    """Contagens e vendas confirmadas por loja (back-end#269)."""

    def __init__(self, db: Session):
        self.db = db

    def counts(self) -> tuple[int, int, int]:
        """Lojas, usuários e peças ativas — as três em uma consulta.

        `ativo` é o único estado que conta como peça à venda: `rascunho` ainda
        não foi publicada e `reservado`/`vendido`/`despublicado` não estão na
        vitrine.
        """
        stmt = select(
            select(func.count(Store.id)).scalar_subquery(),
            select(func.count(User.id)).scalar_subquery(),
            select(func.count(Product.id))
            .where(Product.status == "ativo")
            .scalar_subquery(),
        )
        lojas, usuarios, pecas = self.db.execute(stmt).one()
        return int(lojas or 0), int(usuarios or 0), int(pecas or 0)

    def sales_by_store(self) -> list[tuple[int, str, Decimal, Decimal]]:
        """Vendas confirmadas por loja: id, nome, valor e comissão.

        `confirmado` é o estado gravado na aprovação do comprovante (RN-21).
        `preparando`, `enviado` e `concluido` são derivados na leitura a partir
        da data de aprovação, então não existem como linha: filtrar por
        `confirmado` já inclui todo pedido pago, em qualquer etapa posterior.

        A ordem é a do ranking da tela — de quem mais vendeu para quem menos
        vendeu, com o nome desempatando. Loja sem venda confirmada não entra:
        a lista é de quem vendeu.
        """
        stmt = (
            select(
                Store.id,
                Store.name,
                func.sum(Order.total_amount),
                func.sum(Order.platform_fee),
            )
            .join(Order, Order.store_id == Store.id)
            .where(Order.status == "confirmado")
            .group_by(Store.id, Store.name)
            .order_by(func.sum(Order.total_amount).desc(), Store.name.asc())
        )
        return [
            (int(store_id), str(name), _dinheiro(amount), _dinheiro(fee))
            for store_id, name, amount, fee in self.db.execute(stmt).all()
        ]
