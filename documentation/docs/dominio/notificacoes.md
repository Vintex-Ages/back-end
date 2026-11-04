---
sidebar_position: 10
---

# Notificações

Fonte de verdade: `app/controllers/notification_controller.py`, `app/repositories/notification_repository.py`, `app/models/notification.py` e a issue [#261](https://github.com/Vintex-Ages/back-end/issues/261).

Aviso dentro do produto, e só dentro dele (RN-84): nada é enviado por e-mail nem por push. São dois eventos, os da RN-85, e nenhum outro:

| Evento | Quem recebe | Quando nasce |
| --- | --- | --- |
| `sale` | o vendedor da loja do pedido | quando a administradora **aprova** o comprovante ([Validação do comprovante](./validacao-de-comprovante)), e não no checkout: é a aprovação que confirma a venda (RN-21) |
| `favorite` | o vendedor dono da peça | quando alguém favorita a peça ([Favoritos](./favoritos)) |

O aviso é gravado no mesmo commit do evento: não existe venda aprovada sem aviso, nem aviso de favorito recusado.

## Rotas

Todas exigem login (RN-27) e só enxergam os avisos de quem pede.

| Rota | O que faz | Resposta |
| --- | --- | --- |
| `GET /api/users/me/notifications` | lista paginada, mais recente primeiro | `200` com `{ items, page, page_size, total, unread_count }` |
| `POST /api/users/me/notifications/{id}/read` | marca um como lido | `204` sem corpo · `404 NOTIFICATION_NOT_FOUND` |
| `POST /api/users/me/notifications/read` | marca todos como lidos | `204` sem corpo |

Sem token, as três respondem `401 AUTH_REQUIRED`.

```json
{
  "items": [
    {
      "id": 12,
      "type": "sale",
      "product_id": 7,
      "product_name": "Jaqueta jeans",
      "order_id": 31,
      "created_at": "2026-10-28T14:03:11",
      "is_read": false
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1,
  "unread_count": 1
}
```

## As decisões

- **Um aviso de venda por pedido**, com a primeira peça dele em `product_id`. O pedido é de uma loja só, então tem um vendedor só.
- **Favoritar avisa uma vez por pessoa e por peça.** O índice único parcial `uq_notifications_favorite` (`product_id`, `actor_id`, só onde `type = 'favorite'`) e o `INSERT ... ON CONFLICT DO NOTHING` fazem favoritar, desfavoritar e favoritar de novo não avisar outra vez. Desfavoritar não avisa nem apaga o aviso.
- **Quem favoritou não sai na resposta.** `actor_id` existe só para o índice: o anunciante sabe que alguém favoritou, não quem.
- **O vendedor que favorita a própria peça não é avisado.**
- **`unread_count` conta todas as páginas**, para o badge não depender da página aberta.
- **Marcar é idempotente.** Marcar de novo responde `204` e mantém a data da primeira leitura (`read_at`). Aviso de outra pessoa responde `404`, igual a inexistente: um `403` confirmaria o id.
- **A coluna `type` é texto, com CHECK.** A despublicação pela administradora (RN-80, VS-034) é um terceiro tipo, que entra no `NotificationType` e no CHECK quando chegar.
