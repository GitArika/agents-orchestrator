---
name: esteira-operar
description: Use para conduzir uma esteira de tarefas do ClickUp com o comando `orq` — ver o que está pronto e o que está bloqueado por dependência, saber quantas sessões a máquina aguenta agora, despachar sessões governadas em cópias de trabalho isoladas, acompanhar o vigia de PR, e descobrir o que espera o gate humano. Use quando pedirem para rodar, despachar, priorizar ou conferir o andamento de uma esteira; quando perguntarem "o que eu devo tocar agora", "quantas sessões cabem aqui", "o que está travado", "dispare as próximas", "tem algo me esperando"; ou antes de abrir qualquer sessão longa em segundo plano para trabalho rastreado — a esteira dá a ela cópia de trabalho, ordem de serviço e canal de aviso que um lançamento improvisado não dá.
---

# Operar a esteira

`orq` transforma uma lista do ClickUp numa esteira de agentes auto-contidos. Referência
completa dos comandos: `orq --help` e o `README.md` do repositório do orquestrador.

## Antes de qualquer coisa

```bash
orq doctor
```

Ele **prova** cada dependência por chamada real: o agente responde a um prompt, o `gh`
autentica, o git abre e fecha uma worktree, a cerca está íntegra, o Telegram entrega. Nunca
despache com o pré-voo vermelho — a versão antiga dele acreditava em declaração, dava verde
com token morto, e cada sessão morria dois segundos depois de nascer enquanto o quadro
ficava marcado como se alguém estivesse trabalhando.

## A divisão de autoridade — diga isto em voz alta quando importar

Três fontes de verdade que não se sobrepõem. Quase todo defeito de orquestração vem de
embaralhá-las:

| Pergunta | Quem manda | Por que não em outro lugar |
| --- | --- | --- |
| Em que status a unidade está, o que depende de quê, PR aberto, devoluções | **O banco SQLite da esteira** (`~/.config/orquestrador/esteiras/<nome>.db`) | É a única escrita transacional: dois processos não pisam um no outro, e uma queda no meio nunca deixa estado pela metade. |
| O que a tarefa pede, o que foi decidido nos comentários | **ClickUp** | É o quadro do time. O status ali é só um espelho do banco — nunca é ele quem decide a transição. |
| O que está rodando agora | **Os processos vivos** | Uma marca de "rodando" gravada em disco sobrevive a um travamento e mente. O `orq` deriva isso a cada comando (tmux, PID). |

Nada em `~/.claude/orchestrator/state/` é autoridade: são ordens de serviço, logs e um
histórico só-acrescenta para auditoria. Pode apagar tudo (menos o banco, que fica em
`~/.config/orquestrador/esteiras/`).

## A esteira é uma máquina de cinco estados

```
backlog ──> em_progresso ──> revisão ──> pronto
   ^              │              │
   └── bloqueado ─┴──────────────┘
```

Uma unidade nasce em `backlog`. `orq dispatch` lança uma sessão, que faz o ciclo inteiro —
lê o cartão, implementa, revisa o próprio trabalho, roda a verificação do projeto, abre um
PR — e sai por um de dois caminhos: `orq advance --pr <n>` (vai para `revisão`) ou
`orq hold --motivo "..."` (vai para `bloqueado`). Não há mais um "reprovar": quem reprova
agora é o gate humano, no PR.

**Dependência libera só quando a dependência chega em `pronto`.** A cópia de trabalho nasce
do branch de publicação; enquanto a dependência não estiver fundida, o código dela
simplesmente não existe na base da worktree. Não há mais o conceito de "libera antes,
dependência de decisão vs. de código": com um papel só, todo o trabalho é código, e `pronto`
é o único ponto em que ele está garantidamente na base.

## O ciclo

```bash
orq board           # o quadro inteiro, os cinco status
orq next             # o que pode começar, em ordem de prioridade
orq dispatch -n 2   # dispara as duas de maior prioridade (confirma antes)
orq status           # acompanha o que está vivo e o que pede decisão
```

`orq run <unidade>` lança uma sessão para uma unidade específica, pronta ou não
(`--force` ignora status/dependência/vaga — decisão sua, não da esteira). `orq attach
<unidade>` entra na sessão tmux já lançada; `orq log <unidade> -f` acompanha sem entrar.

## Capacidade: corrija por medida, nunca por palpite

```bash
orq capacity        # quantas sessões cabem, e por quê
orq host            # o que limita esta máquina agora
```

O teto sai do menor entre memória, processadores e carga. O orçamento é **um só** — com um
papel único não há mais "por estágio". `orq capacity` mostra o consumo real das sessões
vivas; um orçamento inventado, sete vezes acima do medido, já serializou uma esteira
inteira: a máquina admitia uma sessão por vez e o teto configurado nunca era alcançado.

Em Linux com systemd, `orq host` lê a **fatia do usuário**, não a máquina. É o número que
importa: uma fatia pode estar sufocada com o medidor da máquina mostrando memória de sobra.

## O laço autônomo e o vigia de PR

```bash
orq loop                 # roda em primeiro plano; Ctrl-C para
tmux new-session -d -s orq-loop-<esteira> "cd <repo> && orq loop"   # deixar rodando
tmux kill-session -t orq-loop-<esteira>                              # para; sessões em curso continuam
```

A cada ciclo (60s por padrão) ele:

1. **Vigia os PRs abertos** (`gh`, a cada ciclo): merge → `pronto` e libera dependentes;
   `CHANGES_REQUESTED` → relança a mesma sessão com os comentários da revisão; fechado sem
   merge → `bloqueado`.
2. **Recolhe sessão morta** — status de trabalho sem sessão viva —, devolve para `backlog`
   com uma falta (`strikes`) contada.
3. **Preenche a capacidade livre** com o que está pronto para começar.

Ele para sozinho quando não há nada vivo nem pronto por `idle_ticks_to_stop` ciclos (padrão
20), ou quando a esteira inteira fica sem trabalho pendente. **Se parar sozinho, o motivo é
um evento no banco** (`laco_parou` ou `esteira_concluida`) — releia a tela da sessão tmux, ou
consulte a tabela `evento` diretamente.

## Quando parar e chamar uma pessoa

- Um PR está em `revisão` há tempo demais: ninguém mais anda até você olhar. O Telegram já
  avisou quando ele abriu.
- A mesma unidade voltou com `CHANGES_REQUESTED` duas vezes: a terceira bloqueia sozinha —
  o defeito provavelmente está no requisito, não na implementação.
- Uma unidade está em `bloqueado`: alguém precisa responder algo. `orq show <unidade>`
  mostra o quê.
- O pré-voo está vermelho.
- `orq host` acusa memória ou swap no teto.

Nunca funda um PR por conta própria dentro de uma sessão, e nunca feche um cartão por conta
própria. Fundir e fechar são decisão humana, sempre.
