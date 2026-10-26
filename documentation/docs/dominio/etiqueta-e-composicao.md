---
sidebar_position: 7
---

# Etiqueta e composição

Fonte de verdade: `app/services/ai/analysis_prompt.py` (o que a IA lê), `app/services/media_rules.py` (o tipo `label`) e `app/controllers/product_controller.py` (a galeria), da BE-US015-1 ([#257](https://github.com/Vintex-Ages/back-end/issues/257)), que entrega o back da VS-015.

O vendedor pode mandar, além das fotos da peça, uma foto só da etiqueta. Dela a IA lê marca, tamanho e **composição do tecido**, e a peça ganha o campo `composition`.

## O caminho da foto da etiqueta

1. Sobe por `POST /api/users/me/media` com `kind=label`, e fica em `products/labels/`. Aceita os mesmos formatos da foto da peça, porque vai para a mesma análise.
2. Vai em `POST /api/ai/listing-suggestions` como `label_image_url`, à parte de `image_urls`. Ela não conta no limite de oito fotos.
3. A análise é uma só: a etiqueta entra depois das fotos da peça, na mesma chamada ao provedor. O prompt diz que da etiqueta saem `brand`, `size` e `composition`, e que categoria, cor, conservação e descrição saem das fotos da peça, nunca da etiqueta.

A URL da etiqueta é pública porque é pela rota pública que o servidor baixa a foto para a IA, e uma etiqueta de roupa não tem nada de sigiloso. Ficar **fora da galeria** é outra regra:

- **A peça recusa a URL da etiqueta em `images`**, ao criar e ao editar, com `422` em `fields.images`. É o que a impede de aparecer na vitrine como foto do produto.
- Por consequência, a etiqueta **não conta como a foto que publicar exige** (RN-47). Peça só com etiqueta continua sem poder publicar.

## A composição nunca é chutada

É o mesmo cuidado que o prompt já tinha com a marca (RN-58): a composição só é preenchida a partir de texto legível na etiqueta. Peça sem etiqueta legível volta com `composition: null`, e o vendedor escreve se quiser (RN-56). Campo vazio o vendedor corrige; campo errado ele não percebe.

## O campo na peça

| Onde | Como |
| --- | --- |
| `products.composition` | texto livre, até 200 caracteres, opcional |
| `POST` e `PATCH /api/users/me/products` | aceitam `composition`; no `PATCH`, campo ausente não muda nada |
| rascunho, detalhe do vendedor e edição | `composition`, nulo quando não há |
| detalhe público (`GET /api/products/{id}`) | `composition`, `""` quando não há, como os outros atributos |
| texto que vira vetor | entra no fim, só quando existe (ver [Busca por semelhança](./busca-por-semelhanca)) |

A análise em segundo plano da peça (`ai-status`) também devolve `composition` quando a IA a lê, porque usa o mesmo resultado da análise. A foto da etiqueta, porém, só chega à IA pela sugestão síncrona: ela não fica ligada à peça.
