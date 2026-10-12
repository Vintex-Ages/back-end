---
sidebar_position: 5
---

# Mensageria de análise de imagens (VE-17)

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
não inclui resultado da análise ou credenciais. O worker previsto na
[VE-18 (#169)](https://github.com/Vintex-Ages/back-end/issues/169) consumirá
esse contrato e deverá confirmar a mensagem somente após concluir o
processamento. A integração do pipeline da API com SQS e o container worker
ficam nessa issue seguinte.

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
make infra-down
```

Os testes integrados também são executados por `make infra-local-test` e
`make infra-complete`.
