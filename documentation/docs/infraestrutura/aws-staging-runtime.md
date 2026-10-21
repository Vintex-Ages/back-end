---
sidebar_position: 6
---

# Runtime e deploy manual da staging (#273)

Esta entrega depende de #168/#169 e da base #272. O host e seus recursos AWS
são definidos na [#274](./aws-staging.md). **Não há deploy nem recursos AWS criados nesta entrega.**
O responsável realiza o primeiro deploy manualmente com o perfil AWS autorizado na subconta institucional;
na EC2 os comandos utilizam a role da instância. O pipeline futuro pertence ao
vintex-prod e não é implementado aqui.

## Runtime

`infra/aws/staging/compose.yml` exige Docker Compose >=2.30 (env_file raw), ARM64
e cinco serviços. API/worker usam o mesmo SHA completo no ECR. Imagens públicas
estão fixadas por versão e digest; não há build na instância.

| Serviço | Memória | Rede/IP | Função |
| --- | ---: | --- | --- |
| Nginx 1.28.0 Alpine | 64 MiB | app / 172.30.73.2 | Front estático, proxy API e rate limit |
| API | 384 MiB | app / 172.30.73.3 | Aplicação existente, S3 e produtor SQS |
| Worker | 256 MiB | app / 172.30.73.4; llm / 172.30.74.2 | Consumidor `app.workers.ai_analysis` existente |
| FreeLLMAPI v0.14.2 | 128 MiB | llm / 172.30.74.3 | Imagem oficial espelhada no ECR |
| pgvector 0.8.1 / PostgreSQL 16 | 448 MiB | app / 172.30.73.5 | Banco local do Compose, dados persistentes no EBS |

As redes são exclusivas deste runtime, com bridges `br-vintex-app` e
`br-vintex-llm`. API não participa de llm; FreeLLMAPI não participa de app.
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

- EC2 ARM64 com SSM, Docker Compose >=2.30, Python 3 e boto3 para o script host,
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

FreeLLMAPI recebe ENCRYPTION_KEY e FREEAPI_CONFIG_JSON para criar o administrador
no primeiro boot; alterações posteriores da senha requerem o procedimento do
dashboard. Seu SQLite persiste em volume próprio. Nunca trocar a chave de
criptografia com SQLite existente. Nunca usar chaves/contas de produção na staging.
Não existe auto-update nem Watchtower.

## Build e envio manual (máquina do responsável)

Após selecionar o perfil AWS e executar `make infra-deploy staging`, usar os
URLs ECR dos outputs. O comando conduz o bucket e a infraestrutura completa;
não existe aplicação separada de shared. Exemplo
com valores públicos fictícios, substituindo conta e SHA pelo release aprovado:

```bash
export AWS_PROFILE=vintex-terraform
aws sts get-caller-identity
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

Antes de publicar artefatos, conferir na máquina do responsável:

```bash
docker buildx inspect
skopeo --version
session-manager-plugin --version
```

O builder precisa listar `linux/arm64`; possuir Buildx em um host x86 não
garante emulação ARM64. Sem esse suporte, preparar QEMU ou um builder ARM64
antes do build. Skopeo é usado pelo espelhamento abaixo e o Session Manager
Plugin pelo acesso/túnel SSM. São pré-requisitos da publicação e do acesso;
não são instalados pelo Terraform no computador do responsável.

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
aws ssm start-session --profile vintex-terraform --region us-east-2 --target <INSTANCE_ID> \
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
sintético; não acessa IMDS real nem instala regras no host.

Referências: [FreeLLMAPI v0.14.2](https://github.com/tashfeenahmed/freellmapi/tree/v0.14.2),
[IMDS](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html),
[Docker e iptables](https://docs.docker.com/engine/network/firewall-iptables/).
