---
sidebar_position: 7
---

# Sugestão de preço

Fonte de verdade: `PriceSuggestionController` (`app/controllers/price_suggestion_controller.py`), `app/services/price_suggestion.py` e a issue [#254](https://github.com/Vintex-Ages/back-end/issues/254).

`POST /api/ai/price-suggestions` devolve uma faixa de preço para a peça que o vendedor está cadastrando. Exige login (RN-27). A sugestão alerta e nunca impede o preço escolhido (RN-68): quem compara o preço digitado com a faixa é o front.

## Contrato

```json
// requisição: `name` é o único obrigatório; os outros refinam a semelhança
{ "name": "Tênis Nike", "category": "Sapatos", "brand": "", "condition": "Seminovo", "size": "", "description": "" }

// resposta 200
{ "min": 121.03, "max": 332.68, "justification": "Peças parecidas no catálogo (Sapatos) costumam custar entre R$ 121,03 e R$ 332,68. Com base em 10 peças.", "based_on": 10 }
```

- **Campo vazio (`""`) vale ausente.** O formulário manda assim o que ainda não foi preenchido.
- **`min` e `max` são número no JSON**, nunca string (`#212`).
- **`based_on`** é quantas peças sustentam a faixa: o vendedor julga a comparação em vez de confiar no número.
- **Sem base suficiente não é erro:** `200` com `min` e `max` nulos, `based_on: 0` e a justificativa dizendo que ainda não há peças parecidas. Não inventa número.
- Erros: `401` sem token, `422` sem `name`.

## De onde a faixa vem

**Do próprio catálogo**, sem consulta externa e **sem chamar o provedor de IA**. É o que o card decide: a fonte é o banco, por custo, por termo de uso e porque não há fonte externa de peça usada brasileira.

A comparação é por similaridade vetorial, com os vetores que as peças **já têm gravados** ([Busca por semelhança](./busca-por-semelhanca)). A peça que está sendo cadastrada ainda não tem vetor, e gerar um seria uma chamada ao provedor. Então:

1. **Referência pelo nome.** As peças ativas cujo nome mais casa com o nome digitado, sem acento e sem caixa, como a busca textual (RN-41). Vence quem tem mais palavras em comum: com "Tênis Nike azul", um "Tênis Nike Azul" é referência, e um "Tênis Branco" só se nenhum nome tiver mais palavras. Com categoria informada, só peças dela. **A descrição desempata**: "Jaqueta" com descrição "jeans azul" prefere a "Jaqueta jeans" à "Jaqueta de couro". Peça que só casa pela descrição não vira referência.
2. **A posição da peça nova** é a média dos vetores das referências.
3. **As comparáveis** são as até 10 peças ativas mais próximas dessa posição. Categoria, conservação, marca e tamanho refinam, do mais específico ao mais largo, enquanto sobrar base:

   | Passo | Filtros |
   |---|---|
   | 1 | categoria, conservação, marca, tamanho |
   | 2 | categoria, conservação, marca |
   | 3 | categoria, conservação |
   | 4 | categoria |

   A categoria nunca sai: o preço de um sapato não diz nada sobre o de um acessório. A justificativa diz com quais filtros a faixa saiu.
4. **A faixa** vai do 1º ao 3º quartil dos preços das comparáveis: a metade do meio. Os extremos ficam de fora para uma peça de grife no meio de camisetas não esticar a faixa até ela não dizer nada.

**Sem referência** (nenhum nome em comum) ou **com menos comparáveis que o mínimo** (`PRICE_SUGGESTION_MIN_BASE`, padrão 3), a faixa vem nula.

**Nada é gravado.** A rota só lê, e um teste confere que todo comando que ela manda ao banco é `SELECT`.

## Limites

- **Depende de o catálogo ter vetores.** Peça sem vetor, ou de outro modelo de embedding, não entra nem como referência nem como comparável.
- **O nome manda.** Sem nenhuma palavra do nome em comum com o catálogo, não há referência, mesmo que a descrição case: a faixa vem nula.
- **Sem categoria, a comparação é com o catálogo todo.** O formulário costuma mandar a categoria; sem ela, as comparáveis podem misturar roupa, sapato e acessório.
- **O seed tem preço aleatório.** Com o catálogo de demonstração, as faixas saem largas; com preços reais, elas acompanham o mercado do próprio Vintex.

## Testar localmente

`tests/test_price_suggestion.py` roda com `TEST_POSTGRES_URL`, porque compara vetores. No Swagger (`/docs`), autentique, chame `POST /api/ai/price-suggestions` com `{"name": "Tênis Nike", "category": "Sapatos"}` sobre o catálogo do seed (depois do backfill) e compare `based_on` com as peças do catálogo.
