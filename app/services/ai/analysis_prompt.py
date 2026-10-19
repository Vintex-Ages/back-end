"""Prompt comum para análise de fotos de peças."""

from app.constants.catalog import CATEGORIES, COLORS, CONDITIONS, SIZES, lista

ANALYZE_IMAGE_PROMPT = f"""\
Você está ajudando um vendedor de brechó a cadastrar uma peça de roupa a \
partir das fotos dela. Analise as imagens e sugira, em português:

- category: escolha UM valor exato desta lista: {lista(CATEGORIES)}. \
É a família da peça no catálogo, não o tipo dela: uma camiseta é "Roupas", \
um tênis é "Sapatos", uma bolsa é "Acessórios".
- color: escolha UM valor exato desta lista: {lista(COLORS)}. \
Se a peça tiver mais de uma cor, escolha a predominante; use "Estampado" \
quando não houver uma cor dominante.
- size: escolha UM valor exato desta lista: {lista(SIZES)}, e só se o \
tamanho estiver legível numa etiqueta na foto. Não estime pelo caimento.
- condition: escolha UM valor exato desta lista: {lista(CONDITIONS)}.
- description: uma frase curta descrevendo a peça. Texto livre.
- brand: a marca, APENAS se houver uma etiqueta ou logo legível na foto — \
se não houver etiqueta visível ou não for possível ler com certeza, não \
preencha este campo. Nunca chute a marca a partir do estilo da peça.

Nos quatro campos de lista, responda com o valor exato como está escrito \
acima, com acento e maiúscula. Se nenhum valor da lista servir, deixe o \
campo nulo — é melhor vazio que aproximado, porque o vendedor corrige um \
campo vazio mas não percebe um valor errado.

Para cada campo que conseguir sugerir, dê um `value` e uma `confidence` \
(0 a 1) de quão certo você está. Deixe o campo nulo se não conseguir \
sugerir algo com razoável confiança — melhor um campo vazio que um chute.
"""
