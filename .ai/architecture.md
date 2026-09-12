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

JWT via `PyJWT` (HS256), hash de senha com bcrypt e as dependencies de
autorização (`get_current_user`, `require_auth`, `require_seller`,
`require_admin`, `optional_user`) vivem em `app/core/security.py`. Papéis não
são uma coluna: comprador é todo usuário, vendedor é derivado de existir linha
em `sellers`, admin é `users.is_admin`. Ver `.ai/adr/0002-autenticacao-jwt.md`
para o contrato completo (algoritmo, expiração, estratégia de sessão/logout via
refresh token).

## Decisões registradas

- `.ai/adr/0001-fundacao-http-kit-api.md`: envelope de erro, prefixo `/api` (sem
  `/v1`), paginação, CORS por ambiente (`CORS_ORIGINS`) e fronteira de transação
  (commit no controller).
- `.ai/adr/0002-autenticacao-jwt.md`: biblioteca, algoritmo, expiração,
  estratégia de sessão persistente/logout (refresh token), hash de senha,
  claim de papel e localização do código de autenticação.

## Decisões pendentes

- padrão de migrations e ciclo de ambientes;
- estratégia de testes com banco.
