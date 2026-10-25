---
sidebar_position: 1
---

# Validação do comprovante

Fonte de verdade: `app/controllers/payment_review_controller.py`, a troca condicional de status em `app/repositories/order_repository.py` e as issues [#251](https://github.com/Vintex-Ages/back-end/issues/251) (aprovar e rejeitar) e [#243](https://github.com/Vintex-Ages/back-end/issues/243) (tabelas do pedido).

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
| `aguardando_comprovante → em_analise` | comprador, `POST /api/users/me/orders/{order_id}/receipt` ([#249](https://github.com/Vintex-Ages/back-end/issues/249)) | um pagamento novo, `pendente`, com nome e tipo do arquivo |
| `em_analise → confirmado` | administradora, `POST /api/admin/payments/{order_id}/approve` | pagamento `aprovado` com quem e quando; peças `reservado → vendido` com `sold_at` |
| `em_analise → aguardando_comprovante` | administradora, `POST /api/admin/payments/{order_id}/reject` | pagamento `rejeitado` com o motivo; **prazo renovado em 3 dias**; peças continuam reservadas |
| `aguardando_comprovante → expirado` | rotina de expiração ([#280](https://github.com/Vintex-Ages/back-end/issues/280)) | peças voltam a `ativo` |

Depois de `confirmado`, as etapas `preparando`, `enviado` e `concluido` não viram linha no banco: são derivadas na leitura a partir da data de aprovação (RN-81 e RN-83 simulam postagem e entrega). Ver [Pedidos do comprador](./pedidos-do-comprador#linha-do-tempo).

## Decisões

- **Aprovar é o que confirma a venda**, e não o checkout. A peça só passa a `vendido`, e a contar no resumo do vendedor (RN-95), na aprovação.
- **Rejeitar não cria estado novo.** O pedido volta para `aguardando_comprovante` e o comprador reenvia pela mesma rota de envio (RN-23). O motivo é obrigatório, porque vai para o comprador.
- **Rejeitar renova o prazo.** Sem isso, um comprovante enviado no fim do prazo e rejeitado depois dele voltaria vencido, e a expiração levaria o pedido antes do reenvio.
- **Reenviar não apaga o comprovante anterior.** Cada envio é uma linha em `payments`; o vigente é o mais recente (RN-22).
- **Duas validações do mesmo comprovante: só a primeira passa.** A troca de status é um `UPDATE … WHERE status = 'em_analise'`, como na reserva das peças. A segunda responde `409 ORDER_NOT_IN_REVIEW`.
- **Pedido, pagamento, histórico e peças mudam no mesmo commit.**

## O envio pelo comprador

`POST /api/users/me/orders/{order_id}/receipt`, multipart com o campo `file`. Serve para o primeiro envio e para o reenvio depois de uma rejeição: rejeitar devolve o pedido para `aguardando_comprovante`, e o estado permite enviar de novo.

- **Só sai de `aguardando_comprovante`.** Pedido já em análise responde `409 ORDER_NOT_AWAITING_RECEIPT`: não dá para empilhar comprovante. A troca é condicional, como as outras; dois envios ao mesmo tempo, só o primeiro passa.
- **O pedido é conferido antes do arquivo, e o arquivo antes do upload.** Tipo fora da lista responde `415 RECEIPT_INVALID_TYPE`, acima de 8 MiB responde `413 RECEIPT_TOO_LARGE`, e nos dois casos nada muda e nada sobe. A rota genérica de mídia continua respondendo 422 para os mesmos casos; aqui o contrato é o do front.
- **Pedido vencido não recebe comprovante.** Não há rotina periódica de expiração, então o próprio envio é o gatilho: pedido em `aguardando_comprovante` com o prazo passado é expirado na hora (as peças voltam a `ativo`) e responde 409.
- **Se a gravação falhar depois do upload, o arquivo é apagado**, para não ficar objeto órfão no bucket.
- A resposta é parcial: `payment` e só a etapa que o envio criou em `history`. O detalhe do pedido tem o resto.

## O arquivo do comprovante

- **Imagem ou PDF** (RN-20): `image/jpeg`, `image/png`, `image/webp`, `image/heic` e `application/pdf`, até **8 MiB** (`app/services/media_rules.py`). PDF vale só para comprovante; foto de peça continua só imagem ([#244](https://github.com/Vintex-Ages/back-end/issues/244)).
- **Só a administradora abre o arquivo**, por `GET /api/admin/payments/{order_id}/receipt`, que devolve o comprovante vigente com o tipo original. Comprovante de Pix tem dado bancário: o comprador, inclusive o dono do pedido, recebe 403. Ele vê o nome e a situação no detalhe do pedido, nunca a URL.
- A resposta sai com `Cache-Control: private, no-store` e `X-Content-Type-Options: nosniff`.
- `payments.receipt_name` e `payments.receipt_content_type` são gravados no envio. A chave do storage é um uuid sem extensão: sem essas colunas o nome seria irrecuperável, e o tipo só sairia baixando o arquivo, um download por linha na fila da administradora.
- O prefixo `payments/receipts/` fica fora da rota pública de mídia (`/api/media/...`).

## Erros

| Status | Código | Quando |
| --- | --- | --- |
| 401 | `AUTH_REQUIRED` | sem sessão |
| 403 | `ADMIN_REQUIRED` | quem não é administradora (ver [Fundação HTTP](../arquitetura/fundacao-http#autorização-por-papel)) |
| 404 | `ORDER_NOT_FOUND` | pedido inexistente |
| 404 | `RECEIPT_NOT_FOUND` | pedido sem comprovante, na rota do arquivo |
| 409 | `ORDER_NOT_IN_REVIEW` | o pedido não está em `em_analise`, inclusive na segunda validação |
| 409 | `ORDER_NOT_AWAITING_RECEIPT` | envio com o pedido fora de `aguardando_comprovante`, ou vencido |
| 413 | `RECEIPT_TOO_LARGE` | comprovante acima de 8 MiB |
| 415 | `RECEIPT_INVALID_TYPE` | comprovante que não é imagem nem PDF |
| 422 | `VALIDATION_ERROR` | rejeitar com motivo vazio |
