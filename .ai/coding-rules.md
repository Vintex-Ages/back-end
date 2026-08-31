# Regras de código

- Use type hints e mantenha contratos Pydantic explícitos na fronteira da API.
- Preserve a separação `View/Route → Controller → Repository`; não pule camadas sem motivo registrado.
- Use injeção de dependência do FastAPI para sessão, serviços e autenticação.
- Não exponha models do banco diretamente quando um schema de resposta for necessário.
- Controllers expressam regras de negócio; repositories encapsulam persistência; views traduzem HTTP.
- Não armazene senha em texto puro, não registre segredos/tokens e não crie autenticação mock como solução final.
- Leia segredos e configuração do ambiente; não incorpore credenciais reais no código.
- Trate transações e rollback explicitamente em operações mutáveis.
- Use migrations para mudanças de schema; não dependa de criação implícita em produção.
- Cubra casos de sucesso, validação, autorização, inexistência e falhas relevantes com Pytest.
- Preserve Ruff e Black; não silencie regras apenas para passar o CI.
- Antes de concluir, execute `pytest tests/ -v`, `ruff check .` e `black --check .`, conforme o escopo.
