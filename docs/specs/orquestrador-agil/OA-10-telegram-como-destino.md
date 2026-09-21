# OA-10 — Telegram como destino de aviso

**Prioridade:** P1 · **Depende de:** nada · **Bloqueia:** OA-11, OA-12

## Por que existe

A esteira roda sozinha, muitas vezes num servidor sem tela. Hoje o aviso tem três destinos
(`clickup`, `macos`, `webhook`) escolhidos por `ORQ_AVISO_DESTINO`
([bin/orq-avisar:23](../../../bin/orq-avisar:23)). Nenhum deles chega ao bolso de quem
precisa decidir. O Telegram passa a ser o canal padrão de todos os avisos do orquestrador —
decisão de 21/09/2026.

Esta unidade entrega **o canal**. O que é avisado e o que é deliberadamente calado está em
OA-11, e as duas podem ser feitas em paralelo até o ponto de integração.

## Escopo

**Dentro:** um destino `telegram` em `bin/orq-avisar`, as credenciais, o formato da
mensagem, e o comportamento diante de falha.

**Fora:** quais eventos disparam aviso (OA-11); notificação de sessão pedindo decisão —
essa continua chegando pelo app do Claude e **não** entra aqui.

## Desenho

### Credenciais

Em `~/.config/orquestrador/credenciais.env`, junto do token do ClickUp, com permissão 600 e
fora de qualquer repositório — a mesma regra que o instalador já impõe:

```
TELEGRAM_BOT_TOKEN=123456:AA...
TELEGRAM_CHAT_ID=-1001234567890
```

O arquivo de exemplo (`modelos/credenciais.env.exemplo`) ganha as duas linhas comentadas,
com a instrução de como obter cada uma: falar com o `@BotFather` para o token, e ler
`getUpdates` para descobrir o id da conversa.

### A entrega

`POST https://api.telegram.org/bot<TOKEN>/sendMessage`, com `chat_id`, `text` e
`parse_mode=HTML` — HTML em vez de Markdown porque nome de branch com `_` quebra o
analisador de Markdown do Telegram e a mensagem volta com erro 400 em vez de chegar.
Timeout de 20s, como os outros destinos.

Formato:

```
<b>▶ FE-03 iniciada</b>
Implementar o seletor de período no painel
esteira: front-end · máquina: vps-orq
https://app.clickup.com/t/868abc
```

Quatro linhas no máximo: título, o que é, de onde veio, e o link que leva ao resto. Aviso
que não cabe na tela de bloqueio não é aviso.

### As duas regras que este arquivo não pode quebrar

Continuam valendo, e agora também para o Telegram:

1. **Nunca derrubar quem chamou.** Sai 0 sempre. O laço chama isto em pontos terminais e o
   Claude Code trata saída != 0 de gancho como erro do turno.
2. **O registro em arquivo acontece antes da entrega.** `avisos.log` é o canal que sempre
   existe; Telegram é entrega, e entrega falha.

`ORQ_AVISO_DESTINO=telegram` passa a ser o padrão de instalação quando as duas credenciais
existirem; sem elas, o comportamento de hoje continua valendo e o pré-voo (OA-12) diz que o
canal não está configurado, em vez de falhar em silêncio.

### Prova de entrega

`orq-avisar --testar` manda uma mensagem de teste e **confere a resposta da API** — `ok:
true` e o `message_id`. Acreditar no código HTTP não basta: o aprendizado nº 17 é
exatamente sobre API que responde sucesso e não faz nada.

## Critérios de aceite

| Critério | Como provar |
| --- | --- |
| Mensagem chega | `orq-avisar --testar` → a conversa recebe, e a saída imprime o `message_id` devolvido |
| Credencial ausente não quebra nada | Remover as variáveis → `orq-avisar "t" "m"` sai 0, grava em `avisos.log`, diz que o canal não está configurado |
| API fora do ar não derruba o chamador | Apontar para host inalcançável → sai 0 em ≤ 20s |
| Caractere especial não quebra a mensagem | Título com `_`, `<`, `&` e emoji → chega legível |
| A credencial não vaza para o rastro | `grep TELEGRAM ~/.claude/orchestrator/state/avisos.log` → vazio |
| A sessão não lê a credencial | A cerca barra leitura de `~/.config/orquestrador` (OA-06) |

## Riscos

- **Token de bot no `getUpdates` expõe o histórico do chat** para quem tiver o token. Por
  isso ele mora no mesmo lugar e com a mesma permissão do token do ClickUp, e a cerca o
  protege da própria sessão.
- **Telegram pode estar bloqueado na rede do host.** O registro em arquivo continua sendo a
  garantia; o pré-voo prova a entrega de verdade, uma vez, em vez de deixar descobrir no
  primeiro bloqueio de madrugada.
