---
sidebar_position: 5
---

# Mensageria e worker de análise de imagens (VE-17/VE-18)

A infra local cria a fila standard `vintex-local-image-analysis` e a DLQ
`vintex-local-image-analysis-dlq` no LocalStack do Compose. A fila principal
redireciona mensagens após três entregas sem confirmação. `make infra-up`
provisiona as filas; `make test-sqs` verifica configuração, envio e consumo
contra o mesmo container LocalStack, acessado pelo alias
`http://localstack:4566`.

## Contrato da mensagem

O corpo é um JSON UTF-8 com o identificador da peça e as URLs de imagens:

```json
{
  "product_id": 123,
  "image_urls": ["https://images.example.test/product-123.jpg"]
}
```

Esse formato acompanha os argumentos de análise usados pelo pipeline atual da
[VE-05 (#62)](https://github.com/Vintex-Ages/back-end/issues/62). A mensagem
não inclui resultado da análise ou credenciais. Ao criar um rascunho com fotos,
a API persiste a peça como `pending` e publica essa mensagem após o commit.
Falha ao publicar mantém o cadastro e registra o estado `failed`.

O worker consome uma mensagem por vez, atualiza `Product.ai_status` para
`processing` e persiste as sugestões em `ai_suggestions` ao concluir. A fila só
é confirmada depois da persistência. Erros deixam a mensagem sem confirmação
para retry e redrive à DLQ; peça já concluída é ignorada em entregas duplicadas.
Peça inexistente é terminal e pode ser confirmada. O resultado continua
consultável pela rota de status de IA da peça.

## Provedor FreeLLMAPI

O worker usa o endpoint OpenAI compatível interno
`http://freellmapi:3001/v1/chat/completions`. As URLs das imagens são baixadas
no worker e enviadas ao gateway como dados inline, para não encaminhar URLs
pré-assinadas ao provedor. O serviço FreeLLMAPI não publica porta no host.

Em AWS, `FREELLMAPI_API_KEY` é injetada pelo deploy a partir do Parameter Store.
Ela não é incluída no repositório, na imagem ou nos testes automatizados.
Para testes manuais locais, o Compose lê `FREELLMAPI_API_KEY` do arquivo
ignorado `infra/vintex-infra/.env` (`${FREELLMAPI_API_KEY:-}`); sem valor,
continua vazio. Configure também `AI_WORKER_PROVIDER=freellmapi` e um
`FREELLMAPI_BASE_URL` acessível pela rede Docker. O gateway não é iniciado
por esta tarefa: o runtime de cinco serviços pertence à [#273](https://github.com/Vintex-Ages/back-end/issues/273).

Configuração do worker e do produtor:

| Variável | Uso |
| --- | --- |
| `AI_ANALYSIS_QUEUE_URL` | URL da fila principal SQS |
| `SQS_ENDPOINT_URL` | Endpoint opcional do LocalStack; vazio usa AWS |
| `AI_WORKER_PROVIDER` | `freellmapi` na AWS; `unavailable` por padrão local |
| `FREELLMAPI_BASE_URL` | Endpoint interno OpenAI compatível |
| `FREELLMAPI_API_KEY` | Token unificado: `.env` ignorado localmente; Parameter Store na AWS |
| `FREELLMAPI_MODEL` | Modelo configurado no FreeLLMAPI; padrão `auto` |
| `PUBLIC_BASE_URL` | Origem pública da API usada nas URLs de mídia |
| `MEDIA_INTERNAL_BASE_URL` | Origem da API para baixar mídia própria dentro da rede Docker |

O navegador continua recebendo URLs públicas. Somente durante o download pelo
Google ou FreeLLMAPI, URLs da origem configurada em `PUBLIC_BASE_URL`, com
caminho `/api/media/`, são resolvidas contra `MEDIA_INTERNAL_BASE_URL`.
As duas bases devem conter apenas esquema e origem, sem caminhos ou query.
No Compose, a base interna é `http://api:8000`; a pública usa
`http://localhost:8001` por padrão. Ajuste `PUBLIC_BASE_URL` ao alterar a porta
do host. URLs externas não são reescritas. Isso conecta o storage da #167 ao
worker e ao futuro acesso por túnel SSM da staging (#273).

O Compose de teste mantém o worker no perfil opt-in `ai-worker`, sem porta
publicada. A configuração do serviço FreeLLMAPI no Compose de deploy pertence
à tarefa de composição de runtime.

## Retry e DLQ

Falhas de processamento deixam a mensagem sem confirmação para que ela volte
a ficar disponível depois do visibility timeout do SQS. Após três entregas, o
redrive envia a mensagem à DLQ para inspeção ou reprocessamento controlado.
Terraform declara a mesma fila, DLQ e redrive policy; os testes Terraform são
mockados. Não execute `terraform apply`: o ambiente local provisiona as filas
diretamente no LocalStack pelo script da infra.

```bash
make infra-up
make test-sqs
make test-ai-worker
make infra-down
```

Os testes integrados também são executados por `make infra-local-test` e
`make infra-complete`.

`make test-ai-worker` executa um teste de polling e três cenários E2E:
sucesso com entrega duplicada, resposta HTTP 503 do provedor e ausência de
chave. Cada cenário inicia API e worker em processos separados no Docker,
usa o Postgres migrado do Compose e filas temporárias no LocalStack, faz
upload/leitura no S3 e consulta a persistência pela API. Só a resposta HTTP
externa é sintética; não há inferência real nem acesso à AWS. Nos erros, três
entregas levam à DLQ, enquanto health e cadastro manual continuam funcionando.
Os tempos de polling/visibilidade são reduzidos apenas no harness de teste.
Filas, objetos e registros sintéticos são removidos ao final.
