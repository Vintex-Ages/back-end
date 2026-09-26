---
sidebar_position: 1
---

# Infraestrutura de teste local

Terraform, Docker Compose, LocalStack e MiniStack — ferramentas de desenvolvimento e teste local da equipe, sem custo de AWS. Ver o épico [VE-29 (#180)](https://github.com/Vintex-Ages/back-end/issues/180) para o backlog completo.

## Subir o ambiente

```bash
cp infra/vintex-infra/.env.example infra/vintex-infra/.env
make infra-up
```

Sobe Postgres, API, LocalStack (`4566`) e MiniStack (`4567`) numa rede Docker própria (`vintex-infra-net`), isolada do compose de desenvolvimento da raiz.

## Alvos do Makefile

| Alvo | O que faz |
| --- | --- |
| `make infra-qa` | Lint, format-check e `terraform fmt/init/validate`. Nunca executa `terraform apply`. |
| `make infra-up` | Reconstrói a imagem da API, sobe o Compose `vintex-infra` e aguarda os health checks. |
| `make infra-down` | Derruba só os containers/rede/volume do projeto `vintex-infra`. |
| `make infra-local-test` | Testes locais (unitários, Terraform mockado, LocalStack, MiniStack, interoperabilidade), sem derrubar o ambiente. |
| `make infra-complete` | QA + subida + testes + `infra-down`, sempre derrubando o ambiente no final, preservando a primeira falha. |

## Terraform

`infra/terraform/envs/local` configura o provider AWS apontando para o LocalStack (S3, SQS, Secrets Manager, IAM, STS) e o MiniStack (ECS, Cloud Map, API Gateway, ECR). Nenhum recurso é declarado ainda — os módulos de feature entram em `infra/terraform/modules/` conforme cada issue (VE-14 a VE-19) sai do hold. `terraform test` roda mockado (`mock_provider`), sem tocar rede nenhuma.

## LocalStack (VE-20)

`make infra-up` prepara um bucket, uma fila, um segredo e um usuário IAM sintéticos no LocalStack. O script verifica também STS. Ele pode ser executado de novo sem duplicar os recursos. Os nomes começam com `vintex-infra-`; o segredo contém apenas `{"synthetic": true}`.

```bash
make infra-up
make test-localstack
make test-localstack  # segunda execução confirma isolamento e limpeza
make infra-down
```

O provisionamento e `make test-localstack` rodam dentro do container da API, onde as dependências Python do projeto já estão instaladas. Os testes criam, leem e removem recursos de S3, SQS, Secrets Manager e IAM, além de consultar STS, pelo alias `http://localstack:4566`. Objetos temporários recebem nomes únicos e são removidos ao final do teste. `make infra-down` remove os containers, a rede e os volumes do projeto `vintex-infra`.

No host, a porta vem de `LOCALSTACK_HOST_PORT` em `infra/vintex-infra/.env` (padrão `4566`). Para apontar explicitamente ao emulador, use `LOCALSTACK_ENDPOINT_URL=http://127.0.0.1:4566`. A ferramenta só aceita endereços HTTP locais ou o alias `localstack` e usa credenciais fictícias `test`; ela não chama a AWS real.

## MiniStack (VE-21)

`make infra-up` prepara um cluster ECS, uma task definition e um serviço Fargate com zero tarefas, um namespace e serviço Cloud Map, uma HTTP API e um repositório ECR sintéticos. O serviço Fargate usa VPC, subnet e grupo de segurança criados apenas como metadados de teste no MiniStack. O fluxo não inicia containers ECS; a execução de tarefas reais depende do socket Docker e fica para a etapa de computação.

```bash
make infra-up
make test-ministack
make test-ministack  # confirma que o provisionamento é idempotente
make infra-down
```

Os comandos rodam no container da API por `http://ministack:4567`, alias da rede Compose. O host usa `MINISTACK_HOST_PORT` de `infra/vintex-infra/.env` (padrão `4567`), ou `MINISTACK_ENDPOINT_URL=http://127.0.0.1:4567` explícito. Só são aceitos endereços HTTP locais ou o alias `ministack`, sempre com credenciais fictícias `test`. Os smoke tests validam o plano de controle; a interoperação entre emuladores fica para a VE-22.

**Limitação para revisão:** a imagem MiniStack atual não implementa `GetVpcLinks`/`CreateVpcLink` da API Gateway v2 (`/v2/vpclinks` responde 404). O VPC Link pedido na descrição da VE-21 permanece pendente; não é simulado pelo script. Uma versão do emulador com essas operações ou outra decisão de implementação é necessária antes de considerar esse ponto concluído.

## Estado atual (S2)

Base local ([VE-12, #163](https://github.com/Vintex-Ages/back-end/issues/163)) e estrutura Terraform ([VE-13, #164](https://github.com/Vintex-Ages/back-end/issues/164)) concluídas. A integração LocalStack ([VE-20, #171](https://github.com/Vintex-Ages/back-end/issues/171)) provisiona recursos sintéticos e os testa. A integração MiniStack ([VE-21, #172](https://github.com/Vintex-Ages/back-end/issues/172)) cobre ECS, Cloud Map, HTTP API e ECR, com VPC Link pendente por falta de suporte do emulador. Os testes de interoperabilidade ([VE-22, #173](https://github.com/Vintex-Ages/back-end/issues/173)) aguardam a revisão desta etapa.

Em hold: os módulos de feature (rede, banco/pgvector, storage, mensageria, worker, computação) e os gates de CI/promoção — ver a lista completa no épico VE-29.
