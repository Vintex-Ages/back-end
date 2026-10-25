---
sidebar_position: 1
---

# Validação do comprovante

Fonte de verdade: `app/controllers/payment_review_controller.py` e as issues [#251](https://github.com/Vintex-Ages/back-end/issues/251) (aprovar e rejeitar) e [#243](https://github.com/Vintex-Ages/back-end/issues/243) (tabelas do pedido).

A plataforma não processa o Pix (RN-13 e RN-14). O comprador paga por fora, direto na chave do vendedor, e anexa o comprovante. Quem confere o arquivo é a administradora, à mão (RN-21).

## Estados do pedido

```
aguardando_comprovante ──envio (#249)──▶ em_analise ──aprovar──▶ confirmado
          ▲                                  │
          └────────────rejeitar──────────────┘
aguardando_comprovante ──prazo vencido (#280)──▶ expirado
```

| Transição | Quem | O que muda além do status |
| --- | --- | --- |
| `aguardando_comprovante → em_analise` | comprador, ao anexar o comprovante ([#249](https://github.com/Vintex-Ages/back-end/issues/249)) | um pagamento novo, `pendente` |
| `em_analise → confirmado` | administradora, `POST /api/admin/payments/{order_id}/approve` | pagamento `aprovado` com quem e quando; peças `reservado → vendido` com `sold_at` |
| `em_analise → aguardando_comprovante` | administradora, `POST /api/admin/payments/{order_id}/reject` | pagamento `rejeitado` com o motivo; **prazo renovado em 3 dias**; peças continuam reservadas |
| `aguardando_comprovante → expirado` | rotina de expiração ([#280](https://github.com/Vintex-Ages/back-end/issues/280)) | peças voltam a `ativo` |

Depois de `confirmado`, as etapas `preparando`, `enviado` e `concluido` não viram linha no banco: são derivadas na leitura a partir da data de aprovação (RN-81 e RN-83 simulam postagem e entrega).

## Decisões

- **Aprovar é o que confirma a venda**, e não o checkout. A peça só passa a `vendido`, e a contar no resumo do vendedor (RN-95), na aprovação.
- **Rejeitar não cria estado novo.** O pedido volta para `aguardando_comprovante` e o comprador reenvia pela mesma rota de envio (RN-23). O motivo é obrigatório, porque vai para o comprador.
- **Rejeitar renova o prazo.** Sem isso, um comprovante enviado no fim do prazo e rejeitado depois dele voltaria vencido, e a expiração levaria o pedido antes do reenvio.
- **Reenviar não apaga o comprovante anterior.** Cada envio é uma linha em `payments`; o vigente é o mais recente (RN-22).
- **Duas validações do mesmo comprovante: só a primeira passa.** A troca de status é um `UPDATE … WHERE status = 'em_analise'`, como na reserva das peças. A segunda responde `409 ORDER_NOT_IN_REVIEW`.
- **Pedido, pagamento, histórico e peças mudam no mesmo commit.**

## Erros

| Status | Código | Quando |
| --- | --- | --- |
| 401 | `AUTH_REQUIRED` | sem sessão |
| 403 | `ADMIN_REQUIRED` | quem não é administradora (ver [Fundação HTTP](../arquitetura/fundacao-http#autorização-por-papel)) |
| 404 | `ORDER_NOT_FOUND` | pedido inexistente |
| 409 | `ORDER_NOT_IN_REVIEW` | o pedido não está em `em_analise`, inclusive na segunda validação |
| 422 | `VALIDATION_ERROR` | rejeitar com motivo vazio |
