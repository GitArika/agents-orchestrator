# OA-03 — Máquina de cinco estados e o quadro derivado

**Prioridade:** P0 · **Depende de:** OA-01, OA-02 · **Bloqueia:** OA-04, OA-05, OA-08, OA-11

## Por que existe

Os quatro estágios (spec → implement → review → integrate) morrem junto com os quatro
papéis. No lugar entram cinco status, e a diferença não é cosmética: hoje o estado é
DERIVADO do cruzamento entre ClickUp, TOML e processos vivos
([bin/orq:1411](../../../bin/orq:1411)); a partir daqui o status é um campo gravado, e o
que se deriva é só o que pode ser conferido na hora (sessão viva, dependência satisfeita).

## Escopo

**Dentro:** os cinco status, as transições legais, quem pode disparar cada uma, o cálculo
de "pode começar agora", e os comandos de leitura (`board`, `next`, `status`, `show`).

**Fora:** o vigia de PR que dispara `revisao → pronto` (OA-08), o briefing do agente
(OA-05), a escrita no ClickUp (OA-07).

## Desenho

### Os cinco status

| Status | Significa | Quem tira dele |
| --- | --- | --- |
| `backlog` | Declarada, esperando vaga de máquina ou dependência | o laço, ao despachar |
| `em_progresso` | Um agente auto-contido está trabalhando | o próprio agente |
| `revisao` | PR aberto, esperando o gate humano | o vigia de PR (OA-08) |
| `pronto` | PR fundido; libera quem dependia dela | ninguém — é terminal |
| `bloqueado` | O agente travou, ou a esteira desistiu de tentar | uma pessoa (`orq release`) |

`backlog` cobre dois casos que o quadro precisa distinguir sem inventar status: **pronta**
(dependências satisfeitas, esperando vaga) e **travada por dependência**. A diferença é
calculada na leitura — `SELECT` nas dependências cujo status ≠ `pronto` —, nunca gravada.
Gravar produziria o problema já conhecido: quadro afirmando bloqueio que já acabou.

### Transições legais

```
backlog      → em_progresso   (laço despacha, ou `orq run`)
em_progresso → revisao        (agente: `orq advance` após abrir o PR)
em_progresso → bloqueado      (agente: `orq hold --motivo`)
em_progresso → backlog        (laço recolhe sessão morta; conta strike)
revisao      → pronto         (vigia: PR fundido)
revisao      → em_progresso   (vigia: revisão pediu mudanças — OA-09)
revisao      → bloqueado      (vigia: PR fechado sem merge)
bloqueado    → backlog        (pessoa: `orq release`)
pronto       → —              (terminal; `orq reopen` exige --forcar e grava evento)
```

Qualquer outra transição é recusada pela camada de escrita, com a mensagem dizendo qual
transição foi tentada. A tabela acima é a lista inteira: transição não listada é erro de
programa, não caso de canto.

**Quarentena e retrabalho deixam de ser estados.** Viram `bloqueado` com `motivo` preenchido
(`"3 arranques falhos seguidos"`, `"2 reprovações no PR — o defeito provavelmente é do
requisito"`). O vocabulário do requisito tem cinco palavras e o quadro passa a ter as
mesmas cinco; o porquê vive em `motivo` e no rastro de `evento`.

### Sessão morta continua sendo recolhida

Unidade em `em_progresso` sem sessão viva é arranque falho — a detecção continua sendo o
sistema operacional (`tmux list-sessions` + `kill(pid, 0)`,
[bin/orq:789](../../../bin/orq:789)), nunca um heartbeat gravado. O recolhimento volta a
unidade para `backlog` e incrementa `strikes`; ao atingir `max_strikes`, vai para
`bloqueado` com o motivo. A exceção que já existe hoje é preservada: unidade recém-solta
por `orq release` não conta falta ([bin/orq:2113](../../../bin/orq:2113)) — o bilhete de uso
único vira uma coluna `solta_em` na unidade, consumida pelo primeiro recolhimento.

### Fila de despacho

Pode começar agora quem satisfaz, nesta ordem:

