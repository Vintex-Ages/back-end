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
| `make infra-up` | Sobe o Compose `vintex-infra` e aguarda os health checks. |
| `make infra-down` | Derruba só os containers/rede/volume do projeto `vintex-infra`. |
| `make infra-local-test` | Testes locais (unitários, Terraform mockado, LocalStack, MiniStack, interoperabilidade), sem derrubar o ambiente. |
| `make infra-complete` | QA + subida + testes + `infra-down`, sempre derrubando o ambiente no final, preservando a primeira falha. |

## Terraform

`infra/terraform/envs/local` configura o provider AWS apontando para o LocalStack (S3, SQS, Secrets Manager, IAM, STS) e o MiniStack (ECS, Cloud Map, API Gateway, ECR). Nenhum recurso é declarado ainda — os módulos de feature entram em `infra/terraform/modules/` conforme cada issue (VE-14 a VE-19) sai do hold. `terraform test` roda mockado (`mock_provider`), sem tocar rede nenhuma.

## Estado atual (S2)

Ativo nesta sprint: base local ([VE-12, #163](https://github.com/Vintex-Ages/back-end/issues/163)), estrutura Terraform ([VE-13, #164](https://github.com/Vintex-Ages/back-end/issues/164)), integração LocalStack ([VE-20, #171](https://github.com/Vintex-Ages/back-end/issues/171)), integração MiniStack ([VE-21, #172](https://github.com/Vintex-Ages/back-end/issues/172)) e testes de interoperabilidade ([VE-22, #173](https://github.com/Vintex-Ages/back-end/issues/173)).

Em hold: os módulos de feature (rede, banco/pgvector, storage, mensageria, worker, computação) e os gates de CI/promoção — ver a lista completa no épico VE-29.
