# Contribuindo com o Vintex

## Fluxo de branches

`main` é a branch padrão e representa a versão principal. O desenvolvimento diário parte de `develop`.

```text
branch de trabalho -> develop -> main -> deploy
```

Crie branches a partir de `develop` usando um dos formatos:

```text
feature/<issue>-<descricao>
bugfix/<issue>-<descricao>
hotfix/<issue>-<descricao>
refactor/<issue>-<descricao>
docs/<issue>-<descricao>
chore/<issue>-<descricao>
```

Use palavras minúsculas separadas por hífen. Todo trabalho deve possuir uma issue.

## Pull Requests

- PRs de trabalho apontam para `develop`.
- Somente `develop` promove para `main`.
- Somente `main` promove para `deploy`.
- Preencha o template inteiro e use `Closes #<issue>`.
- Selecione exatamente um tipo de mudança.
- Declare como IA foi utilizada ou informe explicitamente que não houve uso.
- Faça commits pequenos e solicite review.

## Backend

O backend usa Python 3.12, FastAPI, SQLAlchemy e arquitetura MVC:

```text
View -> Controller -> Repository
```

Schemas Pydantic validam entrada e saída; Models SQLAlchemy representam persistência.

Antes do push, execute:

```bash
ruff check .
black --check .
pytest tests/ -v
mypy app/ --ignore-missing-imports
```

Nunca versionar credenciais, `.env` ou material interno de auditoria.
