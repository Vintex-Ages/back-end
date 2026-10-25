---
sidebar_position: 2
---

# Pedidos do comprador

Fonte de verdade: `app/controllers/order_controller.py` e as issues [#247](https://github.com/Vintex-Ages/back-end/issues/247) (criar o pedido) e [#248](https://github.com/Vintex-Ages/back-end/issues/248) (listar e detalhar).

Um pedido é a compra das peças de **uma loja só**: o comprador paga direto na chave Pix do vendedor (RN-19 e RN-20), então finalizar um carrinho com N lojas gera N pedidos. Todas as rotas exigem login (RN-27) e só enxergam os pedidos de quem pede.

| Rota | O que faz |
| --- | --- |
| `POST /api/users/me/orders` | cria o pedido e reserva as peças |
| `GET /api/users/me/orders` | "Meus pedidos", paginado, mais recente primeiro |
| `GET /api/users/me/orders/{order_id}` | detalhe, com a chave Pix e a linha do tempo |

## Lista e detalhe

- **A lista não traz `pix_key` nem `history`.** Só o detalhe traz; ele é a única rota que devolve a chave Pix ao comprador.
- **A lista traz o endereço de entrega de cada pedido.** O endereço do comprador só existe dentro do pedido (nenhuma rota preenche `users.address_id`), e é da lista que o checkout pré-preenche a próxima compra.
- **Pedido de outra pessoa responde 404**, igual a inexistente: um 403 confirmaria que o id existe.
- **O comprovante aparece com nome e situação, nunca com URL.** Comprovante de Pix tem dado bancário, e quem abre o arquivo é só a administradora. O `receipt_name` fica nulo até a [#244](https://github.com/Vintex-Ages/back-end/issues/244) gravar o nome original no envio.
- O comprovante mostrado é o envio mais recente; reenviar não apaga o anterior (RN-22). Pedido rejeitado traz o motivo (RN-23).
- Valores saem como **número**, nunca string (#212).
- A página inteira da lista são cinco consultas, qualquer que seja o tamanho: pedidos, contagem, e uma por coleção (itens, pagamentos, histórico).

## Linha do tempo

Os estados até `confirmado` são gravados em `order_status_history`, uma linha por transição (ver [Validação do comprovante](./validacao-de-comprovante)).

Depois de `confirmado`, **as etapas seguintes são derivadas na leitura**. Não há transportadora (RN-81 e RN-83), então nenhuma rotina grava essas linhas:

| Etapa | Atingida em |
| --- | --- |
| `preparando` | aprovação + 1 dia |
| `enviado` | aprovação + 2 dias |
| `concluido` | aprovação + 3 dias |

O `status` da lista e do detalhe é a última etapa já atingida, e o `history` do detalhe inclui as derivadas com a data. Os intervalos ficam em `_ETAPAS_SIMULADAS`, no `order_controller`. Um dia entre etapas é o mesmo ritmo do mock do front; o texto da RN-81 e da RN-83 não fixa o intervalo, e trocá-lo é mudar só essa tupla.
