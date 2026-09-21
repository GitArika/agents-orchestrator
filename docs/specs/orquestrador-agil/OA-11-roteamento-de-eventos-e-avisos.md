# OA-11 — Roteamento de eventos: o que avisa e o que cala

**Prioridade:** P0 · **Depende de:** OA-03, OA-08, OA-10 · **Bloqueia:** OA-13

## Por que existe

O requisito nomeia três avisos obrigatórios (tarefa iniciada, PR aberto, tarefa bloqueada) e
**um silêncio obrigatório**: sessão pedindo decisão ou permissão não avisa, porque isso já
chega pelo app do Claude — as sessões sobem com `--remote-control` e `permission-mode auto`.
Avisar de novo produziria dois toques para o mesmo fato, e o segundo ensina a ignorar os
dois.

O silêncio é a parte difícil, porque hoje existe um caminho que faz exatamente isso: o
gancho `Notification` de [hooks/notificar.sh:28](../../../hooks/notificar.sh:28) dispara
"⚠️ <unidade> precisa de você" a cada vez que a sessão aguarda uma decisão, e entrega pelo
mesmo `orq-avisar` que vai ganhar o Telegram em OA-10. Sem esta unidade, ligar o Telegram
liga junto o aviso que o requisito manda calar.

## Escopo

**Dentro:** a origem única dos eventos, o roteamento, e a separação entre o que é do motor
e o que é do gancho de sessão.

**Fora:** o canal em si (OA-10).

## Desenho

### Uma origem só: a transição de estado

Todo aviso do orquestrador nasce de uma linha gravada em `evento` (OA-01), na mesma
transação da mudança de status. Não existe `notify()` espalhado pelos comandos: quem grava a
transição emite o aviso. É o que garante que aviso e estado nunca discordem — e é o que
torna os três avisos do requisito consequência do desenho, não de três chamadas lembradas.

| Evento | Transição que o gera | Telegram |
| --- | --- | --- |
| `despachada` | `backlog → em_progresso` | **sim** — "tarefa iniciada por um agente" |
| `pr_aberto` | `em_progresso → revisao` | **sim** — "PR aberto por um agente" |
| `bloqueada` | `* → bloqueado` | **sim** — com o motivo |
| `pr_fundido` | `revisao → pronto` | sim |
| `retrabalho` | `revisao → em_progresso` | sim |
| `recolhida` | `em_progresso → backlog` | sim |
| `espelho_falhou`, `vigia_falhou`, `teardown_falhou` | — | sim |
| `laco_parou`, `esteira_concluida` | — | sim |
| `declaracao` | verbos de OA-02 | não — é ato humano, quem digitou já sabe |

Decisão de 21/09/2026: "tudo que hoje é `notify()`" vai para o Telegram. A tabela acima é
mais larga que os três do requisito, de propósito — falha operacional silenciosa num
servidor é o que já matou laço sem ninguém notar.

### O que **não** vai

| Caminho | Destino |
| --- | --- |
| Gancho `Notification` (sessão aguardando decisão/permissão) | só `avisos.log` e o app do Claude |
| Gancho `Stop` (sessão encerrou o turno) | só `avisos.log` |

Implementação: `hooks/notificar.sh` passa a chamar o entregador com `ORQ_AVISO_DESTINO=`
vazio — ou, melhor, com `--canal local`, explícito, para que ninguém reintroduza o
comportamento por engano ao mexer no padrão de destino. O caso de teste correspondente é
obrigatório: **disparar o gancho `Notification` e provar que nenhuma requisição ao Telegram
saiu.** Um teste de ausência, que é o que protege um requisito de silêncio.

### Antirrepetição

Aviso repetido é aviso ignorado. Duas regras:

1. `vigia_falhou` só avisa na **terceira** falha seguida da mesma unidade (OA-08);
2. o mesmo par (unidade, tipo de evento) não avisa duas vezes em menos de 5 minutos — o
   `evento` já tem carimbo, a consulta é uma linha.

## Critérios de aceite

| Critério | Como provar |
| --- | --- |
| Os três avisos do requisito chegam | Ciclo de ponta a ponta: três mensagens (iniciada, PR aberto, bloqueada) na conversa |
| Sessão pedindo decisão **não** avisa | Disparar o gancho `Notification` com o Telegram configurado → nenhuma requisição sai; `avisos.log` registra |
| Aviso e estado não divergem | Para cada mensagem enviada existe uma linha em `evento` com o mesmo carimbo |
| Falha de entrega não altera estado | Telegram inalcançável → a transição acontece e o aviso fica no registro |
| Antirrepetição funciona | Duas transições iguais em 1 min → uma mensagem |
| Nenhum `notify()` solto | `grep -n "notify(" bin/orq` → só a função de emissão a partir do evento |

## Riscos

- **O teste de ausência é o único guarda do silêncio.** Se alguém padronizar
  `ORQ_AVISO_DESTINO=telegram` globalmente e o gancho não sobrescrever, o requisito quebra
  sem nenhum sintoma visível — só o incômodo de receber duas notificações. Por isso o caso
  de teste é obrigatório e nomeado.
- **Volume.** Uma esteira de trinta unidades gera facilmente cem mensagens por dia. Se
  virar ruído, a saída é cortar os eventos operacionais (`recolhida`, `espelho_falhou`) por
  configuração — `orq config set avisos <lista>` —, nunca cortar os três do requisito.
