"""Dimensão do embedding do catálogo (BE-US027-1, back-end#92).

Fonte única: `Product.embedding`, a migration que cria a coluna e
`GoogleAIProvider` importam daqui — trocar de modelo/dimensão é mudar em um
lugar só, não três. `768` foi decisão do time em 21/09 (ver comentário da
issue #92): valor recomendado do `gemini-embedding-2` para um catálogo deste
tamanho, não corte arbitrário.
"""

from typing import Final

EMBEDDING_DIM: Final[int] = 768
