# Vintex - Backend

Consulte o [guia de contribuição](CONTRIBUTING.md) antes de abrir uma issue ou Pull Request.

Backend da aplicação Vintex, desenvolvido com **Python** e **FastAPI**, seguindo o padrão **MVC**.

Documentação viva (arquitetura, decisões, infraestrutura) em [`documentation/`](documentation/README.md).

O catálogo de funcionalidades está disponível na seção [Features](documentation/docs/features/index.md).

## Arquitetura

```
app/
├── models/          # Model — entidades do banco (SQLAlchemy)
├── views/           # View — rotas/endpoints (FastAPI Routers)
├── controllers/     # Controller — lógica de negócio
├── schemas/         # DTOs — validação de request/response (Pydantic)
├── repositories/    # Acesso a dados (queries)
├── config.py        # Configurações (env vars)
├── database.py      # Conexão com o banco
└── main.py          # Entrypoint da aplicação
```

## Tecnologias

- Python 3.12
- FastAPI
- SQLAlchemy 2.0
- PostgreSQL
- Alembic (migrations)
- Docker

## Setup local

```bash
# Clonar o repositório
git clone <repo-url>
cd vintex-backend

# Criar e ativar venv
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Instalar dependências
pip install -r requirements.txt

# Copiar variáveis de ambiente e configurar a URL do banco
cp .env.example .env
```

> **Nota:** A `DATABASE_URL` deve ser fornecida pelo responsável pelo banco de dados.

```bash
# Rodar a API
uvicorn app.main:app --reload
```

A API estará disponível em `http://localhost:8000`.
Documentação Swagger em `http://localhost:8000/docs`.

## Migrations

O schema do banco é versionado com Alembic. `alembic/env.py` lê `DATABASE_URL` de `app/config.py` — nunca configure a URL diretamente no `alembic.ini`.

```bash
# Aplicar todas as migrations pendentes (banco vazio -> estado atual)
alembic upgrade head

# Reverter a última migration
alembic downgrade -1

# Reverter todas as migrations (volta ao banco vazio)
alembic downgrade base

# Criar uma nova revisão a partir das mudanças nos models (app/models/)
alembic revision --autogenerate -m "descricao_da_mudanca"

# Criar uma revisão vazia (sem autogenerate), para editar manualmente
alembic revision -m "descricao_da_mudanca"

# Ver o histórico de revisões / a revisão atual do banco
alembic history
alembic current
```

Sempre revise o arquivo gerado em `alembic/versions/` antes de aplicar — o autogenerate não detecta tudo (renomear coluna, alguns constraints, etc.).

## Seeds

Dados sintéticos para desenvolvimento e demo. Rode **depois** de `alembic upgrade head`, nesta ordem:

```bash
python -m app.seeds.lojas   # endereços, vendedores e lojas (RS)
python -m app.seeds.pecas   # peças e imagens, distribuídas entre as lojas
```

Ambos são idempotentes — rodar de novo não duplica.

## Testes

```bash
pytest tests/ -v
```

## Lint

```bash
ruff check .
black --check .
```

## Infraestrutura de teste local

Projeto Compose complementar (`vintex-infra`), isolado do compose de dev da raiz — sobe Postgres, API, LocalStack e MiniStack numa rede própria. Ver a issue [VE-29](https://github.com/Vintex-Ages/back-end/issues/180) para o desenho completo e o backlog relacionado.

```bash
# Copiar as variáveis de ambiente do projeto de infra (sem segredos)
cp infra/vintex-infra/.env.example infra/vintex-infra/.env
```

Alvos principais:

| Alvo | O que faz |
| --- | --- |
| `make infra-qa` | Lint, format-check e `terraform fmt/init/validate`. Nunca executa `terraform apply`. |
| `make infra-up` | Reconstrói a API, sobe o Compose `vintex-infra`, aplica migrations locais e prepara recursos sintéticos. |
| `make infra-down` | Derruba somente os containers/redes/volumes do projeto `vintex-infra`. |
| `make infra-local-test` | Roda os testes locais (unitários, Terraform mockado, PostgreSQL, LocalStack, MiniStack, interoperabilidade) sem derrubar o ambiente. |
| `make infra-complete` | QA + subida + testes + `infra-down`, sempre derrubando o ambiente no final (mesmo em falha), preservando o código de saída da primeira falha. |

Alvos granulares para diagnóstico: `lint`, `format-check`, `terraform-init`, `terraform-fmt`, `terraform-validate`, `terraform-test`, `test-unit`, `test-infra-postgres`, `test-localstack`, `test-ministack`, `test-interoperability`.

`test-localstack`, `test-ministack` e `test-interoperability` executam testes reais dos emuladores e do fluxo local (VE-20/VE-21/VE-22). `infra-up` aplica as migrations ao Postgres local, e `test-unit` roda no container da API. A interoperabilidade usa um consumidor SQS sintético; o worker de produto pertence à VE-18 (#169), em hold. O módulo Terraform de VPC Link pertence à VE-19 (#170), também em hold.

A [VE-14 (#165)](https://github.com/Vintex-Ages/back-end/issues/165) acrescenta módulos Terraform de rede e papel de execução ECS, exercitados apenas por plano mockado. A interface de cada task Fargate será criada pelo modo `awsvpc` quando a VE-19 ligar os módulos à computação; nenhum recurso AWS real é aplicado nesta fase. Veja [a documentação de Terraform](infra/terraform/README.md).

## Convenção de branches

```
feature/<issue-number>-<descricao>
bugfix/<issue-number>-<descricao>
hotfix/<issue-number>-<descricao>
```

Exemplo: `feature/42-tela-de-login`
