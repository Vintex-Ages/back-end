# Vintex - Backend

Backend da aplicação Vintex, desenvolvido com **Python** e **FastAPI**, seguindo o padrão **MVC**.

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

## Testes

```bash
pytest tests/ -v
```

## Lint

```bash
ruff check .
black --check .
```

## Convenção de branches

```
feature/<issue-number>-<descricao>
bugfix/<issue-number>-<descricao>
hotfix/<issue-number>-<descricao>
```

Exemplo: `feature/42-tela-de-login`
