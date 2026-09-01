# Exemplos de aplicação

## Novo endpoint de domínio

1. Confirmar contrato, autorização e casos de erro.
2. Criar/ajustar schemas Pydantic.
3. Implementar persistência no repository.
4. Implementar regra de negócio no controller.
5. Expor HTTP na view/router e registrar o router em `app/main.py`.
6. Criar migration quando o schema do banco mudar.
7. Testar sucesso, validação, inexistência e autorização relevantes.

## Mudança que exige decisão

Escolher biblioteca JWT, política de refresh/revogação, papéis ou fronteira transacional não é detalhe local. Documente alternativas e obtenha decisão antes de consolidar o padrão.
