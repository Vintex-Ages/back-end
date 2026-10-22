---
sidebar_position: 7
---

# Ambiente AWS real de staging (#274)

A [#274](https://github.com/Vintex-Ages/back-end/issues/274), parte do
[épico #180](https://github.com/Vintex-Ages/back-end/issues/180), reúne a
[base #272](./aws-shared.md) e o
[runtime e deploy manual #273](./aws-staging-runtime.md).
O responsável executa bootstrap, apply e deploy com o perfil AWS autorizado na subconta institucional.
**Os testes e o CI não provisionam recursos AWS.**

## Recursos e contratos

| Componente | Configuração |
| --- | --- |
| State | Bucket administrativo criado pelo Terraform, chave `vintex/staging/terraform.tfstate`, criptografia e lock nativo S3 |
| Provider | Ohio `us-east-2`, `allowed_account_ids`, sem endpoints locais ou access keys |
| EC2 | `t4g.small`, Amazon Linux 2023 ARM64, EBS gp3 criptografado de 10 GB e swap de 1 GiB |
| Rede | VPC/subnet criadas no mesmo plano, IPv4 automático, nenhum ingress, saída TCP 443 |
| Metadados | IMDSv2 obrigatório, hop limit 2, IPv6 desativado; guard da #273 instalado antes do Docker |
| Mídia | `vintex-media-staging-<CONTA>`, privado, AES256, ACLs desativadas e HTTP negado |
| Mensageria | `vintex-ai-staging` e DLQ, SSE-SQS, polling 20 s, visibilidade 180 s, redrive após 3 entregas, DLQ 14 dias |
| Parâmetros | Seis SecureString Standard em `/vintex/staging/`, inicialmente provisórios |
| Logs | `/vintex/staging/{proxy,api,worker,freellmapi,db}`, retenção 7 dias |
| Horário | Brasília, seg–sex liga 10h/desliga 22h; varredura diária desliga 02h |

Tags: `Project=Vintex`, `Environment=staging`, `ManagedBy=Terraform`.
Não há Elastic IP, SSH, CloudFront, RDS, backup, pipeline ou recurso de produção.
O banco continua sendo **db:5432 do Compose**, com pgvector/Postgres 16 e migrations
existentes; Terraform não cria outro banco.

O módulo `ai_messaging` aceita os tempos da staging, preservando os defaults do
ambiente local. O bootstrap instala Docker, iptables-nft, Python 3.12/boto3 e
Compose ARM64 v5.6.0 com checksum fixado. Python 3.12 é explícito: o Python
padrão do Amazon Linux 2023 é 3.9. A instância usa créditos CPU Standard para
não gerar cobrança de surplus. O disco é descartado ao destruir a EC2.

O bootstrap não sobe aplicações nem lê segredos. Alterações em AMI/user data
são ignoradas no host existente, para evitar substituição automática; futuras
atualizações do host/guard exigem manutenção manual revisada. O serviço guard
é dependência do Docker e é reaplicado a cada boot. Sua implementação/testes
permanecem na #273; não há mudança de firewall na máquina do desenvolvedor.

## IAM e isolamento

`VintexStagingInstanceRole` permite autenticação ECR, pull dos dois repositórios
da staging, acesso apenas à mídia/fila/parâmetros/logs staging e agente SSM.
Não permite push de imagens, leitura de backups/recursos prod nem consumo da DLQ.
A inspeção da DLQ é uma operação humana.

A policy `AmazonSSMManagedInstanceCore` contém GetParameter(s) com Resource `*`.
Por isso há **Deny explícito de `ssm:GetParameter*` fora de `/vintex/staging/*`**,
que prevalece sobre essa concessão. Recursos adicionais do Systems Manager que
precisem ler parâmetros fora desse caminho não fazem parte deste baseline.
API/worker usam a role pelo IMDS; proxy, db e FreeLLMAPI são bloqueados pelo
guard. Não colocar credenciais SSO nos contêineres ou na EC2.

`VintexStagingSchedulerRole` aceita somente o Scheduler da conta e do grupo
`vintex-staging`; Start/Stop se restringem ao ARN da instância e suas tags.
Os alvos universais EC2 têm janela flexível desativada, retry limitado a 2
vezes e idade máxima 300 s, para evitar ligar horas depois do horário.
Agendamento de desligamento após ativação sob demanda pertence ao pipeline futuro.

## Conta vazia: infraestrutura e aplicação

Configure o perfil institucional e o único `account.tfvars.json` conforme o
[README Terraform](https://github.com/Vintex-Ages/back-end/blob/develop/infra/terraform/README.md),
incluindo os e-mails reais do Budget. Na raiz do backend:

```bash
make terraform-validate staging
make infra-deploy staging
```

O primeiro comando não exige credenciais e usa cache QA com backend desativado.
O segundo verifica a conta em us-east-2 e conduz dois planos/applies revisados:
criação/proteção do bucket administrativo e staging completa (rede, ECR, Budget e
runtime AWS). Cada apply pede o nome da etapa; falha interrompe a sequência.
Reexecutar o mesmo comando após corrigir a causa gera novos planos sobre o state
preservado. Não há retry automático nem criação manual de bucket.

`state/bootstrap/` conserva state e identidade do bucket fora do cache; faça
backup privado. O state completo da staging usa `vintex/staging/terraform.tfstate`,
com lock S3. Estados antigos separados exigem migração revisada. A role EC2 não
acessa state. States/plans podem conter SecureString após refresh, mesmo com
ignore_changes; nunca os anexe à issue, Git ou imagem.

Os comandos granulares `make terraform-{init,plan,show,apply,output} staging`
continuam disponíveis para operação por etapa após preparar o bucket. Comandos
Terraform nativos e as diferenças em relação ao runner estão no README.

Depois da infraestrutura, publicar a aplicação pelo procedimento #273:

1. Aguardar a instância ficar `Online` no Systems Manager. Abrir sessão:

   ```bash
   aws ssm start-session --profile vintex-terraform --region us-east-2 --target <INSTANCE_ID>
   ```

   Na EC2, verificar bootstrap sem imprimir env/segredos:

   ```bash
   sudo cloud-init status --wait
   sudo test -f /var/lib/vintex-staging/bootstrap-ready
   sudo systemctl is-active vintex-imds-guard.service docker amazon-ssm-agent
   sudo docker compose version
   /opt/vintex/deploy-venv/bin/python --version
   ```

   Se falhar, diagnosticar cloud-init antes de implantar; não desativar o guard
   para contornar falha. Boot real, downloads e capacidade ARM64 dependem da conta
   e ainda precisam de evidência operacional.

## Parâmetros e primeiro deploy

No console Parameter Store, substituir os valores de `db_password`, `jwt_secret`,
`llm_encryption_key`, `llm_admin_email` e `llm_admin_password`, conforme o
[contrato da #273](./aws-staging-runtime.md#parâmetros-e-ia). Todos são SecureString.
Terraform ignora futuras mudanças de valor; não gravar valores reais em tfvars.
Não trocar a chave de criptografia se o SQLite do FreeLLMAPI já contiver dados.

`llm_api_key` pode continuar provisório até configurar o dashboard. O script
ignora `REPLACE_MANUALLY_BEFORE_DEPLOY`: parâmetro obrigatório provisório impede
o deploy; token de IA provisório equivale a ausente. Sem token, o worker segue
a falha/retry/DLQ existente, e API/health continuam disponíveis. Gravar o token
unificado **apenas na AWS** depois de cadastrar provedores exclusivos de staging
e reexecutar o deploy para atualizar worker. A variável local `.env` permanece
inalterada. Chat/embeddings usam o provider indisponível já definido no runtime.
Cotas de produto ainda não implementadas não são entregues por esta issue.

Usar `runtime_resources` para preencher o config.json administrativo da #273.
Acrescentar SHA completo, paths do release e frontend; `parameter_path` é
informativo, o script já fixa `/vintex/staging/`. Fazer build/push ARM64,
espelhar FreeLLMAPI e transferir o build estático do front conforme o
[roteiro do runtime](./aws-staging-runtime.md#build-e-envio-manual-máquina-do-responsável).
O bootstrap já instala o guard e o venv do deploy; não é preciso exportar
credenciais na EC2. Executar o script da #273 como root com a role da instância.

Acesso ao front/API: túnel SSM porta 80 → localhost:8080. Dashboard: outro túnel
porta 3001 → localhost:3001. Não existe URL pública da staging; o túnel é
criptografado/autenticado. O front aprovado usa `VITE_API_BASE_URL=/api`.

## Horário e validação operacional

O apply lança a EC2 ligada, mesmo fora da janela. Após preparar/testar, desligar
manualmente se estiver fora do horário. Para testar sob demanda, o responsável
pode usar Start/Stop no console; os schedules recorrentes continuam ativos e
podem desligar a instância durante uma sessão. O pipeline futuro acrescentará
o desligamento após duas horas; por enquanto acompanhar o uso manualmente.
Stop preserva EBS e volumes, embora dados staging sejam exclusivamente sintéticos.
Não restaurar backups de produção neste ambiente.

Após o primeiro deploy, anexar evidências sem segredos:

- SSM Online, bootstrap/serviços saudáveis e front/health pelo túnel.
- IAM Policy Simulator: staging lê seus parâmetros e não parâmetros prod;
  acessa sua mídia/fila/logs/ECR pull e não backups, mídia/fila prod, push ECR
  ou administração IAM. Scheduler só controla esta instância.
- IMDS alcançável somente em API/worker; testar sem imprimir tokens/credenciais.
- Upload/leitura de mídia sintética, processamento ou falha/retry/DLQ de job,
  logs dos cinco serviços e persistência de dados após restart.
- Conferir os três schedules/timezone, parada/retomada, Budget e uso real do disco.
  A memória/disk e o custo devem ser medidos na conta; os testes mockados não
  comprovam comportamento operacional nem faturamento.

Não usar `terraform destroy` para rollback de release. Destruir staging remove
seu disco; esvaziar mídia sintética é uma operação manual explícita se necessária
antes de remover bucket. Rede, ECR e Budget agora pertencem ao mesmo state da
staging; um destroy completo também os alcança. O bucket administrativo tem
state próprio e proteção contra destruição.

## Verificações sem AWS

```bash
make terraform-fmt
make terraform-validate staging
make terraform-test staging
pytest tests/test_terraform_env.py tests/test_terraform_make.py tests/test_infra_staging_config.py tests/test_staging_runtime.py -v
```

Os caches QA e operacionais são distintos; não é necessário outro checkout para
validar. Os testes Terraform só usam provider mockado e plan, cobrindo rede/ECR,
Budget, host/IAM, serviços, Scheduler, outputs e inputs inválidos. Pytest cobre
state/layout, retomada, CLI Make, região, segredos e isolamento. CI valida os roots
local/bootstrap/aws sem conta ou apply. Providers públicos podem ser baixados.

## Ensaio local de prontidão — 21/10/2026 (#288 / PR #289)

Revalidação da composição completa, iniciada no commit `1cf85287f9391f5cd12aec09a1324bb2ed72a264`.
As únicas alterações versionadas posteriores deste ensaio são neste relatório e no roteiro
manual, para remover a etapa shared antiga e documentar os pré-requisitos do
computador do responsável. Nenhum apply, credencial real de IA ou recurso AWS
foi utilizado. O CI do commit publicado deve continuar aprovado antes do merge.

| Verificação | Resultado |
| --- | --- |
| `make infra-qa` | Ruff, Black, Terraform fmt/validate aprovados |
| Terraform validate/test local, bootstrap e staging | 6 + 3 + 19 planos mockados aprovados |
| Testes focados Terraform/Make/config/documentação/Compose no checkout | 99 aprovados |
| Testes runtime/Compose no checkout | 33 aprovados (há sobreposição do teste Compose com a linha anterior) |
| `make infra-up` | Quatro serviços saudáveis, migrations até `e4a2c7b9d1f3`, seeds aprovados |
| Suíte geral na imagem reconstruída | 563 aprovados, 76 pulados, 325 warnings |
| PostgreSQL no banco migrado do Compose | 1 probe aprovado; 33 testes PostgreSQL aprovados e 2 migrations puladas por segurança |
| LocalStack / SQS / mídia / MiniStack / interoperabilidade | Respectivamente 2 / 2 / 3 / 3 / 3 testes aprovados, seeds e verificações aprovados |
| Worker e E2E HTTP → mídia → SQS → worker → banco | 4 aprovados; sucesso sintético, erro do provedor e chave ausente/retry/DLQ |
| Persistência após restart do db | Registro sintético preservado em `db:5432`, depois removido; API saudável |
| PostgreSQL descartável no mesmo contêiner db | 35 aprovados, incluindo as duas migrations com downgrade/upgrade; banco temporário removido |
| Nginx real | SPA, prefixo API, 404, cache e rate limit aprovados |
| Guard IMDS em namespaces isolados | API/worker permitidos; proxy/db/FreeLLMAPI bloqueados; firewall do host inalterado |
| FreeLLMAPI v0.14.2 AMD64 | `/api/ping` saudável, SQLite criado, sem chave e sem rede, limite 128 MiB, sem OOM no smoke test |
| Manifestos oficiais fixados | Nginx, pgvector e FreeLLMAPI disponíveis em ARM64 |

Os logs resumidos e o SHA final são anexados à issue/PR. Os testes mockados não
comprovam chamadas AWS e o smoke curto não comprova dimensionamento sob carga.
O teste de proxy usa frontend/backend sintéticos; não valida o build real do
front-end. Este ensaio não sobe os cinco serviços do Compose AWS com awslogs,
IAM e IMDS reais: essa composição precisa ser validada na EC2.

### Por que há testes pulados

Na suíte geral, os 76 skips correspondem a:

- 35 testes PostgreSQL: executados posteriormente contra o contêiner db;
  os dois que alteram schema só executam no banco descartável exclusivo.
- 17 testes opt-in de infraestrutura: executados pelos alvos específicos de
  `infra-local-test`, que terminam com `[infra-local-test] ok`.
- 21 testes da CLI Make, 1 de Docker Compose e 1 de metadado Git: ferramentas
  e `.gitignore` não fazem parte da imagem API; verificados no checkout.
- 1 teste genérico de descoberta em `/api/products/1`: fixture sem produto
  retorna 404 e aciona um skip preexistente. Os testes próprios de detalhe de
  produto continuam passando; a explicação antiga do skip não prova ausência
  da funcionalidade. Ajuste desse teste de produto fica fora desta task.

Nenhum teste opt-in de infraestrutura ficou sem execução. Os warnings são
visíveis no log; não foram silenciados para obter aprovação. Ao concluir,
`docker compose ... stop` preservou o volume do banco e os demais volumes.
Não foi executado `infra-down`, `down -v`, prune ou remoção de dados existentes.

### Preparação da máquina e execução ARM64

Atualização posterior ao ensaio geral, usando o checkout `7a54462`. O responsável
instalou as ferramentas administrativas; depois foram verificados:

| Verificação | Resultado |
| --- | --- |
| Skopeo / Session Manager Plugin | 1.24.1 / 1.2.896.0 instalados |
| QEMU user static/binfmt | 11.1.2; registro host aarch64 habilitado, flags PF |
| Builder `vintex-arm64` | docker-container, BuildKit 0.33.1, suporte linux/arm64; padrão preservado |
| Build do Dockerfile backend | Concluído com Buildx/QEMU; imagem inspecionada linux/arm64 |
| Smoke backend ARM64 | aarch64, importação e `/health` 200 por FastAPI TestClient, sem rede externa |
| Manifesto FreeLLMAPI ARM64 | SHA-256 conferido com o digest fixado no runtime |
| FreeLLMAPI ARM64, 128 MiB | Exit 137 e OOMKilled=true |
| FreeLLMAPI ARM64, 512 MiB | `/api/ping` saudável, SQLite criado, OOMKilled=false |

Os testes FreeLLMAPI não usaram chave de provedor nem rede externa. O smoke do
backend usou configuração SQLite em memória, sem Uvicorn, conexão PostgreSQL,
migrations ou composição AWS completa; os testes anteriores de banco e E2E são
evidências separadas. Nenhum envio ao ECR ou túnel SSM real foi executado.
Contêineres/volumes temporários e a tag de teste backend foram removidos;
o builder dedicado e seu cache foram preservados.

O resultado com 512 MiB não estabelece o mínimo necessário nem o consumo nativo
da t4g.small. Este é um resultado histórico anterior à #291: o Compose foi
ajustado para 512 MiB após medir 256/384/512 MiB na #290. Consulte a
[evidência atual de memória e payload](./aws-staging-runtime.md#evidência-arm64-de-memória-e-payload-290).
O consumo nativo ainda precisa ser medido; o deploy exige todos os serviços saudáveis.
Os resultados acima substituem a limitação anterior `exec format error` e a
pendência de instalação das ferramentas nesta máquina.

### Decisão de prontidão

O código passou no ensaio local e está apto à revisão para iniciar o
provisionamento manual após o merge da #289. As ferramentas de publicação e
acesso estão preparadas nesta máquina. O destinatário do Budget foi informado
pelo responsável e configurado no arquivo administrativo local ignorado por
Git/Docker. Conta, bucket e lista de e-mails foram validados apenas em formato,
sem credenciais nem STS real; nenhum dado administrativo real é publicado aqui.

O FreeLLMAPI permanece hospedado na EC2 com cotas gratuitas dos provedores,
sem Premium, conforme o [roteiro de runtime](./aws-staging-runtime.md#parâmetros-e-ia).
A #291 integrou os ajustes de memória e parser de payload: 512 MiB e 40 MiB.
A compatibilidade com o Engine oficial do Amazon Linux usa o guard por bridge/IP
da API e das duas interfaces do worker; não exige `gw_priority`/Engine 28.
Memória nativa e inferência externa continuam
[pendências de aceite](./aws-staging-runtime.md#pendências-para-o-aceite-de-ia).

Após preparar os artefatos reais, o responsável confirma
conta/permissões e planos, executa a infraestrutura, preenche os cinco parâmetros
obrigatórios e publica o app. Chave de IA não bloqueia o primeiro deploy.
SSM/boot, IAM/SCP, logs AWS, persistência EBS, consumo de recursos e acesso ao
front real permanecem critérios de aceite operacional do primeiro deploy.

## Referências

- [SSM managed policy](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AmazonSSMManagedInstanceCore.html)
- [Confiança do Scheduler por grupo e conta](https://docs.aws.amazon.com/scheduler/latest/UserGuide/cross-service-confused-deputy-prevention.html)
- [Python no Amazon Linux 2023](https://docs.aws.amazon.com/linux/al2023/ug/python.html)
- [Docker Compose v5.6.0](https://github.com/docker/compose/releases/tag/v5.6.0)


## Compatibilidade do host e recuperação — 22/10/2026 (#288)

Complemento sobre a branch da #288 após o merge da #291 (`7a2c845`). Mantém
Amazon Linux 2023 ARM64, t4g.small, us-east-2 e os pacotes Docker fornecidos pela
AWS. O Compose não depende mais de `gw_priority`: o guard aceita somente os
pares bridge/IP da API e das duas interfaces do worker. Proxy, banco e
FreeLLMAPI continuam sem acesso a IMDS. Mínimos: Engine API 1.44 (Docker 25) e
Compose 2.30.0; bootstrap continua fixando Compose 5.6.0.

O deploy interrompe proxy/worker/API antes de atualizar o banco. A recuperação
cobre falhas parciais da parada, atualização do banco, migration, subida e
health check. Nenhum rollback faz downgrade do schema ou remove volumes.
Black passa a 26.10.1 para atender ao audit de segurança
([GHSA-cg8m-r9f2-5wm2](https://github.com/psf/black/security/advisories/GHSA-cg8m-r9f2-5wm2)).
Os limites ajustados na #291 permanecem: gateway 512 MiB, parser 40 MiB,
adaptador 8 MiB por imagem / 24 MiB no total.

| Verificação repetida neste complemento | Resultado |
| --- | --- |
| Ruff, Black, mypy, `make infra-qa` | Aprovados; Black 26.10.1 |
| `pip-audit` da imagem reconstruída | Nenhuma vulnerabilidade conhecida encontrada |
| Suíte geral com checkout montado | 589 aprovados / 76 pulados; cobertura 95% |
| Suíte geral na imagem do `infra-local-test` | 588 aprovados / 77 pulados; diferença: metadado Git ausente na imagem |
| CLI Make / Compose renderizado no checkout | 21 / 1 aprovados |
| Terraform fmt/validate/test local, bootstrap e staging | 6 + 3 + 19 planos mockados aprovados |
| Postgres migrado do Compose (`db:5432`) | Probe aprovado; 33 testes aprovados / 2 migrations puladas por segurança |
| Postgres descartável no mesmo contêiner db | 35 aprovados, incluindo as duas migrations; banco temporário removido |
| LocalStack / SQS / mídia / MiniStack / interoperabilidade | 2 / 2 / 3 / 3 / 3 aprovados |
| Worker e E2E HTTP → mídia → SQS → worker → banco | 5 aprovados; sucesso, falhas e retry/DLQ |
| Nginx real | SPA, prefixo API, 404, cache e rate limit aprovados |
| Guard IMDS no kernel | API/worker permitidos pelas interfaces previstas; proxy/db/gateway e bridge incorreta bloqueados; controle negativo aprovado |
| Engine 25.0.5/API 1.44 + Compose 5.6.0 | Cinco serviços sintéticos saudáveis, IPs fixos, `NET_RAW` removida e valor literal de env preservados |
| Build Docusaurus | Aprovado |

Os 76 skips da suíte com checkout são 35 PostgreSQL, 18 infra opt-in, 21 CLI
Make, 1 Compose CLI e 1 descoberta genérica sem fixture de produto. Os grupos
aplicáveis foram executados separadamente. A imagem adiciona um skip para o
metadado Git que só existe no checkout. Warnings preexistentes permanecem.

O smoke de compatibilidade usa daemon Docker 25 descartável, sem rede externa
nem socket do host. O teste renderiza os env files do runtime com valores sintéticos e preserva
redes, IPs, limites e capabilities, mas usa processos Alpine em AMD64 e logging
local. Isso comprova compatibilidade da API do Engine e da configuração; não
comprova a AMI/boot da AWS, o conjunto de aplicações ARM64 ou CloudWatch/IAM.
A medição ARM64/QEMU da #290 permanece histórica, descrita no
[guia de runtime](./aws-staging-runtime.md#evidência-arm64-de-memória-e-payload-290).

O aceite na EC2 continua manual: SSM/boot, IAM/SCP, logs reais, memória nativa
dos cinco serviços, persistência EBS e um job com provedor gratuito/token
configurados apenas na AWS. Nenhum apply/deploy AWS foi executado neste ensaio.
