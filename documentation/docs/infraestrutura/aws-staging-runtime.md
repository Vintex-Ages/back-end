---
sidebar_position: 6
---

# Runtime e deploy manual da staging (#273)

Esta entrega depende de #168/#169 e da base #272. O host e seus recursos AWS
são definidos na [#274](./aws-staging.md). **Não há deploy nem recursos AWS criados nesta entrega.**
O responsável realiza o primeiro deploy manualmente com sessão temporária SSO;
na EC2 os comandos utilizam a role da instância. O pipeline futuro pertence ao
vintex-prod e não é implementado aqui.

## Runtime

`infra/aws/staging/compose.yml` exige Docker Engine API >=1.48 e Compose >=2.33.1
(env_file raw e gw_priority), ARM64
e cinco serviços. API/worker usam o mesmo SHA completo no ECR. Imagens públicas
estão fixadas por versão e digest; não há build na instância.

| Serviço | Memória | Rede/IP | Função |
| --- | ---: | --- | --- |
| Nginx 1.28.0 Alpine | 64 MiB | app / 172.30.73.2 | Front estático, proxy API e rate limit |
| API | 384 MiB | app / 172.30.73.3 | Aplicação existente, S3 e produtor SQS |
| Worker | 256 MiB | app / 172.30.73.4; llm / 172.30.74.2 | Consumidor `app.workers.ai_analysis` existente |
| FreeLLMAPI v0.14.2 | 512 MiB | llm / 172.30.74.3 | Imagem oficial espelhada no ECR; ajuste medido na #290 |
| pgvector 0.8.1 / PostgreSQL 16 | 448 MiB | app / 172.30.73.5 | Banco local do Compose, dados persistentes no EBS |

As redes são exclusivas deste runtime, com bridges `br-vintex-app` e
`br-vintex-llm`. API não participa de llm; FreeLLMAPI não participa de app.
O worker fixa `gw_priority: 1` em `app`: tráfego externo e IMDS saem pelo IP
172.30.73.4, permitido no firewall. A interface llm continua acessível para o
gateway, mas não recebe permissão de acesso aos metadados. `priority` não
substitui `gw_priority`.
Nenhuma aplicação usa host networking, modo privilegiado ou socket Docker.
NET_RAW é removida dos cinco serviços para impedir falsificação de origem.
API e banco não publicam portas. Proxy e dashboard publicam somente
`127.0.0.1:80` e `127.0.0.1:3001`, acessíveis por SSM. O SG da #274 não tem ingress.

Nginx mantém `/api` na URL upstream e os 404 da API; só rotas da SPA têm fallback
para index.html. Limite: 10 requisições/s por IP, burst 20, excedentes retornam
429; upload máximo 25 MiB; timeout API 30 s; SSE sem buffering. Não há header de
origem obrigatório. Com SSM, usuários compartilham o IP do túnel no rate limit.
index.html é servido sem cache. HTTPS externo não faz parte desta staging
privada: o transporte até a instância usa o túnel autenticado/criptografado SSM.

## Recursos fornecidos pela #274

- EC2 ARM64 com SSM, Docker Engine API >=1.48, Compose >=2.33.1, Python 3 e boto3 para o script host,
  iptables/ip6tables com backend compatível, 1 GiB de swap e disco para imagens.
- IMDSv2 obrigatório, hop limit **2** para API/worker em bridge; IPv6 de IMDS
  desativado; nenhuma entrada de rede.
- Role de staging: SSM; ECR pull/autenticação; S3 mídia; SQS send/receive/delete/
  change visibility/GetQueueAttributes; leitura/decriptação de
  `/vintex/staging/*`; escrita nos grupos de log abaixo. Nenhum recurso prod.
- Bucket mídia staging, fila staging com DLQ (3 tentativas; visibilidade 180 s),
  Parameter Store e grupos `/vintex/staging/{proxy,api,worker,freellmapi,db}`, com
  retenção de 7 dias. O Compose não cria grupos automaticamente.

O script recusa outra conta, fila fora de Ohio e credenciais de operador na EC2:
SDK deve usar `iam-role`. Não existe backup de produção nem restauração na staging.
Antes de ler parâmetros ou alterar serviços, verifica as versões do Engine e
Compose. Em caso de incompatibilidade, informa os mínimos e orienta atualizar as
ferramentas e repetir o mesmo comando de deploy. O bootstrap fixa Compose 5.6.0;
a versão do Engine depende do pacote Docker instalado no Amazon Linux.
Somente dados sintéticos. Seeds e limites de IA de produto seguem suas próprias
features; esta task não inventa cotas ainda não implementadas no backend.

## Parâmetros e IA

Cadastrar via console, sem valores em Git, histórico de shell ou logs:

| Caminho em `/vintex/staging/` | Tipo / conteúdo |
| --- | --- |
| `db_password` | SecureString, mínimo 16 caracteres |
| `jwt_secret` | SecureString, mínimo 32 caracteres |
| `llm_encryption_key` | SecureString, 64 dígitos hexadecimais, estável |
| `llm_admin_email` | SecureString, e-mail do administrador do dashboard |
| `llm_admin_password` | SecureString, senha forte do administrador |
| `llm_api_key` | SecureString, token unificado criado no dashboard; opcional no primeiro deploy |

O script gera quatro env files raw, separados por serviço, com modo 0600 em
diretórios root 0700. A URL PostgreSQL usa **db:5432**, com senha percent-encoded;
nenhum endpoint de emulador é utilizado. APP_ENV=production ativa a proteção JWT
existente também na staging; APP_DEBUG=false impede logs SQL com valores.
AI_PROVIDER=unavailable mantém embedding, chat e sugestões síncronas de IA degradados; worker usa
FreeLLMAPI. O deploy ignora parâmetros provisórios da #274; os obrigatórios impedem o deploy até serem preenchidos. Sem token, o adaptador existente registra falha e a mensagem segue
retry/DLQ, sem derrubar a API. Nenhum health check invoca inferência.

O arquivo `llm.env` também recebe `REQUEST_BODY_LIMIT_MB=40`. O adaptador aceita
8 MiB por imagem e 24 MiB no total; base64 transforma o total em aproximadamente
32 MiB, além do JSON. Os 25 MiB padrão do gateway rejeitariam esse pedido com
413 antes da normalização das imagens. Esse tráfego é interno entre worker e
gateway; o limite de upload do Nginx permanece independente. Aumentar o parser
não altera os limites do adaptador nem as cotas dos provedores.

FreeLLMAPI recebe ENCRYPTION_KEY e FREEAPI_CONFIG_JSON para criar o administrador
no primeiro boot; alterações posteriores da senha requerem o procedimento do
dashboard. Seu SQLite persiste em volume próprio. Nunca trocar a chave de
criptografia com SQLite existente. Nunca usar chaves/contas de produção na staging.
Não existe auto-update nem Watchtower.

## Build e envio manual (máquina do responsável)

Após preparar SSO/state e aplicar #272, usar os URLs ECR dos outputs. Exemplo
com valores públicos fictícios, substituindo conta e SHA pelo release aprovado:

```bash
aws sso login --profile vintex
export AWS_PROFILE=vintex
export AWS_REGION=us-east-2
export VINTEX_ACCOUNT_ID=123456789012
export VINTEX_SHA=0000000000000000000000000000000000000000
export VINTEX_ECR="$VINTEX_ACCOUNT_ID.dkr.ecr.us-east-2.amazonaws.com"
aws sts get-caller-identity
aws ecr get-login-password --region us-east-2 | docker login --username AWS --password-stdin "$VINTEX_ECR"
docker buildx build --platform linux/arm64 --tag "$VINTEX_ECR/vintex-backend:$VINTEX_SHA" --push .
```

Fazer o build a partir do checkout do SHA informado; não usar tags mutáveis.
Em host x86, preparar previamente Buildx/QEMU para ARM64. Verificar o scan ECR
e o manifesto ARM64 antes de implantar.

Espelhar o manifesto ARM64 oficial FreeLLMAPI v0.14.2 preservando o digest, com
Skopeo instalado. Credenciais do espelho são temporárias; nunca adicionar ao Git:

```bash
aws ecr get-login-password --region us-east-2 | skopeo login --username AWS --password-stdin "$VINTEX_ECR"
skopeo copy --override-os linux --override-arch arm64 --preserve-digests \
  docker://ghcr.io/tashfeenahmed/freellmapi@sha256:1942b1437628deb70699d7371dab3cb7e65c296c4e1db345218b4de2102149eb \
  "docker://$VINTEX_ECR/freellmapi:v0.14.2"
aws ecr describe-images --repository-name freellmapi --image-ids imageTag=v0.14.2 --query 'imageDetails[0].imageDigest'
```

O digest retornado deve ser o mesmo fixado no comando/script. O deploy usa digest,
não a tag do espelho. Nginx e pgvector também têm manifestos ARM64 verificados.

Front: fornecer manualmente o build estático aprovado, configurado com
`VITE_API_BASE_URL=/api`. A task não modifica o repo front-end. Empacotar o build
como `frontend/` com index.html, mais `infra/aws/staging/` e
`scripts/infra/deploy_staging.py` do release aprovado. Transferir pelo procedimento
administrativo SSM da conta (por exemplo upload temporário a S3 pela sessão
humana e download por URL pré-assinada dentro da sessão; não imprimir a URL).
O bucket de mídia staging pode receber esse artefato temporário sob prefixo
administrativo, removido depois. Não requer bucket de releases/pipeline agora.

## Preparação e deploy na EC2

Extrair cada release numa pasta **nova**, root, em `/opt/vintex/releases/<SHA>`;
diretórios do frontend 0755 e arquivos estáticos 0644. Não sobrescrever releases
anteriores: rollback reutiliza configuração e frontend originais.

Antes do primeiro contêiner, instalar o guard com root:

```bash
sudo bash /opt/vintex/releases/<SHA>/infra/aws/staging/install-guard.sh
```

O serviço aplica regras raw/PREROUTING antes de Docker iniciar, inclusive após
reboot. A dependência Docker → guard impede startup quando o guard falha.
Reaplicar é idempotente; backend Docker nftables nativo não está suportado.
Não limpar regras de firewall com runtime ativo; reaplicar guard após manutenção.
O deploy exige serviço ativo e reaplica as regras antes de subir serviços.

Copiar config.json.example para arquivo administrativo root 0600 fora do Git,
preenchendo outputs de #274, SHA e paths. Instalar boto3 no ambiente Python host
(venv recomendado, mesma versão do requirements do release) e executar:

```bash
sudo /opt/vintex/deploy-venv/bin/python /opt/vintex/releases/<SHA>/scripts/infra/deploy_staging.py --config /etc/vintex/staging.json
```

O host usa a role EC2; não exportar AWS_PROFILE/access keys. O script autentica
Docker no ECR sem imprimir senha. Deploys simultâneos são recusados por flock.

1. Valida conta/config/IMDS, lê SSM e gera env files privados.
2. Valida Compose, baixa imagens e confirma ARM64.
3. Espera banco saudável e interrompe proxy/worker/API.
4. Sobe API sem proxy para executar `alembic upgrade head` no container do release,
   usando IP fixo permitido pelo guard. Nenhum tráfego externo chega durante isso.
5. Sobe os cinco serviços e espera seus health checks; consulta /health até 10 vezes.
6. Sucesso: grava current.json, previous.json e remove somente tags SHA antigas do
   ECR backend local, mantendo atual/anterior e imagens ainda em uso.
7. Falha: reativa Compose/frontend/env anteriores e verifica saúde; nunca faz
   downgrade do schema. No primeiro deploy falho, para aplicação e mantém banco.

Migrations devem seguir expand/contract, compatíveis com a imagem anterior.
Rollback de imagem **não desfaz schema**. Volumes nunca são apagados pelo script;
rotação de senha de banco é recusada e exige operação manual de SQL/configuração.
Env files de tentativas ficam protegidos para diagnóstico; limpar tentativas
antigas manualmente após review, preservando paths apontados por current/previous.
Logs capturados de comandos não são impressos para evitar exposição de segredos.
Usar CloudWatch e comandos administrativos sem dump de env para diagnóstico.

## Acesso e validação manual após #274

```bash
aws ssm start-session --profile vintex --region us-east-2 --target <INSTANCE_ID> \
  --document-name AWS-StartPortForwardingSession \
  --parameters '{"portNumber":["80"],"localPortNumber":["8080"]}'
```

Acessar http://localhost:8080 e /health; o frontend usa /api no mesmo domínio.
Para o dashboard, outra sessão com portNumber 3001/localPortNumber 3001.
Cadastrar provedores staging, gerar token unificado, gravar `llm_api_key` no
Parameter Store e reexecutar deploy para atualizar worker.

Health worker verifica processo, banco e acesso à fila; não prova inferência nem
processamento de um job. Validar separadamente upload/leitura de mídia, job
sintético, retry/DLQ, logs e persistência após restart. A role e IMDSv2 reais
só podem ser comprovados na EC2: token/credenciais devem ser alcançáveis em
API/worker e inacessíveis em proxy/db/FreeLLMAPI. Não imprimir credenciais.

## Testes sem AWS

- Pytest cobre parâmetros, proteção de arquivos, Compose renderizado, migrations,
  sucesso/falha, rollback e limpeza seletiva. Compose CLI ausente pula apenas sua
  validação; no CI Ubuntu e na validação local ela está disponível.
- Nginx testado localmente com backend HTTP sintético (SPA, /api, 404 e rate limit).
- Teste kernel IMDS em contêiner descartável sem rede externa. `--privileged` é
  usado **apenas neste teste**, para namespaces/firewall internos; não no runtime:

```bash
docker build -f tests/staging/Dockerfile.imds -t vintex-staging-imds:test .
docker run --rm --privileged --network none vintex-staging-imds:test
```

O teste permite API/worker e bloqueia proxy/db/FreeLLMAPI contra servidor metadata
sintético; o worker tem as duas interfaces e o teste também força uma rota pela
llm para confirmar seu bloqueio. Não acessa IMDS real nem instala regras no host.

### Evidência ARM64 de memória e payload (#290)

O limite original de 128 MiB falhou no ensaio ARM64 sob QEMU. Antes de aumentar
o dimensionamento, foram medidos os candidatos de 256/384 MiB. Como nenhum
atendeu à margem de 20%, o ensaio foi estendido a 512 MiB:

| Limite | Resultado no host x86_64 com QEMU |
| --- | --- |
| 256 MiB | OOM na inicialização, exit 137 |
| 384 MiB | Login, payload de 33.554.711 bytes e parser funcionando; pico 384 MiB, margem insuficiente |
| 512 MiB | Mesmo payload, três requisições sequenciais, rejeição acima de 40 MiB e health saudável; pico 372,41 MiB, sem OOM |

O Compose passa a 512 MiB para o gateway. A soma dos limites dos cinco serviços
é **1.664 MiB**, deixando **384 MiB nominais** dos 2 GiB da t4g.small para host e
agentes. Limites são tetos, não reservas; essa conta não comprova memória
disponível nem o consumo nativo da EC2. Nenhuma instância maior foi configurada.

Reproduzir em Linux com Docker, acesso ao GHCR e suporte ARM64 (QEMU somente
quando o host for x86_64), com boto3 instalado conforme o runbook:

```bash
python -m scripts.infra.test_staging_llm
```

O comando testa 256, 384 e 512 MiB e retorna sucesso se algum candidato passar
sem OOM e com pico abaixo de 80% do teto. Usa cgroup v2 (`memory.peak`), rede
Docker interna sem saída, administrador/token sintéticos, SQLite descartável e
health check igual ao Compose. Não usa AWS nem chaves de provedores. Desabilita
swap **no contêiner de ensaio**, para não mascarar pressão de memória. Remove
contêiner, volumes anônimos e rede ao terminar.

O retorno 503 sem provedor comprova que autenticação e parser aceitaram o pedido;
**não comprova inferência ou qualidade da análise**. O ensaio usa PNGs sintéticos
preenchidos até 8 MiB, sem representar todas as dimensões/formatos de fotos reais.

O ensaio conjunto dos cinco serviços ARM64 também passou com PostgreSQL/pgvector
do próprio Compose, migrations até head, frontend sintético e SQS/S3 no LocalStack.
Foram usados overrides **somente de teste**: logs locais em vez de awslogs,
credenciais sintéticas, nomes/volumes descartáveis e health timeout do worker de
60 s em vez de 10 s. Sob QEMU, esse check demorou aproximadamente 17–20 s. O
timeout de produção permanece em 10 s e precisa ser confirmado no ARM64 nativo.
Para evitar conflito entre plataformas no armazenamento clássico do Docker,
o ensaio usou o manifesto ARM64 filho do índice Nginx fixado; mesma versão/binário.

| Serviço | Pico cgroup no smoke conjunto (MiB) | Resultado |
| --- | ---: | --- |
| Nginx | 62,65 / 64 | Saudável, sem OOM |
| API | 254,60 / 384 | Saudável, sem OOM |
| Worker | 256,00 / 256 | Saudável, sem OOM; teto atingido, investigar no host nativo |
| FreeLLMAPI | 344,64 / 512 | Saudável, sem OOM |
| PostgreSQL | 153,71 / 448 | Saudável, sem OOM |

Esses picos incluem cache e processos de health check e não ocorreram
necessariamente ao mesmo tempo. Não são uma medição de `MemAvailable` da EC2.
Separadamente, quatro cenários E2E com o código Python 3.12 em AMD64, banco ARM64
e emuladores locais passaram: sucesso, erro do provedor, HTTP 413 e chave ausente.
Os casos de falha preservaram a API, fizeram retry e chegaram à DLQ. O resultado
do provedor nesses testes é sintético; eles não aprovam inferência externa.

Na primeira EC2, validar os cinco serviços simultaneamente, com um job real e
health checks ativos; registrar pico do gateway abaixo de 80%, ausência de OOM e
pelo menos 384 MiB de `MemAvailable` no host durante o ensaio. Incluir o pico do
worker ao serializar as imagens. Essa validação nativa permanece pendente até o
deploy manual; o resultado em QEMU não a substitui.

Referências: [FreeLLMAPI v0.14.2](https://github.com/tashfeenahmed/freellmapi/tree/v0.14.2),
[IMDS](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html),
[Docker e iptables](https://docs.docker.com/engine/network/firewall-iptables/),
[Compose gw_priority](https://docs.docker.com/reference/compose-file/services/#gw_priority),
[Engine API GwPriority](https://docs.docker.com/reference/api/engine/version-history/#v148-api-changes).
