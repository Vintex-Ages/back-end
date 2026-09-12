# ADR 0002 — Autenticação JWT e autorização por papel

- **Status:** aceito
- **Data:** 2026-09-12
- **Issue:** Vintex-Ages/back-end#72 (`BE-FND-3`)
- **Contexto:** `.ai/architecture.md` listava "contrato e estratégia completa de
  autenticação/autorização JWT" como decisão pendente. O Épico A (Acesso e
  identidade — issues #22, #24, #67) depende dela para as issues #76, #77, #78,
  #80, #81, #82, #83 e #84. Este ADR fixa as decisões antes da primeira linha de
  código de auth.

## Decisões

### 1. Biblioteca de JWT — PyJWT

Mínima, mantida e suficiente para HS256. `python-jose` só compensaria se um
serviço externo precisasse validar o token via JWKS — não é o caso hoje.

### 2. Algoritmo de assinatura — HS256

Segredo simétrico único, lido de `JWT_SECRET` (variável de ambiente, nunca
versionado). Migrar para RS256 fica em aberto para quando/se outro serviço
precisar validar o token sem compartilhar o segredo.

### 3. Expiração do access token — 30 minutos

`ACCESS_TOKEN_EXPIRE_MINUTES` (default 30) em `app/config.py`. Curto por causa
da decisão 4 (existe refresh token para renovar sem exigir novo login).

### 4. Sessão persistente e logout (issue #83) — refresh token com rotação e revogação

RN da VS-005 exige que a sessão persista entre visitas até o logout; JWT é
stateless, então:

- Login/registro emitem **access token** (30 min) e **refresh token** (mais
  longo, `REFRESH_TOKEN_EXPIRE_DAYS`, default 30 dias), persistido com hash na
  tabela `refresh_tokens` (nunca o valor em texto puro).
- `POST /api/auth/refresh` valida o refresh token, revoga o usado e emite um
  par novo (rotação) — é o mecanismo que sustenta "sessão persiste entre
  visitas". Não estava no desenho original da #83 (só citava logout), mas é
  necessário para a estratégia funcionar; entra na mesma issue.
- `POST /api/auth/logout` revoga o refresh token informado. O access token em
  circulação continua válido até expirar (30 min) — aceitável dado o tempo
  curto; não há lista de revogação de access token nesta fase.

### 5. Hash de senha — bcrypt

Via `passlib[bcrypt]`, cost 12. Padrão de mercado, `password_hash` já é
`String(255)`, comporta o hash. Os usuários de seed (`app/seeds/lojas.py`)
gravam um valor sentinela (`"!seed-no-login"`) que não é um hash bcrypt válido
— a verificação deve falhar para eles por construção; coberto por teste.

### 6. Claim de papel no token — payload mínimo

Não existe coluna `role` em `users`: os papéis são compostos (comprador = todo
usuário; vendedor = tem linha em `sellers`; admin = `users.is_admin`) e um
usuário pode ser comprador **e** vendedor ao mesmo tempo. O payload carrega só
`sub` (id do usuário), `is_admin` e `exp`. `is_seller` **não** vai no token —
`require_seller` resolve por uma consulta a `sellers` a cada request. Efeito
colateral desejado: quem vira vendedor não precisa relogar.

### 7. Localização do código — `app/core/security.py`

Hash de senha, criação/validação de token e as dependencies de autorização
(`get_current_user`, `require_auth`, `require_seller`, `require_admin`,
`optional_user`) ficam em `app/core/`, ao lado de `errors.py` e
`pagination.py` — mesma fundação transversal do ADR 0001. Mudanças nesse
módulo são revisadas como mudança de contrato.

`optional_user` trata token ausente **ou** inválido/expirado como visitante
anônimo (não levanta erro) — uma rota pública não pode quebrar por causa de um
token velho no `Authorization`.

### 8. Rota de identidade — `GET /api/users/me`

Reafirma o ADR 0001 §4: recurso do usuário logado fica sob `/api/users/me`.
`/api/auth/*` continua reservado para ações de credencial (`register`,
`login`, `logout`, `refresh`). O texto da issue #84 ainda menciona
`GET /api/auth/me`; será atualizado por comentário na issue.

### 9. Ordem de execução

`BE-FND-3` (#72) é implementado antes das rotas de leitura pública (feed #85,
estilos #79, loja #108). Cada rota pública, quando chegar, inclui seu próprio
teste "sem token → 200" usando `optional_user`, em vez de um teste de
regressão único e antecipado no #72.

## Fora deste ADR

- Login social / OAuth de terceiros.
- MFA.
- Rotação de `JWT_SECRET` em produção (fica com a infra).

## Consequências

- `requirements.txt` ganha `PyJWT`, `passlib[bcrypt]` e `email-validator`
  (este último para `pydantic.EmailStr` nos schemas de cadastro/login).
- `app/config.py` e `.env.example` ganham `JWT_SECRET`, `JWT_ALGORITHM`,
  `ACCESS_TOKEN_EXPIRE_MINUTES` e `REFRESH_TOKEN_EXPIRE_DAYS`.
- Nova entidade `refresh_tokens` + migration, entregue na issue #83.
- `.ai/architecture.md` atualizado: autenticação sai de "decisões pendentes".
