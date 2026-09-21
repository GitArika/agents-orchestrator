# OA-09 — Retrabalho a partir do PR

**Prioridade:** P1 · **Depende de:** OA-05, OA-08 · **Bloqueia:** OA-13

## Por que existe

O gate humano tem dois desfechos possíveis além do merge: pedir mudanças ou fechar o PR.
Decisão de 21/09/2026: **"changes requested" relança o agente**, com os comentários da
revisão como escopo. Sem isto, todo PR devolvido vira trabalho manual de alguém reabrir a
sessão — e o conhecimento do que foi pedido ficaria só na aba do navegador.

É o substituto direto do `orq reject` que morre em OA-05: o revisor deixou de ser uma
sessão, mas o caminho de volta continua existindo.

## Escopo

**Dentro:** montar o briefing de retrabalho, relançar na mesma worktree, contar retrabalho,
e o teto que manda para `bloqueado`.

**Fora:** a detecção em si (OA-08), o aviso (OA-11).

## Desenho

### O que o agente recebe

Ao relançar, o briefing é o de OA-05 com um bloco no topo — e ele precisa vir **antes** de
tudo, porque o escopo do retrabalho tem prioridade sobre o resto do cartão:

```
RETRABALHO <n>/<max> — este PR foi devolvido pela revisão humana.

O que foi pedido (revisão de <autor>, <data>):
<corpo da review>

Comentários de linha:
<arquivo>:<linha> — <comentário>
...

Estes achados SÃO o seu escopo, com prioridade sobre o resto da tarefa. O PR
#<n> continua aberto no mesmo branch: corrija, rode os portões de novo,
comite e empurre. NÃO abra outro PR.
```

A coleta é uma chamada:

```bash
gh pr view <n> --repo <repo> --json reviews,comments \
   --jq '.reviews[] | select(.state=="CHANGES_REQUESTED")'
```

mais os comentários de linha (`gh api repos/<repo>/pulls/<n>/comments`). Só as revisões
**posteriores ao último relançamento** entram — carimbo guardado na unidade. Sem isso, a
segunda rodada repetiria os achados da primeira, já corrigidos, e o agente gastaria a
sessão provando que já estava certo.

### Onde roda

Na **mesma worktree e no mesmo branch**. É por isso que OA-05 mantém a worktree viva durante
a revisão. O agente empurra por cima; o PR já existe e se atualiza sozinho — daí a ordem
explícita de não abrir outro PR, que é o erro natural de quem encontra um repositório com
trabalho já publicado.

Antes de relançar, a worktree recebe `git fetch` e `merge --ff-only origin/<base>`, como já
acontece no reuso ([bin/orq:1167](../../../bin/orq:1167)): entre a abertura do PR e a
revisão, outras unidades podem ter sido fundidas. Se o `--ff-only` não passar, a base
divergiu de verdade — conciliar é trabalho de julgamento, então a unidade vai para
`bloqueado` com o motivo, em vez de o agente inventar uma resolução de conflito sozinho.

### O teto

`retrabalho` é uma coluna da unidade (OA-01). Ao atingir `max_rework` (padrão 2), a unidade
vai para `bloqueado` com o motivo: *"3ª devolução no PR — o defeito provavelmente está no
requisito, não na implementação."* É a mesma regra de hoje
([bin/orq:1978](../../../bin/orq:1978)) e a razão dela não mudou: a terceira volta significa
que o problema é do enunciado, e enunciado é decisão humana.

`orq release --zerar-retrabalho` devolve à fila e reseta o contador, para quando a pessoa
corrigiu o requisito.

## Critérios de aceite

| Critério | Como provar |
| --- | --- |
| Devolução relança com o escopo certo | Teste: pedir mudanças no PR → o briefing gravado contém o corpo da review e os comentários de linha |
| Não repete achado já corrigido | Duas rodadas de review → o segundo briefing contém só a segunda |
| Relança na mesma worktree e no mesmo PR | Após a 2ª sessão, o PR é o mesmo número e o branch tem commit novo |
| Base divergida bloqueia em vez de adivinhar | Forçar divergência não-ff → `bloqueado` com motivo citando o conflito |
| O teto leva a `bloqueado` | Terceira devolução → `bloqueado`, motivo menciona o requisito |
| Contador zera quando a pessoa manda | `orq release --zerar-retrabalho` → `retrabalho = 0` |

## Riscos

- **Comentário de revisão pode ser vago.** "não gostei disso aqui" vira escopo impossível.
  O briefing instrui: achado que não dá para agir vira `orq hold` com a citação do
  comentário — parar é melhor que adivinhar o que a pessoa quis dizer.
- **Revisão humana com aprovação parcial.** `reviewDecision=APPROVED` mas sem merge não é
  tratado aqui: a unidade fica em `revisao` até o merge acontecer. Aprovar sem fundir é
  estado legítimo do GitHub, e inventar transição para ele produziria unidade marcada
  pronta com código fora da base.
