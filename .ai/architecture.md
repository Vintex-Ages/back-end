# Arquitetura

## Camadas observadas

- `app/views/`: routers e detalhes HTTP.
- `app/controllers/`: orquestração e regras de negócio.
- `app/repositories/`: persistência e queries SQLAlchemy.
- `app/schemas/`: contratos de entrada e saída Pydantic.
- `app/models/`: entidades e mapeamento SQLAlchemy.
- `app/database.py`: conexão e sessões.
- `app/config.py`: configuração por ambiente.
- `app/main.py`: composição da aplicação e middleware.

Fluxo esperado: `Route/View → Controller → Repository → Model/Database`, usando schemas na fronteira HTTP. Rotas não devem conter queries; repositories não devem decidir respostas HTTP; models não devem acumular orquestração de casos de uso.

## Autenticação

JWT é a direção arquitetural informada para o Vintex. Porém, o clone atual não contém implementação JWT nem dependência correspondente. Não copie a antiga regra de autenticação mock e não declare autenticação pronta. Antes de implementar, confirme biblioteca, algoritmo, expiração, refresh/revogação, armazenamento de senha, papéis e política de autorização.

## Decisões pendentes

- contrato e estratégia completa de autenticação/autorização JWT;
- padrão de migrations e ciclo de ambientes;
- formato comum de erros e versionamento da API;
- política de CORS por ambiente (o código atual permite todas as origens);
- fronteiras de transação e estratégia de testes com banco.
