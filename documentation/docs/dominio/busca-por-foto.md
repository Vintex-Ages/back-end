---
sidebar_position: 9
---

# Busca por foto

Fonte de verdade: `ProductController.search_by_image` (`app/controllers/product_controller.py`), `POST /api/products/search-by-image` (`app/views/product_routes.py`) e a issue [#255](https://github.com/Vintex-Ages/back-end/issues/255).

O front já tinha câmera na busca e o service `searchByImage`; faltava a rota. Ela recebe uma foto, encadeia o que já rodava em produção — **análise da imagem, texto dos atributos, embedding e busca por similaridade** — e devolve as peças como o catálogo devolve, com a distância. Nenhuma peça nova, nenhum modelo novo: é a mesma engrenagem do [chat](./conversa-com-a-vintex) e da [busca por semelhança](./busca-por-semelhanca).

## Contrato

```text
POST /api/products/search-by-image          multipart/form-data
```

Campos: `image` (o arquivo) mais os filtros do catálogo como campos de formulário — `category`, `price_min`, `price_max`, `size`, `brand`, `condition`, `color`, `city`, `state`, `page`. Sem `page_size`: a página é sempre de 20.

```json
// resposta 200
{
  "items": [{
    "id": 12,
    "name": "Jaqueta jeans",
    "price": 149.9,
    "cover_image_url": "https://.../foto.jpg",
    "status": "ativo",
    "store": { "id": 3, "name": "Brechó da Ana", "verified": true },
    "distance": 0.1843
  }],
  "interpreted": { "category": "Jaquetas", "color": "Azul", "brand": "" },
  "page": 1,
  "page_size": 20,
  "total": 34
}
```

- **O item é o do feed** (`ProductFeedItemResponse`), mais `distance`: 0 é idêntica e quanto maior, menos parecida. O front usa o mesmo mapeador da grade.
- **`interpreted` é o que a análise leu da foto** — o mesmo princípio dos chips do chat. Atributo que a IA não reconheceu sai `""`, e a marca só sai com etiqueta legível (RN-58).
- **`distance` pode ser nula** num único caso: o catálogo devolvido no lugar de lista vazia, quando não houve comparação vetorial (ver abaixo). Zero ali seria dizer "idêntica".
- **Público (RN-26):** funciona deslogado, como o catálogo. Com sessão, a cota conta pelo id; sem, pela origem da requisição.

Erros: `415` tipo não aceito (`IMAGE_INVALID_TYPE`) · `413` acima de 8 MiB (`IMAGE_TOO_LARGE`) · `429` cota diária esgotada (`QUOTA_EXCEEDED`) · `503` quando a análise ou o embedding falham (`AI_UNAVAILABLE`, mesma semântica da sugestão de anúncio).

Formatos aceitos: `image/jpeg`, `image/png`, `image/webp`, `image/heic` — os mesmos de `media_rules`, para a busca não aceitar o que a análise recusaria.

## A foto não é gravada

Ela é lida da requisição (no máximo 8 MiB + 1 byte, só para saber se passou do teto), mandada ao provedor como bytes e descartada. Não passa pelo armazenamento de mídia: não existe arquivo de busca que não é de ninguém, e o contrato declara que a foto não fica guardada.

Foi por isso que o provedor ganhou `analyze_image_bytes`: `analyze_image` só sabia baixar URL. Agora o caminho por URL baixa — continua igual para a sugestão de anúncio e o worker — e delega aos bytes, e os dois montam as **mesmas partes** para o modelo (`_partes_das_fotos`). Um provedor que não implemente os bytes responde `503` na busca, em vez de devolver análise vazia como se a foto não tivesse nada.

## O caminho, passo a passo

1. **Validação** do tipo e do tamanho, antes de gastar IA.
2. **Cota** (`ChatQuota`, a mesma do chat): são duas chamadas ao provedor por busca, no mesmo orçamento diário. Estourar responde `429` com a mensagem que diz quando volta.
3. **Análise** (`analyze_image_bytes`): categoria, cor, tamanho, conservação, descrição, marca e composição.
4. **Texto e vetor** (`texto_da_foto` + `embed`): só os atributos lidos, na ordem de `texto_da_peca`, porque é o mesmo espaço vetorial do catálogo. Preço, cidade e estilo não existem numa foto.
5. **Similaridade** (`find_similar`): os filtros do catálogo somam por E com a semelhança, e a distância volta em cada peça.

## Never empty, e o que isso significa

**Nunca devolve lista vazia enquanto houver catálogo** (RN-61):

- Sem filtro, `find_similar` não tem limiar: uma foto sem nada parecido devolve as peças mais próximas.
- Filtro que não casa **relaxa**, como no chat e no feed: primeiro só a categoria, depois o catálogo inteiro.
- Se nenhuma peça tem vetor do modelo ativo (catálogo sem backfill), ou a IA respondeu e não reconheceu nada na foto, a resposta é o catálogo paginado, com `distance` nula. Um vetor de texto vazio não significa nada, e inventá-lo seria ruído com cara de semelhança.

## A fatia declarada

**Acha peça com atributo parecido, não semelhança visual pura.** Foto de jaqueta de couro preta acha jaquetas de couro pretas; duas peças do mesmo corte em cores diferentes não se encontram. O embedding é de **texto** — o que a análise leu da foto —, o mesmo que descreve as peças do catálogo.

Fica fora, declarado: embedding de imagem de verdade, que poria foto e texto no mesmo espaço vetorial. Trocaria o modelo e exigiria recalcular o vetor de todo o catálogo.
