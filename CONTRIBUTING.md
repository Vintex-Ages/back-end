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
- Preencha o template inteiro e use `Closes #<issue>` como referência primária lida pela automação.
- A primeira issue vinculada deve ser a issue indicada na branch. Outras issues podem ser incluídas, desde que não tenham milestones conflitantes.
- Como os PRs de trabalho apontam para `develop` e `main` é a branch padrão, o GitHub não cria o vínculo nativo em Development a partir da keyword. Para exibi-lo, vincule o PR manualmente na sidebar Development ou crie a branch pela própria issue antes de começar o trabalho.
- Selecione exatamente um tipo de mudança.
- Declare como IA foi utilizada ou informe explicitamente que não houve uso.
- Assignees e labels são unidos a partir das issues; a milestone e os campos dos Projects vêm da issue primária.
- O PR entra no Project do backend e no Project geral. Draft fica em `In progress`, PR pronto em `In review` e merge em `Done`.
- O GitHub solicita review aos quatro integrantes de AGES III. O merge exige duas aprovações vigentes, que podem vir de AGES III ou AGES IV.
- Faça commits pequenos; novo commit invalida aprovações anteriores.

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
