# Operação no dia a dia

## Os cinco comandos

```bash
orq doctor       # está tudo de pé? prova cada peça de verdade
orq board        # o quadro: o que está pronto, em revisão, bloqueado, rodando
orq next         # o que pode começar agora, em ordem de prioridade
orq dispatch -n 2   # dispara as duas mais importantes
orq status       # o que está vivo e o que espera você
```

Comece o dia pelo `orq status`. Ele é a resposta para "tem alguma coisa me esperando?".

## Lendo o quadro

`orq board` mostra cada unidade e o status em que está — os cinco do banco, os mesmos do
ClickUp:

| Status | O que significa | O que fazer |
| --- | --- | --- |
| **backlog** | declarada, sem dependência pendente ou ainda esperando uma | `orq dispatch` quando estiver pronta |
| **em_progresso** | uma sessão está trabalhando nela agora | `orq log <unidade> -f` para acompanhar, ou `orq attach` para entrar |
| **revisão** | o PR está aberto, esperando uma pessoa | veja "Quando o PR espera você", abaixo |
| **bloqueado** | parou por decisão humana, ou o PR foi devolvido até o limite | leia o motivo com `orq show <unidade>` |
| **pronto** | o PR foi fundido. Estado terminal — só `orq reopen --forcar` sai dele | nada; quem depende dela já foi liberado |

Não existe mais "deriva": tarefa que está no ClickUp e não foi declarada com `orq task add`
simplesmente não aparece no quadro. A esteira só conhece o que foi declarado.

## Quando o PR espera você

Uma unidade em **revisão** tem um PR aberto. Ninguém mais faz nada até uma pessoa olhar:

- **Aprovar e fundir no GitHub.** O vigia (dentro do laço, a cada 60s) detecta o merge, marca
  a unidade `pronto`, libera quem dependia dela e avisa no Telegram.
- **Pedir mudanças** (`CHANGES_REQUESTED`). O vigia relança a mesma sessão com os comentários
  da revisão — a unidade volta para `em_progresso`. Depois de `max_rework` devoluções (padrão
  2), a terceira vez bloqueia em vez de relançar: o defeito provavelmente está no requisito,
  não na implementação, e isso é decisão humana.
- **Fechar sem fundir.** A unidade vai para `bloqueado`.

Uma unidade em **bloqueado** por decisão explícita (`orq hold`) tem o motivo em
`orq show <unidade>`. Depois de responder:

```bash
orq release <unidade>
```

Ela volta para `backlog`. `--zerar-retrabalho` também zera o contador de devoluções, se a
correção foi no requisito.

Se a máquina não tem tela — um servidor —, configure o Telegram como destino de aviso. Sem
isso, a espera é silenciosa e a esteira parece travada sem motivo. Está em
[Host Linux](host-linux.md).

## Deixar andando sozinha

```bash
orq loop                 # roda em primeiro plano; Ctrl-C para
orq loop --interval 30   # sobrepõe o intervalo padrão (60s)
```

Para deixá-la rodando sem ocupar o terminal, abra dentro de uma sessão `tmux` própria:

```bash
tmux new-session -d -s orq-loop-<esteira> "cd <repo> && orq loop"
tmux kill-session -t orq-loop-<esteira>    # para; as sessões em curso continuam
```

A cada ciclo o laço vigia os PRs abertos, recolhe sessão que morreu sem se despedir e
preenche a capacidade livre com o que está pronto para começar. Duas falhas seguidas de
arranque na mesma unidade contam como falta (`strikes`); no limite, ela vai para
`bloqueado` em vez de tentar para sempre.

**Se o laço parar sozinho**, ele imprime o motivo antes de sair — releia a tela da sua sessão
`tmux` (`tmux capture-pane -p -t orq-loop-<esteira>`) ou o registro que ele deixou no banco:

```bash
sqlite3 ~/.config/orquestrador/esteiras/<esteira>.db \
  "SELECT ts, tipo, texto FROM evento WHERE tipo IN ('laco_parou','esteira_concluida')
   ORDER BY id DESC LIMIT 1;"
```

Ele para sozinho depois de `idle_ticks_to_stop` ciclos (padrão 20) sem nada vivo e sem nada
mudar — é a espera humana em silêncio para sempre que esse limite evita.

## Quantas sessões cabem

```bash
orq capacity      # o teto agora, e por quê
orq host          # o que está limitando a máquina
```

O número sai do menor entre memória, processadores e carga — um orçamento só, porque o papel
é um só. **Corrija por medida, não por palpite:** `orq capacity` mostra o consumo real das
sessões vivas. Um palpite sete vezes acima do real já fez uma máquina admitir uma sessão por
vez, quando caberiam oito.

## Como uma sessão termina

Toda sessão termina de um destes dois jeitos, e você vai ver isso no cartão:

- **`orq advance <unidade> --pr <n>`** — abriu o PR, a unidade vai para `revisão`;
- **`orq hold <unidade> --motivo "..."`** — travou em algo que só uma pessoa resolve, vai para
  `bloqueado`.

Não existe mais um terceiro caminho de "reprovar": quem reprova agora é a pessoa, no PR.

Se uma sessão acabar sem nenhum dos dois — morreu, foi encerrada de fora, o processo caiu —
a unidade fica marcada como sessão morta e é recolhida pelo próprio laço (ou por `orq tick`),
contando uma falta. Ela nunca some.

## Quando alguma coisa está estranha

```bash
orq doctor        # começa por aqui, sempre
```

Se não resolver, a skill `esteira-diagnosticar` tem a lista de sintomas já conhecidos, com a
causa provada de cada um. E os [Aprendizados](aprendizados.md) contam as histórias
completas.
