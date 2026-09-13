# Arquitetura

## Camadas observadas

- `app/views/`: routers e detalhes HTTP.
- `app/controllers/`: orquestração e regras de negócio.
- `app/repositories/`: persistência e queries SQLAlchemy.
- `app/schemas/`: contratos de entrada e saída Pydantic.
- `app/models/`: entidades e mapeamento SQLAlchemy.
- `app/database.py`: conexão e sessões.
- `app/config.py`: configuração por ambiente.
- `app/core/`: fundação transversal (envelope de erro, paginação) — ver ADR 0001.
- `app/main.py`: composição da aplicação (`create_app`) e middleware.

Fluxo esperado: `Route/View → Controller → Repository → Model/Database`, usando schemas na fronteira HTTP. Rotas não devem conter queries; repositories não devem decidir respostas HTTP; models não devem acumular orquestração de casos de uso.

Routers de domínio são agregados em `app/views/__init__.py` sob o prefixo `/api` e incluídos uma vez pelo `main.py`.

## Autenticação

JWT é a direção arquitetural informada para o Vintex. Porém, o clone atual não contém implementação JWT nem dependência correspondente. Não copie a antiga regra de autenticação mock e não declare autenticação pronta. Antes de implementar, confirme biblioteca, algoritmo, expiração, refresh/revogação, armazenamento de senha, papéis e política de autorização.

## Decisões registradas

- `.ai/adr/0001-fundacao-http-kit-api.md`: envelope de erro, prefixo `/api` (sem
  `/v1`), paginação, CORS por ambiente (`CORS_ORIGINS`) e fronteira de transação
  (commit no controller).

## Decisões pendentes

- contrato e estratégia completa de autenticação/autorização JWT;
- padrão de migrations e ciclo de ambientes;
- estratégia de testes com banco.
