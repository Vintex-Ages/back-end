"""Schemas da loja.

Dois conjuntos, de issues diferentes que nasceram juntas:

- **loja publica** (`GET /api/stores/{id}`, back-end#142): o que qualquer um ve.
- **loja do vendedor** (`/api/users/me/store`, back-end#141): criacao e leitura
  da propria loja, com documento e termos.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
)

_DOCUMENT_DIGIT_LENGTH = {"CPF": 11, "CNPJ": 14}


class StoreAddressResponse(BaseModel):
    street: str
    number: str
    complement: str | None
    neighborhood: str | None
    city: str
    state: str
    zip_code: str


class StoreMetricsResponse(BaseModel):
    """Métricas que já existem hoje. O que não existir não entra aqui —
    o front mostra "em breve" pra qualquer coisa fora deste conjunto."""

    created_at: datetime
    products_listed: int
    products_sold: int


class StoreDetailResponse(BaseModel):
    id: int
    name: str
    description: str | None
    logo_url: str | None
    verified: bool
    address: StoreAddressResponse | None
    metrics: StoreMetricsResponse


class StoreProductItemResponse(BaseModel):
    id: int
    name: str
    price: Decimal
    cover_image_url: str | None
    status: str


class StoreAddressCreate(BaseModel):
    """Endereco da loja no cadastro (back-end#216).

    Espelha o `StoreAddressResponse` de proposito: o que entra e o que sai tem
    o mesmo nome de campo. `zip_code` e `neighborhood`, e nao `cep`/`district`,
    porque e assim que a resposta publica ja devolve e assim que a modelagem
    (`vintex-modelagem-1.md` secao 1.3) nomeia as colunas.
    """

    street: str = Field(min_length=1, max_length=150)
    number: str = Field(min_length=1, max_length=20)
    complement: str | None = Field(default=None, max_length=100)
    neighborhood: str | None = Field(default=None, max_length=100)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=2, max_length=2)
    zip_code: str = Field(min_length=1, max_length=10)


class StoreCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # Opcionais porque a modelagem decide assim: na secao 1.4 de
    # `vintex-modelagem-1.md`, com a legenda "NN = not null (obrigatorio)", so
    # `seller_id` e `name` tem NN. `description`, `logo_url`, `pix_key` e
    # `address_id` nao tem -- e o model implementa assim
    # (`Mapped[str | None]`), e o `StoreResponse` devolve assim.
    #
    # A `description` exigia `min_length=1` desde a #141, contra as tres
    # fontes acima e contra a propria tela, que rotula "Descricao (opcional)".
    description: str | None = None
    logo_url: AnyHttpUrl | None = None
    # RN-18, Firme: "No cadastro do vendedor, registra-se sua chave Pix para
    # recebimento." A coluna existe desde a migration base; o cadastro nunca a
    # aceitou, e o formulario do `front-end#212` pede o campo e perdia o valor.
    pix_key: str | None = Field(default=None, max_length=255)
    # `VS-006` em Gherkin: "informo CPF ou CNPJ, endereco e chave Pix".
    address: StoreAddressCreate | None = None
    document_type: Literal["CPF", "CNPJ"]
    document_value: str = Field(min_length=1, max_length=18)
    # Opcional ate a tela de aceite do contrato existir (`front-end#215`,
    # Should, sem PR). Exigir aqui fazia um Should nao construido bloquear o
    # `front-end#212`, que e Must e esta pronto -- e o front nao tem de onde
    # tirar a versao: `legal_documents` nasce vazia e `GET /api/legal/terms`
    # devolve 404 sem rodar o seed. Gravar versao chumbada seria registrar um
    # aceite que ninguem deu. NULL e a verdade.
    terms_version: str | None = Field(default=None, max_length=20)

    @field_validator("document_value")
    @classmethod
    def normalizar_documento(cls, valor: str, info: ValidationInfo) -> str:
        """Confere a quantidade de dígitos e **devolve só os dígitos**.

        Duas coisas que estavam erradas (back-end#220, migradas para cá porque
        mexem nesta mesma função):

        1. A regra era um `model_validator(mode="after")`, que não tem campo
           associado, então o erro saía como `fields: {"body": ...}`. O
           ADR 0001 §2 fixa `fields` como campo → motivo, e com `"body"` o
           front não consegue destacar o input. Como `field_validator` de
           `document_value` o erro cai no campo certo — e funciona porque
           `document_type` é declarado antes e já está em `info.data`.
        2. O valor era gravado cru, então `52998224725` e `529.982.247-25`
           criavam dois vendedores com o mesmo CPF: o índice único de
           `Seller.document_value` e o pre-check do controller comparam string
           literal. A normalização já era feita para contar os dígitos, e era
           descartada em vez de gravada.
        """
        tipo = info.data.get("document_type")
        digitos = "".join(c for c in valor if c.isdigit())
        if tipo is None:
            # `document_type` já falhou a validação; não há o que conferir aqui.
            return digitos
        esperado = _DOCUMENT_DIGIT_LENGTH[tipo]
        if len(digitos) != esperado:
            raise ValueError(
                f"{tipo} deve ter {esperado} dígitos (recebeu {len(digitos)})."
            )
        return digitos


class StoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seller_id: int
    name: str
    description: str | None
    logo_url: str | None
    # A loja precisa conseguir ler a propria chave, senao o vendedor nao tem
    # como conferir onde vai cair o dinheiro. Nao entra no retrato publico
    # (`StoreDetailResponse`): e dado do vendedor, nao da vitrine.
    pix_key: str | None
    document_type: str
    document_value: str
    terms_version: str | None
    terms_accepted_at: datetime | None
    address: StoreAddressResponse | None
