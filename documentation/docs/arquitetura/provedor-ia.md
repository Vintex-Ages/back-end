---
sidebar_position: 2
---

# Provedor de IA

Fonte de verdade: [`app/services/ai/`](https://github.com/Vintex-Ages/back-end/tree/develop/app/services/ai) e `.ai/architecture.md` (VE-06, [#63](https://github.com/Vintex-Ages/back-end/issues/63)).

Toda feature de IA consome `AIProvider` / `get_ai_provider()` — nunca um SDK de IA diretamente. Isso existe para que trocar de provedor seja só registrar e apontar a config, sem tocar quem chama.

## Sem provedor configurado

Enquanto nenhum provedor real for escolhido, o provider ativo é `UnavailableAIProvider`. Ele levanta `AIProviderUnavailableError` — quem chama **degrada a funcionalidade**, nunca deixa isso virar um `500` sem tratamento. Ex.: cadastro manual de peça continua funcionando mesmo com a IA fora do ar; só o preenchimento automático fica indisponível.

## Onde isso importa

- [VE-05 (#62)](https://github.com/Vintex-Ages/back-end/issues/62) — pipeline assíncrono de ingestão de IA.
- [VE-07 (#65)](https://github.com/Vintex-Ages/back-end/issues/65) — observabilidade de IA.
- [VE-08 (#66)](https://github.com/Vintex-Ages/back-end/issues/66) — guardrails contra injeção.
- [VE-10 (#64)](https://github.com/Vintex-Ages/back-end/issues/64) — suíte de avaliação da IA.

Essas issues estão em hold nesta sprint (S2) — o foco atual é a infraestrutura de teste local. Ver [Infraestrutura de teste local](../infraestrutura/teste-local).
