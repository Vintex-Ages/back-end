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
Ela não é incluída no repositório, na imagem ou nos testes. O Compose local
mantém a chave vazia; testes substituem o provedor por doubles.

Configuração do worker e do produtor:

| Variável | Uso |
| --- | --- |
| `AI_ANALYSIS_QUEUE_URL` | URL da fila principal SQS |
| `SQS_ENDPOINT_URL` | Endpoint opcional do LocalStack; vazio usa AWS |
| `AI_WORKER_PROVIDER` | `freellmapi` na AWS; `unavailable` por padrão local |
| `FREELLMAPI_BASE_URL` | Endpoint interno OpenAI compatível |
| `FREELLMAPI_API_KEY` | Token unificado, fornecido apenas pela AWS |
| `FREELLMAPI_MODEL` | Modelo configurado no FreeLLMAPI; padrão `auto` |

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