1. `status = 'backlog'`;
2. toda dependência em `pronto`;
3. `modo` não está na lista `skip_modes` (para o laço; `orq run` à mão ignora);
4. há vaga de máquina — o cálculo de RAM/processador de
   [bin/orq:728](../../../bin/orq:728) é preservado, com **um orçamento só**
   (`ram_per_session_gb`), já que não há mais estágios com custos diferentes.

Ordenação: prioridade, depois quantas unidades dependem dela (quem desbloqueia mais vai
antes), depois a chave. O segundo critério é novo e barato: com dependência liberando só no
merge, escolher mal a ordem custa mais do que custava.

### Comandos de leitura

`orq board`, `orq next`, `orq status`, `orq show <unidade>` passam a ler o banco. `show`
não imprime mais descrição e comentários do ClickUp (o motor não fala mais com ele);
imprime o que o banco sabe — status, motivo, dependências, PR, últimos eventos — e a URL do
cartão para quem quiser o resto. Ler o cartão passa a ser trabalho do agente, via
`orq-clickup`.

## Critérios de aceite

| Critério | Como provar |
| --- | --- |
| Transição ilegal é recusada | Teste: `pronto → em_progresso` sem `--forcar` levanta erro nomeando a transição |
| `backlog` distingue pronta de travada | Unidade com dependência em `revisao` aparece como travada; a dependência vai a `pronto` e ela aparece pronta, **sem nenhuma escrita** entre as duas leituras |
| Dependência só libera em `pronto` | Teste: dependência em `revisao` (PR aberto) não libera; em `pronto` libera |
| Sessão morta volta para `backlog` com strike | Matar o tmux da sessão e rodar um tick → status `backlog`, `strikes = 1`, evento gravado |
| `max_strikes` leva a `bloqueado`, não a loop | Repetir até o teto → `bloqueado` com motivo contendo o número de arranques |
| `release` não gera falta | `hold` → `release` → tick → `strikes` inalterado |
| Ciclo de vida inteiro | Teste de ponta a ponta: backlog → em_progresso → revisao → pronto libera dependente |

## Riscos

- **Cinco status escondem o motivo.** Sem quarentena e retrabalho como estados, o quadro
  precisa mostrar `motivo` na linha da unidade bloqueada — caso contrário todo bloqueio
  vira "olhe o log". O critério de aceite do `board` inclui o motivo truncado na linha.
- **`pronto` é terminal e depende do GitHub.** Se o PR for fundido fora do fluxo (merge na
  mão, squash local), o vigia de OA-08 nunca vê `merged` e a unidade fica em `revisao`.
  `orq advance <unidade> --forcar` existe para isso, e grava evento dizendo que foi humano.

## Nota de implementação (22/09/2026)

Duas decisões tomadas ao codificar, não previstas na letra do spec original:

1. **`orq run` e `orq dispatch` NÃO entram nesta unidade.** O spec atribui `backlog →
   em_progresso` a "o laço despacha, ou `orq run`", mas despachar sem lançar (o lançador —
   worktree, tmux, briefing — é OA-05) seria um comando que promete e não faz. Os dois
   continuam apontando para o motor antigo (TOML) até OA-05 lhes dar um lançador de
   verdade. Em compensação, **`orq advance`, `orq hold`, `orq release`, `orq reopen` e
   `orq tick` (só recolhimento) entram**, porque nenhum deles depende de lançar nada — são
   leitura e escrita de estado puras, e é exatamente isso que permite ao ciclo de vida
   inteiro (backlog→em_progresso→revisão→pronto) ser provado de ponta a ponta nesta
   unidade, com `transicionar()` fazendo o papel de `orq run`/`orq advance` de dentro do
   teste. `orq board/next/status/show` também SUBSTITUEM os comandos TOML de mesmo nome —
   mesma decisão de 22/09/2026 já aplicada a `orq init` em OA-02.
2. **A resolução de banco fica completa aqui**, como a nota de OA-02 já sinalizava: `--db`
   (ou `$ORQ_DB`) → banco desta máquina cujo `repo` bate com o repositório onde você está
   → o último banco usado (`~/.claude/orchestrator/state/last-db`). `orq init` continua
   exigindo `--db` explícito — não há o que descobrir antes de o banco existir.

O `solta_em` do texto original virou uma coluna de fato (`ALTER` direto no esquema de
OA-01, sem migração — nada em produção usa a versão anterior).
