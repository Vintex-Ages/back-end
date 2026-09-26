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
| `make infra-up` | Reconstrói a imagem da API, sobe o Compose `vintex-infra`, aguarda os health checks, aplica migrations no Postgres e prepara recursos sintéticos. |
| `make infra-down` | Derruba só os containers/rede/volume do projeto `vintex-infra`. |
| `make infra-local-test` | Testes locais (unitários, Terraform mockado, PostgreSQL, LocalStack, mídia S3, MiniStack, interoperabilidade), sem derrubar o ambiente. |
| `make test-media-storage` | Confere bucket privado e upload, leitura e limpeza de mídia no LocalStack. |
| `make infra-complete` | QA + subida + testes + `infra-down`, sempre derrubando o ambiente no final, preservando a primeira falha. |

## Terraform

`infra/terraform/envs/local` configura o provider AWS apontando para o LocalStack (S3, SQS, Secrets Manager, IAM, STS) e o MiniStack (EC2, ECS, Cloud Map, API Gateway, ECR). A [VE-14 (#165)](https://github.com/Vintex-Ages/back-end/issues/165) declara módulos de rede e papel mínimo ECS; a [VE-16 (#167)](https://github.com/Vintex-Ages/back-end/issues/167) acrescenta o bucket privado de mídia. `terraform test` roda mockado (`mock_provider`), sem tocar os emuladores ou a AWS real; não há `terraform apply` nesta etapa. Banco, mensageria, worker e computação seguem nas respectivas issues.

O módulo de rede especifica VPC, duas subnets em zonas distintas e rota pelo Internet Gateway. Nenhuma subnet atribui IP público automaticamente. A API só aceita a porta 8000 do security group do VPC Link; o worker não tem ingress. Os dois têm saída HTTPS, e o VPC Link só pode alcançar a API. O papel de execução ECS tem confiança apenas para tasks ECS e a política gerenciada de ECR/logs, sem permissões de aplicação. Cada task Fargate recebe uma ENI via `awsvpc`; a VE-19 deverá escolher subnets, grupos e a atribuição explícita de IP público para cada task que precise de saída HTTPS, inclusive ECR/logs, já que não há NAT. Os grupos continuam sem ingress público. A VE-15 tratará as regras de acesso ao banco.

## PostgreSQL (VE-15)

O serviço `db` usa PostgreSQL 16, persiste no volume nomeado `vintex_infra_pgdata` e só fica saudável quando `pg_isready` responde. A API depende desse estado saudável; `make infra-up` aplica as migrations Alembic antes de preparar os recursos sintéticos. Para validar o banco após a subida, execute `make test-infra-postgres`: o teste confirma PostgreSQL ativo, todas as migrations no head atual, tabelas `products` e `users`, e uma gravação/leitura temporária.

Para repetir o ciclo sobre uma base vazia, execute `make infra-down` e depois `make infra-up`; o `down` remove o volume dedicado do projeto. `make infra-complete` também testa e remove o ambiente ao final.

A dimensão, índice e métrica vetorial seguem a proposta da PR #188 — 768 dimensões, IVFFlat e distância cosseno — ainda pendente de review. A imagem `pgvector/pgvector` e a migration da extensão `vector` pertencem à [subissue #185](https://github.com/Vintex-Ages/back-end/issues/185), mantida em hold para revisar junto com a [PR #188](https://github.com/Vintex-Ages/back-end/pull/188). Esta etapa testa o PostgreSQL base e não ativa busca semântica.

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

## Storage de mídia (VE-16)

`make infra-up` também prepara `vintex-local-media` no LocalStack, com bloqueio
de acesso público e criptografia AES256. O módulo Terraform declara esse mesmo
bucket, sem aplicar o plano. Os prefixos lógicos propostos são:

| Tipo | Prefixo |
| --- | --- |
| Fotos de peças | `products/photos/` |
| Vídeos curtos | `products/videos/` |
| Comprovantes Pix | `payments/receipts/` |

São prefixos de chaves de objeto, sem pastas ou marcadores vazios. A proposta
deve ser alinhada ao habilitador [VE-04 (#59)](https://github.com/Vintex-Ages/back-end/issues/59),
que define formatos, tamanhos e URLs para o front. A VE-16 não expõe rota HTTP.

O serviço `app/services/media_storage.py` lê `MEDIA_BUCKET`, `AWS_REGION` e
`S3_ENDPOINT_URL` de `app/config.py`. O Compose configura
`http://localstack:4566` e credenciais fictícias. Em AWS real, configure
`MEDIA_BUCKET` e região, omita `S3_ENDPOINT_URL` e forneça credenciais pela
cadeia padrão do boto3 ou role; não há credenciais embutidas no serviço.

```bash
make infra-up
make test-media-storage
make test-media-storage  # repetição confirma limpeza e isolamento
make infra-down
```

O teste cria uma chave única por upload, lê o conteúdo e exclui cada objeto
mesmo se a asserção falhar. Depois confirma a ausência da chave e as proteções
do bucket. `make infra-local-test` inclui esse alvo.

## MiniStack (VE-21)

`make infra-up` prepara um cluster ECS, uma task definition e um serviço Fargate com zero tarefas, um namespace e serviço Cloud Map, uma HTTP API e um repositório ECR sintéticos. O serviço Fargate usa VPC, subnet e grupo de segurança criados apenas como metadados de teste no MiniStack. O fluxo não inicia containers ECS; a execução de tarefas reais depende do socket Docker e fica para a etapa de computação.

```bash
make infra-up
make test-ministack
make test-ministack  # confirma que o provisionamento é idempotente
make infra-down
```

Os comandos rodam no container da API por `http://ministack:4567`, alias da rede Compose. O host usa `MINISTACK_HOST_PORT` de `infra/vintex-infra/.env` (padrão `4567`), ou `MINISTACK_ENDPOINT_URL=http://127.0.0.1:4567` explícito. Só são aceitos endereços HTTP locais ou o alias `ministack`, sempre com credenciais fictícias `test`. Os smoke tests validam o plano de controle; a interoperação entre emuladores é descrita abaixo.

O handoff de infraestrutura (item 10) e os critérios de aceite da VE-21 delimitam esta integração local a ECS, Cloud Map, HTTP API e ECR. O módulo Terraform de VPC Link é entregável da [VE-19 (#170)](https://github.com/Vintex-Ages/back-end/issues/170), hoje em hold. A imagem MiniStack atual responde 404 a `GetVpcLinks` (`/v2/vpclinks`); essa limitação deverá ser tratada ao retomar a VE-19. O script da VE-21 não simula VPC Link.

## Interoperabilidade e limpeza (VE-22)

`make test-interoperability` usa os aliases `api`, `localstack` e `ministack` dentro do Compose. Ele verifica a API contra o Postgres migrado, publica uma mensagem na fila SQS, executa um consumidor sintético que grava o resultado em S3 e registra a localização no Cloud Map. O teste consulta os dados nos dois emuladores e remove bucket, fila e registro ao final. Outro caso injeta falha após a gravação em S3 e confirma que nenhum desses recursos temporários fica para trás. O consumidor é somente um harness de infraestrutura: o worker de produto permanece na [VE-18 (#169)](https://github.com/Vintex-Ages/back-end/issues/169), em hold.

```bash
make infra-complete  # QA, subida, testes e teardown
make infra-complete  # repetição confirma isolamento entre execuções
```

`make infra-local-test` executa suíte da API, Terraform mockado e os alvos de integração sem derrubar o ambiente; use após `make infra-up`. `make infra-complete` executa `infra-down` mesmo se QA, subida ou algum teste falhar. O script preserva o código da primeira falha; se somente a limpeza falhar, devolve o código dela. Os testes unitários de orquestração exercitam falhas em QA, subida, testes e teardown.

## Estado atual (S2)

Base local ([VE-12, #163](https://github.com/Vintex-Ages/back-end/issues/163)) e estrutura Terraform ([VE-13, #164](https://github.com/Vintex-Ages/back-end/issues/164)) concluídas. As integrações LocalStack ([VE-20, #171](https://github.com/Vintex-Ages/back-end/issues/171)) e MiniStack ([VE-21, #172](https://github.com/Vintex-Ages/back-end/issues/172)) provisionam e testam os recursos sintéticos previstos nesta sprint. A interoperabilidade ([VE-22, #173](https://github.com/Vintex-Ages/back-end/issues/173)) cobre o fluxo local e o teardown. A rede e segurança ([VE-14, #165](https://github.com/Vintex-Ages/back-end/issues/165)) foi concluída na PR #192; a base PostgreSQL da VE-15 (#166) foi concluída na PR #193. O storage de mídia da VE-16 (#167) é a etapa atual.

Em hold: a extensão pgvector ([VE-31, #185](https://github.com/Vintex-Ages/back-end/issues/185)) aguarda review da PR #188. Mensageria, worker, computação e gates de CI/promoção seguem no backlog do épico VE-29.
